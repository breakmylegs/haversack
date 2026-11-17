"""Keepsake's built-in sign-in clients (ADR-0032).

These are public clients: the device code flow cannot keep a secret, and
Google's own pages say so for the "TVs and Limited Input devices" client type.
They are not credentials. An empty value means no built-in client yet, and the
user's own registration is needed, as before.

A user's own client always wins when one is saved. Every saved sign-in records
the client ID it was made with, and refreshes use that one.
"""

from typing import Any

# Microsoft Entra registration "Keepsake": personal accounts, public client
# flows on, Files.ReadWrite.AppFolder and offline_access, no secret.
ONEDRIVE_CLIENT_ID = ""

# Google Cloud client "TVs and Limited Input devices", scope drive.appdata only,
# published to Production.
GOOGLE_CLIENT_ID = ""
GOOGLE_CLIENT_SECRET = ""


def onedrive_builtin() -> bool:
    return bool(ONEDRIVE_CLIENT_ID)


def google_builtin() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def onedrive_client_id(own: Any) -> str:
    """The user's own client ID if saved, otherwise the built-in one (or "")."""
    own = str(own or "").strip()
    return own or ONEDRIVE_CLIENT_ID


def google_client(own: dict[str, Any]) -> tuple[str, str]:
    """The user's own Google client if both parts are saved, otherwise the built-in one."""
    client_id, secret = str(own.get("clientId") or "").strip(), str(own.get("clientSecret") or "")
    if client_id and secret:
        return client_id, secret
    return GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


def google_secret_for(client_id: str, own: dict[str, Any]) -> str:
    """The secret that belongs to ``client_id``: a refresh keeps the client a sign-in was made with."""
    if GOOGLE_CLIENT_ID and client_id == GOOGLE_CLIENT_ID:
        return GOOGLE_CLIENT_SECRET
    if client_id and client_id == str(own.get("clientId") or "").strip():
        return str(own.get("clientSecret") or "")
    return google_client(own)[1]
