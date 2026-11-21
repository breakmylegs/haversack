"""Browser sign-in with PKCE and a loopback redirect (ADR-0044). Synthetic clients; a fake token endpoint."""

import asyncio
import base64
import hashlib
import http.client
import pathlib
import threading
import urllib.parse

import pytest

import test_app_cloud
from keepsake import auth, clients, diagnostics, loopback_auth
from keepsake.auth import GOOGLE, MICROSOFT, AuthError, TokenStore
from keepsake.loopback_auth import LoopbackFlow, check_authorize_url, pkce_pair
from test_app_cloud import CLIENT
from test_backends import Recorder

setup = test_app_cloud.setup
TOKENS = (200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})


def query(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


def visit(port, path, agent=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers={"User-Agent": agent} if agent else {})
    response = conn.getresponse()
    body = response.read().decode()
    conn.close()
    return response.status, body


def polling(flow):
    """Run ``poll`` in a thread, as the app does; returns the thread and its outcome box."""
    box = {}

    def run():
        try:
            box["tokens"] = flow.poll()
        except AuthError as exc:
            box["error"] = exc.reason

    thread = threading.Thread(target=run)
    thread.start()
    return thread, box


def test_pkce_challenge_is_the_s256_of_the_verifier():
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128 and "=" not in verifier + challenge  # RFC 7636 section 4.1
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected and pkce_pair()[0] != verifier


@pytest.mark.parametrize(
    ("provider", "host", "extra"),
    [
        (MICROSOFT, "localhost", {"response_mode": "query"}),
        (GOOGLE, "127.0.0.1", {"access_type": "offline", "prompt": "consent"}),
    ],
)
def test_the_sign_in_address_carries_pkce_state_and_a_loopback_redirect(tmp_path, provider, host, extra):
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=Recorder([]), provider=provider)
    shown = flow.start()
    flow.cancelled.set()
    polling(flow)[0].join(5)
    url = shown["authUrl"]
    assert url.startswith(provider.authorize_url + "?") and shown["method"] == "browser"
    params = query(url)
    port = int(params["redirect_uri"].rsplit(":", 1)[1])
    assert params["redirect_uri"] == f"http://{host}:{port}" and 1024 <= port <= 65535
    assert params["client_id"] == "client-x" and params["response_type"] == "code"
    assert params["scope"] == provider.scope and params["code_challenge_method"] == "S256"
    assert len(params["state"]) >= 40 and len(params["code_challenge"]) == 43
    assert {k: params[k] for k in extra} == extra


def test_a_valid_callback_signs_in_and_only_the_right_state_counts(tmp_path):
    transport = Recorder([TOKENS])
    store = TokenStore(str(tmp_path), GOOGLE.token_file)
    flow = LoopbackFlow("client-x", store, transport=transport, provider=GOOGLE, client_secret="not-secret")
    params = query(flow.start()["authUrl"])
    port = int(params["redirect_uri"].rsplit(":", 1)[1])
    thread, box = polling(flow)
    assert visit(port, "/?state=wrong&code=stolen")[0] == 404  # another page guessing: ignored
    assert visit(port, f"/other?state={params['state']}&code=c")[0] == 404
    assert visit(port, "/favicon.ico")[0] == 404
    status, page = visit(port, f"/?state={params['state']}&code=the-code")
    thread.join(10)
    assert status == 200 and "You're signed in" in page
    assert box["tokens"]["refresh_token"] == "rt" and store.load()["client_id"] == "client-x"
    [(url, form)] = transport.calls
    assert url == GOOGLE.token_url
    assert form["grant_type"] == "authorization_code" and form["code"] == "the-code"
    assert form["redirect_uri"] == params["redirect_uri"] and form["client_secret"] == "not-secret"
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=")
    assert challenge.decode() == params["code_challenge"]
    # v0.30.2: it answers for a grace period with the signed-in page, and takes no second code.
    assert visit(port, f"/?state={params['state']}&code=again") == (200, page)
    assert len(transport.calls) == 1
    flow.close()
    with pytest.raises(OSError):
        visit(port, f"/?state={params['state']}&code=again")  # the listener is gone


def test_microsoft_exchange_sends_the_scope_and_no_secret(tmp_path):
    transport = Recorder([TOKENS])
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=transport)
    params = query(flow.start()["authUrl"])
    port = int(params["redirect_uri"].rsplit(":", 1)[1])
    thread, box = polling(flow)
    visit(port, f"/?state={params['state']}&code=c")
    thread.join(10)
    form = transport.calls[0][1]
    assert form["scope"] == MICROSOFT.scope and "client_secret" not in form and "tokens" in box


def test_a_refusal_at_the_provider_ends_the_attempt_without_tokens(tmp_path):
    transport = Recorder([])
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=transport)
    params = query(flow.start()["authUrl"])
    port = int(params["redirect_uri"].rsplit(":", 1)[1])
    thread, box = polling(flow)
    status, page = visit(port, f"/?state={params['state']}&error=access_denied")
    thread.join(10)
    assert status == 200 and "did not complete" in page
    assert box == {"error": "access_denied"} and transport.calls == []


def test_an_answer_with_both_a_code_and_an_error_is_a_refusal(tmp_path):
    transport = Recorder([TOKENS])
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=transport)
    params = query(flow.start()["authUrl"])
    port = int(params["redirect_uri"].rsplit(":", 1)[1])
    visit(port, f"/?state={params['state']}&code=c&error=access_denied")
    with pytest.raises(AuthError, match="access_denied"):
        flow.poll()
    assert transport.calls == []


def test_a_cancel_after_the_browser_answered_still_exchanges_nothing(tmp_path):
    transport = Recorder([TOKENS])
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=transport)
    params = query(flow.start()["authUrl"])
    port = int(params["redirect_uri"].rsplit(":", 1)[1])
    visit(port, f"/?state={params['state']}&code=c")
    flow.cancelled.set()
    with pytest.raises(AuthError, match="cancelled"):
        flow.poll()
    assert transport.calls == []


def test_a_cancel_or_the_timeout_closes_the_listener(tmp_path):
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=Recorder([]))
    port = int(query(flow.start()["authUrl"])["redirect_uri"].rsplit(":", 1)[1])
    thread, box = polling(flow)
    flow.cancelled.set()
    thread.join(5)
    assert box == {"error": "cancelled"}
    assert "moved to your phone" in visit(port, "/")[1]  # v0.30.2: a grace page, not a refused connection
    flow.close()
    with pytest.raises(OSError):
        visit(port, "/")

    now = [1000.0]
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=Recorder([]), clock=lambda: now[0])
    flow.start()
    thread, box = polling(flow)
    now[0] += loopback_auth.TIMEOUT_SECONDS + 1
    thread.join(5)
    assert box == {"error": "expired_token"}


def test_only_provider_sign_in_pages_are_handed_to_a_browser():
    assert check_authorize_url("https://accounts.google.com/o/oauth2/v2/auth?x=1")
    for url in (
        "http://login.microsoftonline.com/x",
        "https://login.microsoftonline.com.evil.example/x",
        "https://evil.example/?https://accounts.google.com/",
        "javascript:alert(1)",
    ):
        with pytest.raises(AuthError, match="bad-authorize-url"):
            check_authorize_url(url)


def test_no_client_no_browser_sign_in(tmp_path):
    with pytest.raises(AuthError, match="client ID"):
        LoopbackFlow("", TokenStore(str(tmp_path)))


def test_the_app_signs_in_through_the_browser_with_the_built_in_client(setup, monkeypatch):
    app, _, events, _ = setup
    monkeypatch.setattr(clients, "ONEDRIVE_CLIENT_ID", CLIENT)

    async def run():
        status = await app.cloud_status()
        shown = await app.start_signin("onedrive", "browser")
        params = query(shown["authUrl"])
        port = int(params["redirect_uri"].rsplit(":", 1)[1])
        await asyncio.to_thread(visit, port, f"/?state={params['state']}&code=c")
        for _ in range(250):
            if events:
                break
            await asyncio.sleep(0.02)
        return status, shown

    status, shown = asyncio.run(run())
    assert status["methods"]["onedrive"] == {"browser": True, "phone": True}
    assert shown["method"] == "browser" and events[0][1][0]["status"] == "signed-in"
    assert app.token_store.load()["client_id"] == CLIENT


def test_google_needs_a_desktop_client_for_the_browser_and_a_tv_client_for_the_phone(setup, monkeypatch):
    app, _, _, _ = setup
    for name in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_DESKTOP_CLIENT_ID",
        "GOOGLE_DESKTOP_CLIENT_SECRET",
    ):
        monkeypatch.setattr(clients, name, "")
    assert asyncio.run(app.cloud_status())["methods"]["gdrive"] == {"browser": False, "phone": False}
    monkeypatch.setattr(clients, "GOOGLE_DESKTOP_CLIENT_ID", "desktop-id")
    monkeypatch.setattr(clients, "GOOGLE_DESKTOP_CLIENT_SECRET", "desktop-secret")
    assert asyncio.run(app.cloud_status())["methods"]["gdrive"] == {"browser": True, "phone": False}
    assert clients.google_browser_client({}) == ("desktop-id", "desktop-secret")
    assert clients.google_secret_for("desktop-id", {}) == "desktop-secret"  # its refreshes use its own secret
    assert clients.google_builtin() is True


def test_gaming_mode_sign_in_setting(setup):
    app, _, _, _ = setup
    assert asyncio.run(app.get_settings())["gamingModeSignin"] == {"onedrive": "browser", "gdrive": "phone"}
    changed = asyncio.run(app.set_setting("gamingModeSignin", {"onedrive": "phone", "gdrive": "browser"}))
    assert changed["gamingModeSignin"] == {"onedrive": "phone", "gdrive": "browser"}
    for bad in (
        {"onedrive": "phone"},
        {"onedrive": "tv", "gdrive": "phone"},
        "browser",
        {"onedrive": "phone", "gdrive": "phone", "x": "phone"},
    ):
        with pytest.raises(ValueError):
            asyncio.run(app.set_setting("gamingModeSignin", bad))


def test_the_probe_reports_whether_the_browser_reached_the_loopback_redirect(setup):
    app, _, _, paths = setup

    async def run():
        assert (await app.signin_probe("result"))["error"] == "not-started"
        url = (await app.signin_probe("start"))["url"]
        before = await app.signin_probe("result")
        parts = urllib.parse.urlsplit(url)
        assert parts.hostname == "localhost" and query(url)["code"] == "probe"
        await asyncio.to_thread(visit, parts.port, f"{parts.path}?{parts.query}", "SyntheticBrowser/1.0")
        return parts.port, before, await app.signin_probe("result")

    port, before, after = asyncio.run(run())
    assert before["arrived"] is False and "127.0.0.1" in before["listening"]
    assert after["arrived"] is True and after["address"] == "127.0.0.1" and after["ipv6"] is False
    assert after["userAgent"] == "SyntheticBrowser/1.0"
    with pytest.raises(OSError):
        visit(port, "/")  # closed once it has answered
    recorded = (pathlib.Path(paths.runtime_dir) / diagnostics.PROBE_FILE).read_text()
    assert "signin-loopback" in recorded


def test_the_phone_sign_in_is_unchanged_by_default(setup, monkeypatch):
    app, _, _, _ = setup
    monkeypatch.setattr(clients, "ONEDRIVE_CLIENT_ID", CLIENT)
    shown = asyncio.run(app.start_signin("onedrive"))
    asyncio.run(app.cancel_signin())
    assert shown["userCode"] == "WXYZ-1234" and "method" not in shown
    assert auth.DeviceCodeFlow  # still the device code flow
