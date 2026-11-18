"""Keepsake's built-in sign-in clients (ADR-0032).

These are public clients: neither the device code flow nor a desktop app can keep
a secret, and Google's own pages say so for both client types used here.
They are not credentials. An empty value means no built-in client yet, and the
user's own registration is needed, as before.

A user's own client always wins when one is saved. Every saved sign-in records
the client ID it was made with, and refreshes use that one.

The two Google secrets are not in the repository: secret scanners rightly flag
their shape, so the release build adds ``client_secrets.json`` beside this file
from the owner's git-ignored copy (ADR-0055). A source checkout without it has
no built-in Google client, as before.
"""

import json
import os
from typing import Any

SECRETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")


def _secrets(path: str = SECRETS_FILE) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str) and v.startswith("GOCSPX-")}


_SECRETS = _secrets()

# Microsoft Entra registration "Keepsake": personal accounts, public client
# flows on, Files.ReadWrite.AppFolder and offline_access, no secret.
ONEDRIVE_CLIENT_ID = "85765c01-7092-40b4-a7eb-f61c9d00b6d9"

# Google Cloud client "TVs and Limited Input devices", scope drive.appdata only,
# published to Production. Used by the phone (device code) sign-in.
GOOGLE_CLIENT_ID = "572895278811-l1nic6t0fo5b9om3pmsj24tptt9po3ud.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = _SECRETS.get("googleClientSecret", "")

# Google Cloud client "Desktop app" in the same project (ADR-0044). Used by the browser
# sign-in with a loopback redirect; Google treats its secret as not secret, too.
GOOGLE_DESKTOP_CLIENT_ID = "572895278811-7s60khejasi35c5dmte3tebh8chvaj8f.apps.googleusercontent.com"
GOOGLE_DESKTOP_CLIENT_SECRET = _SECRETS.get("googleDesktopClientSecret", "")


def onedrive_builtin() -> bool:
    return bool(ONEDRIVE_CLIENT_ID)


def google_builtin() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET) or google_browser_builtin()


def google_browser_builtin() -> bool:
    return bool(GOOGLE_DESKTOP_CLIENT_ID and GOOGLE_DESKTOP_CLIENT_SECRET)


def google_phone_builtin() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def google_browser_client(own: dict[str, Any]) -> tuple[str, str]:
    """The user's own Google client if saved (it must be a Desktop app client), otherwise the built-in one."""
    client_id, secret = str(own.get("clientId") or "").strip(), str(own.get("clientSecret") or "")
    if client_id and secret:
        return client_id, secret
    if not google_browser_builtin():  # an ID without its secret is no client (a source checkout)
        return "", ""
    return GOOGLE_DESKTOP_CLIENT_ID, GOOGLE_DESKTOP_CLIENT_SECRET


def onedrive_client_id(own: Any) -> str:
    """The user's own client ID if saved, otherwise the built-in one (or "")."""
    own = str(own or "").strip()
    return own or ONEDRIVE_CLIENT_ID


def google_client(own: dict[str, Any]) -> tuple[str, str]:
    """The user's own Google client if both parts are saved, otherwise the built-in one."""
    client_id, secret = str(own.get("clientId") or "").strip(), str(own.get("clientSecret") or "")
    if client_id and secret:
        return client_id, secret
    if not google_phone_builtin():
        return "", ""
    return GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


def google_secret_for(client_id: str, own: dict[str, Any]) -> str:
    """The secret that belongs to ``client_id``: a refresh keeps the client a sign-in was made with."""
    if GOOGLE_CLIENT_ID and client_id == GOOGLE_CLIENT_ID:
        return GOOGLE_CLIENT_SECRET
    if GOOGLE_DESKTOP_CLIENT_ID and client_id == GOOGLE_DESKTOP_CLIENT_ID:
        return GOOGLE_DESKTOP_CLIENT_SECRET
    if client_id and client_id == str(own.get("clientId") or "").strip():
        return str(own.get("clientSecret") or "")
    return google_client(own)[1]
