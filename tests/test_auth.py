import json
import os
import stat
import urllib.parse

import pytest

from keepsake import auth, net
from keepsake.auth import AuthError, DeviceCodeFlow, TokenManager, TokenStore


class FakeLogin:
    """Scripted responses for the device code and token endpoints."""

    def __init__(self, token_responses, verification_uri="https://www.microsoft.com/link", offline=False):
        self.token_responses = list(token_responses)
        self.verification_uri = verification_uri
        self.offline = offline
        self.requests = []

    def __call__(self, method, url, headers=None, body=None, **kw):
        if self.offline:
            raise net.NetError("offline")
        fields = dict(urllib.parse.parse_qsl(body.decode()))
        self.requests.append((url, fields))
        if url == auth.DEVICECODE_URL:
            return net.HttpResponse(
                200,
                body=json.dumps(
                    {
                        "device_code": "DEV",
                        "user_code": "ABCD-EFGH",
                        "verification_uri": self.verification_uri,
                        "expires_in": 900,
                        "interval": 5,
                    }
                ).encode(),
            )
        status, payload = self.token_responses.pop(0)
        return net.HttpResponse(status, body=json.dumps(payload).encode())


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


TOKENS = {"access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600, "scope": "Files.ReadWrite.AppFolder"}


def flow(tmp_path, login, clock):
    return DeviceCodeFlow("client-123", TokenStore(str(tmp_path)), transport=login, clock=clock, sleep=clock.sleep)


def test_device_flow_pending_slow_down_then_success(tmp_path):
    clock = Clock()
    login = FakeLogin([(400, {"error": "authorization_pending"}), (400, {"error": "slow_down"}), (200, TOKENS)])
    f = flow(tmp_path, login, clock)
    shown = f.start()
    assert shown == {"userCode": "ABCD-EFGH", "verificationUri": "https://www.microsoft.com/link", "expiresIn": 900}
    assert login.requests[0][1] == {"client_id": "client-123", "scope": "Files.ReadWrite.AppFolder offline_access"}
    tokens = f.poll()
    assert tokens["refresh_token"] == "RT1" and tokens["expires_at"] == clock.now + 3600
    assert clock.now == 1000 + 5 + 5 + 10  # interval, interval, interval plus 5 after slow_down
    assert login.requests[1][1]["grant_type"] == auth.DEVICE_GRANT


@pytest.mark.parametrize("error", ["authorization_declined", "expired_token", "bad_verification_code"])
def test_device_flow_terminal_errors(tmp_path, error):
    clock = Clock()
    f = flow(tmp_path, FakeLogin([(400, {"error": error})]), clock)
    f.start()
    with pytest.raises(AuthError) as exc:
        f.poll()
    assert exc.value.reason == error
    assert TokenStore(str(tmp_path)).load() is None


def test_device_flow_times_out_and_cancels(tmp_path):
    clock = Clock()
    f = flow(tmp_path, FakeLogin([(400, {"error": "authorization_pending"})] * 500), clock)
    f.start()
    with pytest.raises(AuthError, match="expired"):
        f.poll()
    g = flow(tmp_path, FakeLogin([]), clock)
    g.start()
    g.cancelled.set()
    with pytest.raises(AuthError, match="cancelled"):
        g.poll()


def test_verification_uri_must_be_microsoft(tmp_path):
    for uri in (
        "https://evil.example/devicelogin",
        "http://microsoft.com/devicelogin",
        "https://microsoft.com.evil.example/x",
    ):
        with pytest.raises(AuthError, match="Microsoft"):
            flow(tmp_path, FakeLogin([], verification_uri=uri), Clock()).start()


def test_needs_client_id(tmp_path):
    with pytest.raises(AuthError, match="client ID"):
        DeviceCodeFlow("", TokenStore(str(tmp_path)))


@pytest.mark.posix
@pytest.mark.skipif(os.name != "posix", reason="file modes need POSIX")
def test_token_file_is_private(tmp_path):
    clock = Clock()
    f = flow(tmp_path, FakeLogin([(200, TOKENS)]), clock)
    f.start()
    f.poll()
    assert stat.S_IMODE(os.stat(tmp_path / auth.TOKEN_FILE).st_mode) == 0o600


def manager(tmp_path, responses, clock, offline=False):
    store = TokenStore(str(tmp_path))
    store.save(
        {"client_id": "client-123", "access_token": "AT1", "refresh_token": "RT1", "expires_at": clock.now + 3600}
    )
    login = FakeLogin(responses, offline=offline)
    return TokenManager(store, lambda: "client-123", transport=login, clock=clock), login, store


def test_refreshes_only_near_expiry_and_keeps_refresh_token(tmp_path):
    clock = Clock()
    mgr, login, store = manager(tmp_path, [(200, {"access_token": "AT2", "expires_in": 3600})], clock)
    assert mgr.access_token() == "AT1" and login.requests == []
    clock.now += 3600 - 200  # inside the 5 minute margin
    assert mgr.access_token() == "AT2"
    assert login.requests[0][1]["grant_type"] == "refresh_token"
    assert store.load()["refresh_token"] == "RT1"  # not returned, so kept


def test_invalid_grant_means_sign_in_needed_and_keeps_file(tmp_path):
    clock = Clock()
    mgr, _, store = manager(tmp_path, [(400, {"error": "invalid_grant"})], clock)
    with pytest.raises(AuthError) as exc:
        mgr.access_token(force_refresh=True)
    assert exc.value.reason == "sign-in-needed" and mgr.last_error == "sign-in-needed"
    assert store.load() is not None


def test_offline_refresh_is_not_a_sign_in_problem(tmp_path):
    clock = Clock()
    mgr, _, _ = manager(tmp_path, [], clock, offline=True)
    with pytest.raises(AuthError) as exc:
        mgr.access_token(force_refresh=True)
    assert exc.value.reason == "offline" and mgr.last_error is None


def test_signed_out(tmp_path):
    mgr = TokenManager(TokenStore(str(tmp_path)), lambda: "c")
    assert not mgr.signed_in()
    with pytest.raises(AuthError, match="signed-out"):
        mgr.access_token()
