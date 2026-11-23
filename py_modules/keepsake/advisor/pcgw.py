"""PCGamingWiki, optional and off by default (v2 spec 8.1, ADR-0031).

Which upscalers and frame generation a game supports, from the Cargo API.
Since August 2026 that API needs a bot password (Special:BotPasswords, with the
grant "Create, query and delete data through the Cargo extension") and the
MediaWiki login flow. Limits are 60 requests a minute, and a 429 blocks the IP
for a minute, so a game costs two queries and the answer is cached for 7 days.
Content is CC BY-NC-SA: shown with attribution and a link, never committed.

Ported from Tuning Advisor (ADR-0013) onto Keepsake's ``net.request``: one host,
no redirects, the session cookies kept in memory only for this client.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from .. import net

HOST = "www.pcgamingwiki.com"
API = f"https://{HOST}/w/api.php"
SOURCE = "pcgw"
ATTRIBUTION = "From PCGamingWiki, CC BY-NC-SA."
HINT_LOGIN = (
    "PCGamingWiki rejected the sign-in. Use the bot user name shown at Special:BotPasswords, "
    "such as YourName@keepsake, and the bot password it gave you."
)
HINT_GRANT = (
    "The bot password cannot run Cargo queries. In Special:BotPasswords, give it the grant "
    '"Create, query and delete data through the Cargo extension".'
)
SAFE_NAME = re.compile(r"^[^\"\\]{1,200}$")
COOKIE_RE = re.compile(r"^\s*([^=;\s]+)=([^;]*)")

Transport = Callable[..., net.HttpResponse]


class PcgwError(Exception):
    def __init__(self, hint: str) -> None:
        super().__init__(hint)
        self.hint = hint


def split_list(value: Any) -> list[str]:
    """Cargo returns list fields as one comma-separated string."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


class PcgwClient:
    def __init__(self, username: str, password: str, user_agent: str, transport: Transport = net.request) -> None:
        self.username, self.password = username, password
        self._ua = user_agent
        self._transport = transport
        self._cookies: dict[str, str] = {}
        self._logged_in = False
        self._lock = threading.Lock()

    def _send(self, method: str, query: dict[str, Any], form: dict[str, str] | None = None) -> dict[str, Any]:
        headers = {"User-Agent": self._ua, "Accept": "application/json"}
        if self._cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        body = None
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urlencode(form).encode("utf-8")
        try:
            response = self._transport(
                method, f"{API}?{urlencode(query)}", headers, body, timeout=15.0, allowed=frozenset({HOST}), suffixes=()
            )
        except net.NetError as exc:
            raise PcgwError("PCGamingWiki could not be reached. Cached details are shown if there are any.") from exc
        for line in (response.headers.get("set-cookie") or "").split("\n"):
            match = COOKIE_RE.match(line)
            if match:
                self._cookies[match.group(1)] = match.group(2)
        if response.status == 429:
            raise PcgwError("PCGamingWiki is rate limiting this device. Wait a minute and try again.")
        if response.status == 403:
            raise PcgwError("PCGamingWiki blocked the request. Try again later.")
        if response.status != 200:
            raise PcgwError(f"PCGamingWiki answered HTTP {response.status}. Try again later.")
        try:
            data = json.loads(response.body)
        except ValueError as exc:
            raise PcgwError("PCGamingWiki sent an answer Haversack cannot read.") from exc
        if not isinstance(data, dict):
            raise PcgwError("PCGamingWiki sent an answer Haversack cannot read.")
        return data

    def login(self) -> None:
        if not self.username or not self.password:
            raise PcgwError("Enter your PCGamingWiki bot user name and bot password first.")
        self._cookies.clear()
        tokens = self._send("GET", {"action": "query", "meta": "tokens", "type": "login", "format": "json"})
        query = tokens.get("query")
        token = ((query or {}).get("tokens") or {}).get("logintoken") if isinstance(query, dict) else None
        if not isinstance(token, str) or not token:
            raise PcgwError("PCGamingWiki did not return a login token. Try again later.")
        form = {"lgname": self.username, "lgpassword": self.password, "lgtoken": token}
        result = self._send("POST", {"action": "login", "format": "json"}, form)
        login = result.get("login")
        if not isinstance(login, dict) or login.get("result") != "Success":
            raise PcgwError(HINT_LOGIN)
        self._logged_in = True

    def cargo(self, tables: str, fields: str, where: str, join_on: str = "", limit: int = 20) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "action": "cargoquery",
            "tables": tables,
            "fields": fields,
            "where": where,
            "limit": limit,
            "format": "json",
        }
        if join_on:
            query["join_on"] = join_on
        with self._lock:
            if not self._logged_in:
                self.login()
            data = self._send("GET", query)
            error = (data.get("error") or {}).get("code") if isinstance(data.get("error"), dict) else None
            if error == "permissiondenied":  # the session may have expired: sign in once more
                self.login()
                data = self._send("GET", query)
                error = (data.get("error") or {}).get("code") if isinstance(data.get("error"), dict) else None
        if error == "permissiondenied":
            raise PcgwError(HINT_GRANT)
        if error:
            raise PcgwError("PCGamingWiki could not run the query. Try again later.")
        rows = data.get("cargoquery")
        return [r.get("title") or {} for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

    def game(self, appid: int | None, name: str | None) -> dict[str, Any] | None:
        """Blocking. The game's upscaling and frame generation support, or None if the wiki has no page."""
        if appid:
            where = f'Game.Steam_AppID HOLDS "{int(appid)}"'
        elif name and SAFE_NAME.match(name):
            where = f'Game._pageName="{name}"'
        else:
            return None
        video = self.cargo(
            "Game,Video",
            "Game._pageName=Page,Video.Upscaling=Upscaling,Video.Frame_gen=FrameGen,Video.HDR=HDR,Video.Ray_tracing=RayTracing",
            where,
            join_on="Game._pageID=Video._pageID",
            limit=1,
        )
        if not video or not isinstance(video[0], dict):
            return None
        row = video[0]
        page = str(row.get("Page") or "")[:200]
        return {
            "page": page,
            "url": f"https://{HOST}/wiki/" + page.replace(" ", "_") if page else "",
            "upscaling": split_list(row.get("Upscaling"))[:10],
            "frameGen": split_list(row.get("FrameGen"))[:10],
            "hdr": str(row.get("HDR") or "")[:40] or None,
            "rayTracing": str(row.get("RayTracing") or "")[:40] or None,
            "attribution": ATTRIBUTION,
        }


def upscaler_family(name: str) -> str:
    """ "AMD FidelityFX Super Resolution 2" and "FSR 3.1" are both "fsr"."""
    text = name.casefold().replace("fidelityfx super resolution", "fsr").replace("super resolution", "")
    for vendor in ("amd", "intel", "nvidia"):
        text = text.replace(vendor, "")
    return re.sub(r"[^a-z]", "", text)[:4]


def upscaler_supported(name: str, listed: list[str]) -> bool:
    """True when the wiki lists the upscaler by family (FSR, DLSS, XeSS), or lists none."""
    return not listed or upscaler_family(name) in {upscaler_family(s) for s in listed}
