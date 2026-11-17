"""Device code sign-in and token refresh (build prompt section 11).

Microsoft (OneDrive personal):

* Tenant ``consumers`` (personal Microsoft accounts only).
* Scopes ``Files.ReadWrite.AppFolder offline_access``; adding any other is an
  escalation item.

Google (Google Drive, slice 10):

* The device flow for TVs and limited-input devices, scope ``drive.appdata``
  only (the narrowest Drive scope the flow allows; verified in slice 10).
* The client ID and secret are entered by the user, never committed.

For both, tokens live in one file per provider in the settings folder with
mode 0600, are never logged (``keepsake.redact``) and are only ever sent to the
token endpoint and the provider's API. Sign-in starts only from a user action
(threat model T2).
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Provider:
    name: str
    devicecode_url: str
    token_url: str
    scope: str
    verification_domains: tuple[str, ...]
    token_file: str
    refresh_with_scope: bool
    issuer: str


MICROSOFT = Provider("OneDrive", DEVICECODE_URL, TOKEN_URL, SCOPE, VERIFICATION_DOMAINS, TOKEN_FILE, True, "Microsoft")
GOOGLE = Provider(
    "Google Drive",
    "https://oauth2.googleapis.com/device/code",
    "https://oauth2.googleapis.com/token",
    "https://www.googleapis.com/auth/drive.appdata",
    ("google.com",),
    "google-token.json",
    False,
    "Google",
)


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


def _check_verification_uri(uri: str, provider: Provider = MICROSOFT) -> str:
    parts = urlsplit(uri)
    host = (parts.hostname or "").lower()
    domains = provider.verification_domains
    if parts.scheme != "https" or not any(host == d or host.endswith("." + d) for d in domains):
        raise AuthError("bad-verification-uri", f"the sign-in page is not a {provider.issuer} address")
    return uri


class TokenStore:
    def __init__(self, settings_dir: str, file_name: str = TOKEN_FILE) -> None:
        self.path = os.path.join(settings_dir, file_name)

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
        provider: Provider = MICROSOFT,
        client_secret: str = "",
    ) -> None:
        if not client_id:
            raise AuthError("no-client-id", f"set the {provider.name} client ID first")
        self.client_id = client_id
        self.client_secret = client_secret
        self.provider = provider
        self.store = store
        self.transport = transport
        self.clock = clock
        self.sleep = sleep
        self.cancelled = threading.Event()
        self.device: dict[str, Any] | None = None

    def _client(self) -> dict[str, str]:
        fields = {"client_id": self.client_id}
        if self.client_secret:
            fields["client_secret"] = self.client_secret
        return fields

    def start(self) -> dict[str, Any]:
        status, data = _form(
            self.transport, self.provider.devicecode_url, {"client_id": self.client_id, "scope": self.provider.scope}
        )
        if status != 200 or not data.get("device_code") or not data.get("user_code"):
            raise AuthError("devicecode-failed", str(data.get("error", status)))
        # Microsoft says verification_uri, Google says verification_url.
        uri = _check_verification_uri(
            str(data.get("verification_uri") or data.get("verification_url") or ""), self.provider
        )
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
                self.provider.token_url,
                {"grant_type": DEVICE_GRANT, **self._client(), "device_code": self.device["device_code"]},
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
        provider: Provider = MICROSOFT,
        client_secret: Callable[[str], str] = lambda client_id: "",
    ) -> None:
        self.store = store
        self.client_id = client_id
        self.client_secret = client_secret
        self.provider = provider
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
                raise AuthError("signed-out", f"sign in to {self.provider.name} first")
            if not force_refresh and float(tokens.get("expires_at", 0)) - self.clock() > REFRESH_MARGIN_SECONDS:
                return str(tokens["access_token"])
            return str(self._refresh(tokens)["access_token"])

    def _refresh(self, tokens: dict[str, Any]) -> dict[str, Any]:
        client_id = str(tokens.get("client_id") or self.client_id())
        fields = {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": str(tokens["refresh_token"])}
        if self.provider.refresh_with_scope:
            fields["scope"] = self.provider.scope
        secret = self.client_secret(client_id)  # the secret of the client this sign-in was made with
        if secret:
            fields["client_secret"] = secret
        status, data = _form(self.transport, self.provider.token_url, fields)
        if status != 200:
            error = str(data.get("error", f"http-{status}"))
            # invalid_grant means the refresh token is no longer accepted: sign in again.
            self.last_error = "sign-in-needed" if error in ("invalid_grant", "interaction_required") else error
            raise AuthError(self.last_error, str(data.get("error_description", ""))[:200])
        self.last_error = None
        return _store_tokens(self.store, client_id, data, self.clock(), str(tokens["refresh_token"]))
