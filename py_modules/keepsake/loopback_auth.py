"""Browser sign-in: authorization code with PKCE and a loopback redirect (ADR-0044, RFC 8252).

1. ``start`` opens a one-shot listener on the loopback interface, on a port the system
   picks, and returns the provider's sign-in address for the browser.
2. The browser signs in at the provider, which sends it back to
   ``http://<loopback>:<port>/?code=...&state=...``.
3. ``poll`` (in a worker thread) waits for that one request, checks ``state`` in constant
   time, exchanges the code with the PKCE verifier and stores the tokens exactly as the
   device code flow does.

The listener answers only ``GET /`` with the right ``state``; anything else gets a 404
and leaves the attempt running. Nothing is ever logged from the callback (T2, T11).

**After the attempt ends** (v0.30.2) the listener stays up for ``GRACE_SECONDS`` and answers
every request with a page that says how it ended, never a code: a browser that loads the
address again, or arrives after the user finished on a phone instead, sees "You're signed in"
rather than the browser's own "cannot connect to localhost" error. Then it closes. With a
``localhost`` redirect it holds the same port on ``127.0.0.1`` and ``::1``, trying another
port if ``::1`` has that one taken, so a browser that resolves ``localhost`` to IPv6 arrives.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import hmac
import secrets
import socket
import threading
import time
import urllib.parse
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from . import net
from .auth import MICROSOFT, AuthError, Provider, TokenStore, _form, _store_tokens

TIMEOUT_SECONDS = 300.0
GRACE_SECONDS = 120.0  # how long the listener answers after the attempt ends
PORT_TRIES = 8  # ports tried to find one free on both 127.0.0.1 and ::1
AUTHORIZE_HOSTS = {"login.microsoftonline.com", "accounts.google.com"}

DONE_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Haversack</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
    "<h1>You're signed in</h1><p>You can close this tab and go back to Haversack.</p>"
)
FAILED_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Haversack</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
    "<h1>Sign-in did not complete</h1><p>Close this tab and try again in Haversack.</p>"
)
ELSEWHERE_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Haversack</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
    "<h1>You're signed in</h1><p>You finished signing in on your phone, so Haversack is signed in. "
    "You can close this tab.</p>"
)
MOVED_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Haversack</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
    "<h1>Sign-in moved to your phone</h1><p>Haversack stopped waiting for this tab. Finish on your phone, "
    "or start again in Haversack. You can close this tab.</p>"
)
EXPIRED_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Haversack</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
    "<h1>This sign-in timed out</h1><p>Close this tab and start again in Haversack.</p>"
)
# What the listener shows once the attempt has ended, by how it ended.
ENDED_PAGES = {
    "signed-in": DONE_PAGE,
    "elsewhere": ELSEWHERE_PAGE,
    "moved": MOVED_PAGE,
    "expired": EXPIRED_PAGE,
    "failed": FAILED_PAGE,
}


def pkce_pair() -> tuple[str, str]:
    """A 64-byte random verifier and its S256 challenge (RFC 7636)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=")
    return verifier, challenge.decode("ascii")


class _Listener:
    """One HTTP listener per loopback address, all on the same port, sharing one result."""

    def __init__(self, state: str, hosts: tuple[str, ...]) -> None:
        self.state = state
        self.result: dict[str, str] | None = None
        self.client: dict[str, str] = {}  # which address answered, and the browser (the probe reports it)
        self.done = threading.Event()
        self.ended: str | None = None  # how the attempt ended, once it has: a key of ENDED_PAGES
        self._close_lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self.servers = _bind_all(hosts, self)
        self.port = self.servers[0].server_address[1]
        for server in self.servers:
            threading.Thread(target=server.serve_forever, name="keepsake-signin", daemon=True).start()

    def linger(self, ended: str, seconds: float) -> None:
        """The attempt is over: answer every request with how it ended for ``seconds``, then close."""
        self.ended = ended
        with self._close_lock:
            if not self.servers or self._timer is not None:
                return
            self._timer = threading.Timer(seconds, self.close)
            self._timer.daemon = True
            self._timer.start()

    def close(self) -> None:
        with self._close_lock:
            servers, self.servers = self.servers, []
            if self._timer is not None:
                self._timer.cancel()
        for server in servers:
            server.shutdown()
            server.server_close()


def _bind_all(hosts: tuple[str, ...], listener: _Listener) -> list[HTTPServer]:
    """The same port on every address. The first (127.0.0.1) must work; another address that has
    that port taken means trying a new port, and one the system lacks (no IPv6) is left out."""
    for _attempt in range(PORT_TRIES):
        servers = [_server(hosts[0], 0, listener)]
        port = servers[0].server_address[1]
        clash = False
        for host in hosts[1:]:
            try:
                servers.append(_server(host, port, listener))
            except OSError as exc:
                if exc.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE)):
                    clash = True
                    break
                # No IPv6 here: 127.0.0.1 alone, as before.
        if not clash:
            return servers
        for server in servers:
            server.server_close()
    raise OSError(errno.EADDRINUSE, "no loopback port is free on every address")


def _server(host: str, port: int, listener: _Listener) -> HTTPServer:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET

    class Server(HTTPServer):
        address_family = family
        allow_reuse_address = False

    return Server((host, port), _handler(listener))


def _handler(listener: _Listener) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Keepsake"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            pass  # the query holds the code: never logged

        def _page(self, status: int, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            parts = urllib.parse.urlsplit(self.path)
            if listener.ended is not None:
                # The attempt is over: say how, whatever is asked, and never take a code now.
                if parts.path == "/favicon.ico":
                    self.send_response(204)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self._page(200, ENDED_PAGES.get(listener.ended, FAILED_PAGE))
                return
            query = urllib.parse.parse_qs(parts.query)
            state = (query.get("state") or [""])[0]
            if parts.path != "/" or not hmac.compare_digest(state.encode(), listener.state.encode()):
                self._page(404, FAILED_PAGE)  # not this sign-in's answer: keep waiting
                return
            if listener.done.is_set():
                self._page(410, FAILED_PAGE)
                return
            code, error = (query.get("code") or [""])[0], (query.get("error") or [""])[0]
            listener.result = {"code": code} if code and not error else {"error": error or "no-code"}
            agent = self.headers.get("User-Agent", "")[:200]
            listener.client = {"address": str(self.client_address[0]), "userAgent": agent}
            self._page(200, DONE_PAGE if "code" in listener.result else FAILED_PAGE)
            listener.ended = "signed-in" if "code" in listener.result else "failed"
            listener.done.set()

    return Handler


class LoopbackFlow:
    """One browser sign-in attempt, with the same shape as ``DeviceCodeFlow``: ``start`` then ``poll``."""

    def __init__(
        self,
        client_id: str,
        store: TokenStore,
        transport: net.Transport = net.request,
        clock: Callable[[], float] = time.time,
        provider: Provider = MICROSOFT,
        client_secret: str = "",
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        if not client_id:
            raise AuthError("no-client-id", f"set the {provider.name} client ID first")
        if not provider.authorize_url:
            raise AuthError("no-browser-signin", f"{provider.name} has no browser sign-in")
        self.client_id, self.client_secret, self.provider = client_id, client_secret, provider
        self.store, self.transport, self.clock, self.timeout = store, transport, clock, timeout
        self.cancelled = threading.Event()
        self._listener: _Listener | None = None
        self._verifier = ""
        self.redirect_uri = ""

    def start(self) -> dict[str, Any]:
        state = secrets.token_urlsafe(32)
        self._verifier, challenge = pkce_pair()
        hosts = ("127.0.0.1", "::1") if self.provider.redirect_host == "localhost" else ("127.0.0.1",)
        self._listener = _Listener(state, hosts)
        self.redirect_uri = f"http://{self.provider.redirect_host}:{self._listener.port}"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.provider.scope,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            **dict(self.provider.authorize_extra),
        }
        url = f"{self.provider.authorize_url}?{urllib.parse.urlencode(params)}"
        return {"method": "browser", "authUrl": check_authorize_url(url), "expiresIn": int(self.timeout)}

    def poll(self) -> dict[str, Any]:
        """Wait for the browser to come back, then exchange the code. Returns the stored tokens."""
        listener = self._listener
        if listener is None:
            raise AuthError("not-started")
        deadline = self.clock() + self.timeout
        ended = "moved"
        try:
            while not listener.done.wait(0.25):
                if self.cancelled.is_set():
                    raise AuthError("cancelled")
                if self.clock() >= deadline:
                    ended = "expired"
                    raise AuthError("expired_token", "the sign-in took too long; start again")
            ended = listener.ended or "failed"
        finally:
            listener.linger(listener.ended or ended, GRACE_SECONDS)
        if self.cancelled.is_set():
            listener.ended = "moved"  # the code came, but the user had moved on: nothing is exchanged
            raise AuthError("cancelled")
        result = listener.result or {}
        if "code" not in result:
            raise AuthError(str(result.get("error") or "no-code")[:60])
        fields = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": result["code"],
            "redirect_uri": self.redirect_uri,
            "code_verifier": self._verifier,
        }
        if self.provider.refresh_with_scope:
            fields["scope"] = self.provider.scope
        if self.client_secret:
            fields["client_secret"] = self.client_secret
        status, data = _form(self.transport, self.provider.token_url, fields)
        if status != 200:
            listener.ended = "failed"  # a tab loaded again now says so, not "signed in"
            raise AuthError(str(data.get("error", f"http-{status}")), str(data.get("error_description", ""))[:200])
        return _store_tokens(self.store, self.client_id, data, self.clock())

    def signed_in_elsewhere(self) -> None:
        """The user finished on the phone instead: a tab still open here is told it worked."""
        if self._listener is not None and self._listener.servers:
            self._listener.ended = "elsewhere"

    def close(self) -> None:
        if self._listener is not None:
            self._listener.close()


class BrowserProbe:
    """The Gaming Mode probe's first step (ADR-0044): can Steam's browser reach a loopback redirect?

    Listens like a Microsoft sign-in would (``localhost``, IPv4 and IPv6) and hands out a
    test address with a fake code. Nothing is exchanged; ``result`` says whether the
    browser arrived, over which address, and with which user agent.
    """

    def __init__(self, timeout: float = TIMEOUT_SECONDS, clock: Callable[[], float] = time.time) -> None:
        self._state = secrets.token_urlsafe(16)
        self._listener = _Listener(self._state, ("127.0.0.1", "::1"))
        self._deadline = clock() + timeout
        self._clock = clock
        self.listening = [str(s.server_address[0]) for s in self._listener.servers]
        self.url = f"http://localhost:{self._listener.port}/?state={self._state}&code=probe"

    def result(self) -> dict[str, Any]:
        arrived = self._listener.done.is_set()
        report = {
            "arrived": arrived,
            "ipv6": arrived and ":" in self._listener.client.get("address", ""),
            "listening": self.listening,
            **self._listener.client,
        }
        if arrived or self._clock() >= self._deadline:
            self.close()
        return report

    def close(self) -> None:
        if self._listener.servers:
            self._listener.close()
            self._listener.servers = []


def check_authorize_url(url: str) -> str:
    """Only a provider's own https sign-in page is ever handed to a browser (T2)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in AUTHORIZE_HOSTS:
        raise AuthError("bad-authorize-url", "the sign-in page is not a Microsoft or Google address")
    return url
