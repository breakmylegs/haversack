"""v0.30.2: the browser sign-in never ends on the browser's own "cannot connect to localhost" page.

The listener answers for a grace period after the attempt ends, holds ``::1`` as well as
``127.0.0.1`` on one port, and a tab left open when the user finished on the phone is told it
worked. Synthetic clients and a fake token endpoint; no real browser is opened.
"""

import asyncio
import errno
import http.client
import socket
import time

import pytest

from keepsake import clients, loopback_auth
from keepsake.auth import AuthError, TokenStore
from keepsake.loopback_auth import LoopbackFlow
from test_app_cloud import CLIENT
from test_backends import Recorder
from test_loopback_auth import TOKENS, polling, query, setup, visit  # noqa: F401 - setup is a fixture


def ipv6_loopback() -> bool:
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
        return True
    except OSError:
        return False


def visit6(port, path):
    conn = http.client.HTTPConnection("::1", port, timeout=10)
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read().decode()
    conn.close()
    return response.status, body


def started(tmp_path, transport=None):
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=transport or Recorder([TOKENS]))
    params = query(flow.start()["authUrl"])
    return flow, params, int(params["redirect_uri"].rsplit(":", 1)[1])


def test_extra_requests_after_signing_in_get_the_signed_in_page(tmp_path):
    flow, params, port = started(tmp_path)
    thread, box = polling(flow)
    status, body = visit(port, f"/?state={params['state']}&code=c")
    thread.join(5)
    assert "tokens" in box and status == 200 and "signed in" in body
    try:
        # The browser loads the address again, or asks for its icon: still answered, never refused.
        again = visit(port, f"/?state={params['state']}&code=c")
        assert again[0] == 200 and "You're signed in" in again[1]
        assert visit(port, "/")[0] == 200 and "You're signed in" in visit(port, "/anything")[1]
        assert visit(port, "/favicon.ico") == (204, "")
    finally:
        flow.close()


def test_the_code_is_exchanged_once_however_often_the_browser_comes_back(tmp_path):
    transport = Recorder([TOKENS, TOKENS])
    flow, params, port = started(tmp_path, transport)
    thread, _box = polling(flow)
    visit(port, f"/?state={params['state']}&code=c")
    thread.join(5)
    try:
        for _ in range(3):
            visit(port, f"/?state={params['state']}&code=c2")
        assert len(transport.calls) == 1
    finally:
        flow.close()


def test_a_failed_exchange_is_not_shown_as_signed_in_on_a_reload(tmp_path):
    flow, params, port = started(tmp_path, Recorder([(400, {"error": "invalid_grant"})]))
    thread, box = polling(flow)
    visit(port, f"/?state={params['state']}&code=c")
    thread.join(5)
    try:
        assert box == {"error": "invalid_grant"}
        assert "did not complete" in visit(port, "/")[1]
    finally:
        flow.close()


def test_the_listener_closes_after_the_grace_period(tmp_path, monkeypatch):
    monkeypatch.setattr(loopback_auth, "GRACE_SECONDS", 0.3)
    flow, params, port = started(tmp_path)
    thread, _box = polling(flow)
    visit(port, f"/?state={params['state']}&code=c")
    thread.join(5)
    assert visit(port, "/")[0] == 200
    time.sleep(1.0)
    with pytest.raises(OSError):
        visit(port, "/")


def test_a_cancelled_attempt_says_it_moved_to_the_phone_then_that_the_phone_worked(tmp_path):
    flow, params, port = started(tmp_path)
    thread, box = polling(flow)
    flow.cancelled.set()  # the user chose "Use your phone instead"
    thread.join(5)
    try:
        assert box == {"error": "cancelled"}
        status, body = visit(port, f"/?state={params['state']}&code=c")
        assert status == 200 and "moved to your phone" in body  # the code is not taken now
        flow.signed_in_elsewhere()
        status, body = visit(port, "/")
        assert (
            status == 200
            and "signing in on your phone, so Keepsake is signed in" in body
            and "You're signed in" in body
        )
    finally:
        flow.close()


def test_a_code_that_came_after_the_user_moved_on_is_not_shown_as_signed_in(tmp_path):
    flow, params, port = started(tmp_path)
    visit(port, f"/?state={params['state']}&code=c")
    flow.cancelled.set()
    try:
        with pytest.raises(AuthError, match="cancelled"):
            flow.poll()
        assert "moved to your phone" in visit(port, "/")[1]
    finally:
        flow.close()


def test_a_timed_out_attempt_says_so(tmp_path):
    now = [1000.0]
    flow = LoopbackFlow("client-x", TokenStore(str(tmp_path)), transport=Recorder([]), clock=lambda: now[0])
    port = int(query(flow.start()["authUrl"])["redirect_uri"].rsplit(":", 1)[1])
    thread, box = polling(flow)
    now[0] += loopback_auth.TIMEOUT_SECONDS + 1
    thread.join(5)
    try:
        assert box == {"error": "expired_token"} and "timed out" in visit(port, "/")[1]
    finally:
        flow.close()


@pytest.mark.skipif(not ipv6_loopback(), reason="no IPv6 loopback here")
def test_a_browser_that_resolves_localhost_to_ipv6_signs_in(tmp_path):
    flow, params, port = started(tmp_path)
    thread, box = polling(flow)
    status, _body = visit6(port, f"/?state={params['state']}&code=c")
    thread.join(5)
    try:
        assert status == 200 and "tokens" in box
        assert visit6(port, "/")[0] == 200  # and the grace page on IPv6 too
    finally:
        flow.close()


def test_a_port_taken_on_ipv6_means_another_port_not_a_missing_listener(monkeypatch):
    real = loopback_auth._server
    clashes = [1]

    def server(host, port, listener):
        if host == "::1" and clashes:
            clashes.pop()
            raise OSError(errno.EADDRINUSE, "in use")
        if host == "::1":
            return real("127.0.0.1", 0, listener)  # stands in for ::1 where the system has no IPv6
        return real(host, port, listener)

    monkeypatch.setattr(loopback_auth, "_server", server)
    listener = loopback_auth._Listener("s", ("127.0.0.1", "::1"))
    try:
        assert len(listener.servers) == 2 and clashes == []  # tried again rather than going without ::1
    finally:
        listener.close()


def test_no_ipv6_at_all_still_listens_on_ipv4(monkeypatch):
    real = loopback_auth._server

    def server(host, port, listener):
        if host == "::1":
            raise OSError(errno.EAFNOSUPPORT, "no IPv6")
        return real(host, port, listener)

    monkeypatch.setattr(loopback_auth, "_server", server)
    listener = loopback_auth._Listener("s", ("127.0.0.1", "::1"))
    try:
        assert len(listener.servers) == 1
    finally:
        listener.close()


def test_the_app_tells_an_open_browser_tab_when_the_phone_sign_in_worked(setup, monkeypatch):  # noqa: F811
    app, _, events, _ = setup
    monkeypatch.setattr(clients, "ONEDRIVE_CLIENT_ID", CLIENT)

    class PhoneFlow:
        """The device code flow, finished on the phone."""

        def __init__(self, *args, **kwargs):
            self.cancelled = asyncio.Event()

        def start(self):
            return {"method": "phone", "userCode": "ABCD"}

        def poll(self):
            app.token_store.save({"client_id": CLIENT, "refresh_token": "rt", "access_token": "at", "expires": 1e12})

    async def run():
        shown = await app.start_signin("onedrive", "browser")
        params = query(shown["authUrl"])
        port = int(params["redirect_uri"].rsplit(":", 1)[1])
        monkeypatch.setattr("keepsake.app.DeviceCodeFlow", PhoneFlow)
        await app.start_signin("onedrive", "phone")  # "Use your phone instead"
        for _ in range(250):
            if any(e[1][0].get("status") == "signed-in" for e in events if e[0] == "keepsake_signin"):
                break
            await asyncio.sleep(0.02)
        page = await asyncio.to_thread(visit, port, f"/?state={params['state']}&code=late")
        await app.stop()
        return page, port

    (status, body), port = asyncio.run(run())
    signed = [e[1][0] for e in events if e[0] == "keepsake_signin" and e[1][0].get("status") == "signed-in"]
    assert signed and signed[0]["method"] == "phone"
    assert status == 200 and "signing in on your phone, so Keepsake is signed in" in body
    with pytest.raises(OSError):
        visit(port, "/")  # gone with the plugin


def test_a_cancel_is_still_a_cancel(tmp_path):
    flow, _params, _port = started(tmp_path)
    flow.cancelled.set()
    try:
        with pytest.raises(AuthError, match="cancelled"):
            flow.poll()
    finally:
        flow.close()
