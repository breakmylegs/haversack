"""Microsoft sign-in for OneDrive personal: device code flow and token refresh (build prompt section 11).

* Tenant ``consumers`` (personal Microsoft accounts only).
* Scopes ``Files.ReadWrite.AppFolder offline_access``; adding any other is an
  escalation item.
* Tokens live in one file in the settings folder with mode 0600, are never
  logged (``keepsake.redact``) and are only ever sent to the token endpoint
  and Graph.
* Sign-in starts only from a user action (threat model T2).
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from . import net
from .fsutil import atomic_write_json, read_json

AUTHORITY = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
DEVICECODE_URL = f"{AUTHORITY}/devicecode"
TOKEN_URL = f"{AUTHORITY}/token"
SCOPE = "Files.ReadWrite.AppFolder offline_access"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
TOKEN_FILE = "onedrive-token.json"  # noqa: S105 - a file name, not a secret
REFRESH_MARGIN_SECONDS = 300
# The page the user is sent to must be Microsoft's (threat model T2).
VERIFICATION_DOMAINS = ("microsoft.com", "live.com")


class AuthError(Exception):
    """Sign-in failed or is needed again. ``reason`` is a short machine code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def _form(transport: net.Transport, url: str, fields: dict[str, str]) -> tuple[int, dict[str, Any]]:
    body = urllib.parse.urlencode(fields).encode("ascii")
    try:
        response = transport("POST", url, {"Content-Type": "application/x-www-form-urlencoded"}, body)
    except net.NetError as exc:
        raise AuthError("offline", str(exc)) from exc
    try:
        data = json.loads(response.body.decode("utf-8") or "{}")
    except ValueError:
        data = {}
    return response.status, data if isinstance(data, dict) else {}


def _check_verification_uri(uri: str) -> str:
    parts = urlsplit(uri)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not any(host == d or host.endswith("." + d) for d in VERIFICATION_DOMAINS):
        raise AuthError("bad-verification-uri", "the sign-in page is not a Microsoft address")
    return uri


class TokenStore:
    def __init__(self, settings_dir: str) -> None:
        self.path = os.path.join(settings_dir, TOKEN_FILE)

    def load(self) -> dict[str, Any] | None:
        try:
            data = read_json(self.path, default=None)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and data.get("refresh_token") else None

    def save(self, tokens: dict[str, Any]) -> None:
        atomic_write_json(self.path, tokens, mode=0o600)

    def clear(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


def _store_tokens(
    store: TokenStore, client_id: str, data: dict[str, Any], now: float, previous_refresh: str = ""
) -> dict[str, Any]:
    access = data.get("access_token")
    refresh = data.get("refresh_token") or previous_refresh
    if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
        raise AuthError("bad-token-response", "no access or refresh token returned")
    try:
        expires_in = int(data.get("expires_in", 3600))
    except (TypeError, ValueError):
        expires_in = 3600
    tokens = {
        "client_id": client_id,
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": now + expires_in,
        "scope": str(data.get("scope", "")),
        "obtained_at": now,
    }
    store.save(tokens)
    return tokens


class DeviceCodeFlow:
    """One sign-in attempt. ``start`` then ``poll`` (blocking, in a worker thread)."""

    def __init__(
        self,
        client_id: str,
        store: TokenStore,
        transport: net.Transport = net.request,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not client_id:
            raise AuthError("no-client-id", "set the OneDrive client ID first (docs/setup-entra.md)")
        self.client_id = client_id
        self.store = store
        self.transport = transport
        self.clock = clock
        self.sleep = sleep
        self.cancelled = threading.Event()
        self.device: dict[str, Any] | None = None

    def start(self) -> dict[str, Any]:
        status, data = _form(self.transport, DEVICECODE_URL, {"client_id": self.client_id, "scope": SCOPE})
        if status != 200 or not data.get("device_code") or not data.get("user_code"):
            raise AuthError("devicecode-failed", str(data.get("error", status)))
        uri = _check_verification_uri(str(data.get("verification_uri", "")))
        self.device = {
            "device_code": str(data["device_code"]),
            "user_code": str(data["user_code"]),
            "verification_uri": uri,
            "expires_at": self.clock() + int(data.get("expires_in", 900)),
            "interval": max(1, int(data.get("interval", 5))),
        }
        return {
            "userCode": self.device["user_code"],
            "verificationUri": uri,
            "expiresIn": int(data.get("expires_in", 900)),
        }

    def poll(self) -> dict[str, Any]:
        """Poll until signed in, declined, expired or cancelled. Returns stored tokens."""
        if self.device is None:
            raise AuthError("not-started")
        interval = float(self.device["interval"])
        while True:
            if self.cancelled.is_set():
                raise AuthError("cancelled")
            if self.clock() >= self.device["expires_at"]:
                raise AuthError("expired_token", "the code expired; start again")
            self.sleep(interval)
            if self.cancelled.is_set():
                raise AuthError("cancelled")
            status, data = _form(
                self.transport,
                TOKEN_URL,
                {"grant_type": DEVICE_GRANT, "client_id": self.client_id, "device_code": self.device["device_code"]},
            )
            if status == 200:
                return _store_tokens(self.store, self.client_id, data, self.clock())
            error = str(data.get("error", f"http-{status}"))
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5  # RFC 8628 section 3.5
                continue
            raise AuthError(error, str(data.get("error_description", ""))[:200])


class TokenManager:
    """Hands out a valid access token, refreshing proactively. Thread-safe."""

    def __init__(
        self,
        store: TokenStore,
        client_id: Callable[[], str],
        transport: net.Transport = net.request,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.client_id = client_id
        self.transport = transport
        self.clock = clock
        self._lock = threading.Lock()
        self.last_error: str | None = None

    def signed_in(self) -> bool:
        return self.store.load() is not None

    def access_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            tokens = self.store.load()
            if tokens is None:
                raise AuthError("signed-out", "sign in to OneDrive first")
            if not force_refresh and float(tokens.get("expires_at", 0)) - self.clock() > REFRESH_MARGIN_SECONDS:
                return str(tokens["access_token"])
            return str(self._refresh(tokens)["access_token"])

    def _refresh(self, tokens: dict[str, Any]) -> dict[str, Any]:
        client_id = str(tokens.get("client_id") or self.client_id())
        status, data = _form(
            self.transport,
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": str(tokens["refresh_token"]),
                "scope": SCOPE,
            },
        )
        if status != 200:
            error = str(data.get("error", f"http-{status}"))
            # invalid_grant means the refresh token is no longer accepted: sign in again.
            self.last_error = "sign-in-needed" if error in ("invalid_grant", "interaction_required") else error
            raise AuthError(self.last_error, str(data.get("error_description", ""))[:200])
        self.last_error = None
        return _store_tokens(self.store, client_id, data, self.clock(), str(tokens["refresh_token"]))
