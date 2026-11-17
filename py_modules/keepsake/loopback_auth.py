"""Browser sign-in: authorization code with PKCE and a loopback redirect (ADR-0044, RFC 8252).

1. ``start`` opens a one-shot listener on the loopback interface, on a port the system
   picks, and returns the provider's sign-in address for the browser.
2. The browser signs in at the provider, which sends it back to
   ``http://<loopback>:<port>/?code=...&state=...``.
3. ``poll`` (in a worker thread) waits for that one request, checks ``state`` in constant
   time, exchanges the code with the PKCE verifier and stores the tokens exactly as the
   device code flow does.

The listener answers only ``GET /`` with the right ``state``; anything else gets a 404
and leaves the attempt running. It closes after the first valid answer, a cancel or the
timeout, whichever comes first. Nothing is ever logged from the callback (T2, T11).
"""

from __future__ import annotations

import base64
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
AUTHORIZE_HOSTS = {"login.microsoftonline.com", "accounts.google.com"}

DONE_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Keepsake</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
    "<h1>You're signed in</h1><p>You can close this tab and go back to Keepsake.</p>"
)
FAILED_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Keepsake</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
    "<h1>Sign-in did not complete</h1><p>Close this tab and try again in Keepsake.</p>"
)


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
        self.servers: list[HTTPServer] = []
        port = 0
        for index, host in enumerate(hosts):
            try:
                server = _server(host, port, self)
            except OSError:
                if index == 0:
                    raise  # the first address (127.0.0.1) must work; the others are a courtesy
                continue
            port = server.server_address[1]
            self.servers.append(server)
        self.port = port
        for server in self.servers:
            threading.Thread(target=server.serve_forever, name="keepsake-signin", daemon=True).start()

    def close(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()


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
        try:
            while not listener.done.wait(0.25):
                if self.cancelled.is_set():
                    raise AuthError("cancelled")
                if self.clock() >= deadline:
                    raise AuthError("expired_token", "the sign-in took too long; start again")
        finally:
            listener.close()
        if self.cancelled.is_set():
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
            raise AuthError(str(data.get("error", f"http-{status}")), str(data.get("error_description", ""))[:200])
        return _store_tokens(self.store, self.client_id, data, self.clock())


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
