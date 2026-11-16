"""Anti-cheat status from Are We Anti-Cheat Yet (v2 spec 8.1, ADR-0028).

``games.json`` from the AreWeAntiCheatYet repository on GitHub (MIT licence,
copyright Starz0r and Curve) lists games with anti-cheat and whether they work
under Proton. The whole list is downloaded at most once a week, so no game name
or app ID is sent anywhere; a trimmed copy is kept in the Advisor's cache folder
and looked up locally. A failed refresh keeps the old copy. The list is
community input: shown, never acted on. Ported from Tuning Advisor (ADR-0013).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Any

from .. import net
from ..fsutil import atomic_write_json, read_json

URL = "https://raw.githubusercontent.com/AreWeAntiCheatYet/AreWeAntiCheatYet/master/games.json"
SITE = "https://areweanticheatyet.com"
CACHE_FILE = "anticheat.json"
REFRESH_AFTER = 7 * 24 * 60 * 60
RETRY_AFTER = 60 * 60  # after a failure, so an offline device does not retry for every game
MAX_BYTES = 8 * 1024 * 1024
MAX_NOTES = 3
SCHEMA = 1
ATTRIBUTION = "Anti-cheat status from Are We Anti-Cheat Yet (areweanticheatyet.com), MIT licence."

# The project's own wording for each status (MIT, as above).
STATUSES = {
    "Supported": "The developers enabled the anti-cheat on Linux, or it works under Proton as it is.",
    "Running": "Runs on Linux with no impact on online play, but may need some tinkering.",
    "Planned": "The developers have said they plan to support Linux.",
    "Broken": "Will not run online because of its anti-cheat.",
    "Denied": "The developers have said they will not enable the anti-cheat on Linux.",
}
BLOCKED = frozenset({"Broken", "Denied"})


class AntiCheatError(Exception):
    def __init__(self, hint: str) -> None:
        super().__init__(hint)
        self.hint = hint


def download(fetcher: Callable[..., net.HttpResponse] = net.fetch) -> bytes:
    """Blocking."""
    try:
        response = fetcher(URL, max_bytes=MAX_BYTES, timeout=30.0)
    except net.NetError as exc:
        raise AntiCheatError("Could not download the anti-cheat list. It is tried again in an hour.") from exc
    if response.status != 200:
        raise AntiCheatError(f"The anti-cheat list answered HTTP {response.status}.")
    return response.body


def _text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _url(value: Any) -> str:
    text = str(value or "").strip()
    return text[:300] if text.startswith("https://") else ""


def trim(raw: Any) -> dict[str, Any]:
    """Keep what the page shows, keyed by Steam app ID and by name."""
    if not isinstance(raw, list):
        raise AntiCheatError("The anti-cheat list was not valid. Try again later.")
    by_appid: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for game in raw:
        if not isinstance(game, dict) or game.get("status") not in STATUSES:
            continue
        notes = []
        for note in game.get("notes") or []:
            if isinstance(note, list) and note:
                notes.append({"text": _text(note[0], 200), "url": _url(note[1] if len(note) > 1 else "")})
            if len(notes) >= MAX_NOTES:
                break
        entry = {
            "name": _text(game.get("name"), 120),
            "status": game["status"],
            "anticheats": [_text(a, 60) for a in game.get("anticheats") or [] if isinstance(a, str)][:4],
            "notes": notes,
            "slug": _text(game.get("slug"), 120),
            "changed": _text(game.get("dateChanged"), 30),
        }
        stores = game.get("storeIds")
        steam = stores.get("steam") if isinstance(stores, dict) else None
        if steam is not None and str(steam).isdigit():
            by_appid[str(int(steam))] = entry
        if entry["name"]:
            by_name[entry["name"].casefold()] = entry
    if not by_appid and not by_name:
        raise AntiCheatError("The anti-cheat list was empty. Try again later.")
    return {"schema": SCHEMA, "by_appid": by_appid, "by_name": by_name}


class AntiCheatList:
    def __init__(
        self, cache_dir: str, fetch: Callable[[], bytes] | None = None, now: Callable[[], float] = time.time
    ) -> None:
        self.path = os.path.join(cache_dir, CACHE_FILE)
        self._fetch = fetch or download
        self._now = now
        self._data: dict[str, Any] | None = None
        self._failed_at: float | None = None

    def _load(self) -> dict[str, Any] | None:
        if self._data is None:
            try:
                data = read_json(self.path, default=None)
            except (OSError, ValueError):
                data = None
            self._data = data if isinstance(data, dict) and data.get("schema") == SCHEMA else None
        return self._data

    def age(self) -> float | None:
        try:
            return self._now() - os.path.getmtime(self.path)
        except OSError:
            return None

    def ensure(self, force: bool = False) -> None:
        """Blocking. Download when missing or a week old; after a failure wait an hour unless forced."""
        data = self._load()
        age = self.age()
        if data and age is not None and age < REFRESH_AFTER and not force:
            return
        if not force and self._failed_at is not None and self._now() - self._failed_at < RETRY_AFTER:
            if data:
                return
            raise AntiCheatError("Could not download the anti-cheat list. Press Refresh to try again.")
        try:
            fresh = trim(json.loads(self._fetch().decode("utf-8")))
        except (AntiCheatError, ValueError, UnicodeDecodeError):
            self._failed_at = self._now()
            if data:
                return
            raise
        self._failed_at = None
        atomic_write_json(self.path, fresh)
        self._data = fresh

    def lookup(self, appid: int | None, name: str = "") -> dict[str, Any] | None:
        """By Steam app ID, or by exact name when there is no app ID."""
        data = self._load() or {}
        entry = None
        if appid:
            entry = (data.get("by_appid") or {}).get(str(int(appid)))
        elif name:
            entry = (data.get("by_name") or {}).get(name.strip().casefold())
        if not entry:
            return None
        slug = entry.get("slug") or ""
        return {
            **entry,
            "meaning": STATUSES.get(entry.get("status", ""), ""),
            "blocked": entry.get("status") in BLOCKED,
            "by_name": not appid,
            "url": f"{SITE}/game/{slug}" if slug else SITE,
            "attribution": ATTRIBUTION,
        }
