"""Backend settings and secrets (slice 10), and Google sign-in through the shared device code flow."""

import json
import os
import stat
import urllib.parse

import pytest

from keepsake import net
from keepsake.auth import GOOGLE, AuthError, DeviceCodeFlow, TokenManager, TokenStore
from keepsake.backends import BackendConfigError, CredentialStore

# Assembled at runtime so the file holds no secret-shaped literal.
SECRET = "pass" + "word-123"


def test_secrets_are_never_returned_and_blank_keeps_them(tmp_path):
    store = CredentialStore(str(tmp_path))
    saved = store.save("webdav", {"url": "https://dav.example.test/files/", "username": "me", "password": SECRET})
    assert saved == {
        "url": "https://dav.example.test/files/",
        "username": "me",
        "password": "",
        "passwordSet": True,
        "configured": True,
    }
    store.save("webdav", {"username": "me2", "password": ""})  # blank keeps the stored password
    assert store.load("webdav")["password"] == SECRET and store.load("webdav")["username"] == "me2"


@pytest.mark.parametrize(
    ("kind", "values", "message"),
    [
        ("webdav", {"url": "http://dav.example.test/"}, "https"),
        ("webdav", {"url": "https://user:pw@dav.example.test/"}, "without a user name"),
        ("s3", {"endpoint": "https://s3.example.test", "bucket": "Bad_Bucket"}, "bucket"),
        ("s3", {"region": "EU WEST"}, "region"),
        ("s3", {"prefix": "../up"}, "prefix"),
        ("gdrive", {"unknown": "x"}, "unknown"),
    ],
)
def test_invalid_settings_are_refused(tmp_path, kind, values, message):
    with pytest.raises(BackendConfigError, match=message):
        CredentialStore(str(tmp_path)).save(kind, values)


def test_configured_needs_every_required_field(tmp_path):
    store = CredentialStore(str(tmp_path))
    assert store.configured("s3") is False
    store.save(
        "s3",
        {"endpoint": "https://s3.example.test", "bucket": "saves", "accessKey": "AKIDEXAMPLE", "secretKey": SECRET},
    )
    assert store.configured("s3") is True
    assert store.public("s3")["prefix"] == "keepsake"
    store.clear("s3")
    assert store.configured("s3") is False


@pytest.mark.posix
@pytest.mark.skipif(os.name != "posix", reason="file modes need POSIX")
def test_backend_files_are_private(tmp_path):
    CredentialStore(str(tmp_path)).save("gdrive", {"clientId": "id", "clientSecret": SECRET})
    assert stat.S_IMODE(os.stat(tmp_path / "google-client.json").st_mode) == 0o600


class Recorder:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, method, url, headers=None, body=None, **kw):
        self.calls.append((url, dict(urllib.parse.parse_qsl((body or b"").decode()))))
        status, data = self.answers.pop(0)
        return net.HttpResponse(status=status, body=json.dumps(data).encode())


def test_google_device_flow_uses_the_secret_and_the_appdata_scope(tmp_path):
    transport = Recorder(
        [
            (
                200,
                {
                    "device_code": "dc",
                    "user_code": "ABCD-EFGH",
                    "verification_url": "https://www.google.com/device",
                    "expires_in": 1800,
                    "interval": 5,
                },
            ),
            (428, {"error": "authorization_pending"}),
            (200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3599}),
        ]
    )
    store = TokenStore(str(tmp_path), GOOGLE.token_file)
    flow = DeviceCodeFlow(
        "client", store, transport=transport, sleep=lambda s: None, provider=GOOGLE, client_secret=SECRET
    )
    assert flow.start()["verificationUri"] == "https://www.google.com/device"
    flow.poll()
    (code_url, code_form), _, (token_url, token_form) = transport.calls
    assert code_url == "https://oauth2.googleapis.com/device/code"
    assert code_form == {"client_id": "client", "scope": "https://www.googleapis.com/auth/drive.appdata"}
    assert token_url == "https://oauth2.googleapis.com/token" and token_form["client_secret"] == SECRET
    assert store.load()["refresh_token"] == "rt"


def test_google_sign_in_page_must_be_google(tmp_path):
    transport = Recorder(
        [(200, {"device_code": "d", "user_code": "u", "verification_url": "https://evil.test/device"})]
    )
    flow = DeviceCodeFlow("c", TokenStore(str(tmp_path), GOOGLE.token_file), transport=transport, provider=GOOGLE)
    with pytest.raises(AuthError, match="bad-verification-uri"):
        flow.start()


def test_google_refresh_sends_the_secret_and_no_scope(tmp_path):
    store = TokenStore(str(tmp_path), GOOGLE.token_file)
    store.save({"client_id": "c", "access_token": "old", "refresh_token": "rt", "expires_at": 0})
    transport = Recorder([(200, {"access_token": "new", "expires_in": 3600})])
    manager = TokenManager(store, lambda: "c", transport=transport, provider=GOOGLE, client_secret=lambda: SECRET)
    assert manager.access_token() == "new"
    form = transport.calls[0][1]
    assert form["client_secret"] == SECRET and "scope" not in form and form["refresh_token"] == "rt"
