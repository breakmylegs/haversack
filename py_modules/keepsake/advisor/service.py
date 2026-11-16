"""Advisor service (v2 spec 8.1, slice 14, ADR-0028).

Read-only (P16): it detects the device and the tuning tools, fetches community
reports and returns recommendations. It never writes Steam settings, other
plugins' files, game files, prefixes or system files. The only files it writes
are its own settings (``advisor.json`` in Keepsake's settings folder) and its
cache folder; ``tests/test_advisor.py`` checks this.

Non-Steam shortcuts are mapped to a Steam app ID through the Ludusavi
manifest's Steam ID (the caller's ``map_game``), with a manual override per
shortcut. Without one, reports are looked up by name with low confidence.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

from .. import devices
from ..fsutil import atomic_write_json, read_json
from . import anticheat, deckverified, recommend, stack
from .cache import SourceCache

SETTINGS_FILE = "advisor.json"
DEFAULTS: dict[str, Any] = {
    "deviceOverride": "",
    "stackOverrides": {},
    "workload": "medium",
    "sourceDeckVerified": True,
    "sourceAntiCheat": True,
    "steamIdOverrides": {},  # shortcut app ID (text) -> Steam app ID
}
SHORTCUT_APPID_MIN = 2**31  # non-Steam shortcuts use app IDs at or above this

MapGame = Callable[[int], dict[str, Any]]


class AdvisorError(ValueError):
    pass


class Advisor:
    def __init__(
        self,
        settings_dir: str,
        cache_dir: str,
        decky_home: str,
        user_home: str,
        user: str,
        map_game: MapGame,
        root: str = "/",
        fetch_reports: Callable[[int | None, str | None], dict[str, Any]] = deckverified.fetch,
        anticheat_fetch: Callable[[], bytes] | None = None,
    ) -> None:
        self._settings_path = os.path.join(settings_dir, SETTINGS_FILE)
        self.cache_dir = cache_dir
        self.cache = SourceCache(cache_dir)
        self.anticheat = anticheat.AntiCheatList(cache_dir, fetch=anticheat_fetch)
        self.profiles = devices.load_profiles()
        self.tools = stack.load_tools()
        self.decky_home, self.user_home, self.user, self.root = decky_home, user_home, user, root
        self._map_game = map_game
        self._fetch_reports = fetch_reports
        self._lock = threading.Lock()
        self.facts: dict[str, Any] = {}
        self.device: dict[str, Any] = devices.generic_profile({})
        self.device_how = "generic"
        self.detected: dict[str, Any] = {"tools": [], "os": {"id": "other", "pretty": "", "version": ""}}
        self.game: dict[str, Any] | None = None
        self.reports: list[dict[str, Any]] = []
        self.source_state: dict[str, Any] = {"enabled": True, "cached": False, "error": None, "fetchedAt": None}
        self.ac_state: dict[str, Any] = {"enabled": True, "error": None, "entry": None}

    # Settings (the Advisor's own file)

    def settings(self) -> dict[str, Any]:
        try:
            stored = read_json(self._settings_path, default={})
        except (OSError, ValueError):
            stored = {}
        stored = stored if isinstance(stored, dict) else {}
        return {k: stored.get(k, v) for k, v in DEFAULTS.items()}

    def save_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict) or set(values) - set(DEFAULTS):
            raise AdvisorError("unknown Advisor settings")
        current = self.settings()
        if values.get("deviceOverride") and not any(p["id"] == values["deviceOverride"] for p in self.profiles):
            raise AdvisorError("unknown device")
        if "workload" in values and values["workload"] not in recommend.WORKLOADS:
            raise AdvisorError("workload must be light, medium or heavy")
        for key in ("sourceDeckVerified", "sourceAntiCheat"):
            if key in values and not isinstance(values[key], bool):
                raise AdvisorError(f"{key} must be true or false")
        if "stackOverrides" in values:
            overrides = values["stackOverrides"]
            if not isinstance(overrides, dict):
                raise AdvisorError("tool choices must be an object")
            for category, choice in overrides.items():
                if category not in self.tools.categories:
                    raise AdvisorError(f"unknown category {category}")
                valid = {stack.AUTO, stack.NONE} | {t["id"] for t in self.tools.tools_for(category)}
                if choice not in valid:
                    raise AdvisorError(f"unknown tool for {category}")
        if "steamIdOverrides" in values:
            mapping = values["steamIdOverrides"]
            if not isinstance(mapping, dict) or not all(
                str(k).isdigit() and isinstance(v, int) and not isinstance(v, bool) and 0 < v < SHORTCUT_APPID_MIN
                for k, v in mapping.items()
            ):
                raise AdvisorError("a Steam app ID is a whole number below 2147483648")
        merged = {**current, **values}
        os.makedirs(os.path.dirname(self._settings_path), exist_ok=True)
        atomic_write_json(self._settings_path, merged)
        if "deviceOverride" in values or "stackOverrides" in values:
            self.detect()
        return merged

    # Detection

    def detect(self) -> None:
        """Blocking. Reads DMI, cpuinfo, os-release and plugin manifests only."""
        self.facts = devices.read_facts(self.root)
        self.device, self.device_how = devices.resolve(self.profiles, self.facts, self.settings()["deviceOverride"])
        self.detected = stack.detect(self.tools, self.decky_home, self.user_home, self.user, self.device, self.root)

    def selected(self) -> dict[str, str]:
        return stack.select(self.tools, self.detected, self.settings()["stackOverrides"])

    # Game and reports

    def set_game(self, appid: int, force: bool = False) -> None:
        """Blocking. Choose the game to advise on and load its reports."""
        appid = int(appid)
        found = self._map_game(appid)
        shortcut = appid >= SHORTCUT_APPID_MIN or found.get("kind") == "shortcut"
        override = self.settings()["steamIdOverrides"].get(str(appid)) if shortcut else None
        known = found.get("kind") in ("steam", "shortcut")
        steam_appid = override or found.get("steamAppid") or (appid if known and not shortcut else None)
        how = (
            "manual"
            if override
            else ("manifest" if shortcut and steam_appid else ("steam" if not shortcut else "name"))
        )
        game = {
            "appid": appid,
            "name": str(found.get("name") or "")[:200],
            "shortcut": shortcut,
            "steamAppid": steam_appid,
            "mapping": how,
            "manifestTitle": found.get("manifestTitle"),
        }
        with self._lock:
            self.game = game
        self.load_reports(force)

    def _cache_key(self, game: dict[str, Any]) -> str:
        return f"app:{game['steamAppid']}" if game.get("steamAppid") else f"name:{game.get('name', '').casefold()}"

    def load_reports(self, force: bool = False) -> None:
        game = self.game
        if game is None:
            return
        settings = self.settings()
        reports: list[dict[str, Any]] = []
        state: dict[str, Any] = {
            "enabled": settings["sourceDeckVerified"],
            "cached": False,
            "error": None,
            "fetchedAt": None,
        }
        if state["enabled"] and (game.get("steamAppid") or game.get("name")):
            key = self._cache_key(game)
            cached = self.cache.get(deckverified.SOURCE, key)
            raw: Any = None
            if cached and not force and self.cache.fresh(cached[1]):
                raw, state["cached"], state["fetchedAt"] = cached[0], True, cached[1]
            else:
                try:
                    raw = self._fetch_reports(game.get("steamAppid"), None if game.get("steamAppid") else game["name"])
                except deckverified.SourceError as exc:
                    state["error"] = exc.hint
                    if cached:
                        raw, state["cached"], state["fetchedAt"] = cached[0], True, cached[1]
                else:
                    self.cache.put(deckverified.SOURCE, key, raw)
                    state["fetchedAt"] = time.time()
            items = raw.get("reports") if isinstance(raw, dict) else None
            reports = [deckverified.normalise(r) for r in items or [] if isinstance(r, dict)]
        ac: dict[str, Any] = {"enabled": settings["sourceAntiCheat"], "error": None, "entry": None}
        if ac["enabled"] and (game.get("steamAppid") or game.get("name")):
            try:
                self.anticheat.ensure(force)
            except anticheat.AntiCheatError as exc:
                ac["error"] = exc.hint
            ac["entry"] = self.anticheat.lookup(game.get("steamAppid"), "" if game.get("steamAppid") else game["name"])
        with self._lock:
            if self.game is game:  # the player may have picked another game meanwhile
                self.reports, self.source_state, self.ac_state = reports, state, ac

    def recommendations(self) -> list[dict[str, Any]]:
        game = self.game or {}
        low = bool(game.get("shortcut") and not game.get("steamAppid"))
        reports = self.reports if self.game else []
        return recommend.build(
            reports, self.profiles, self.tools, self.device, self.selected(), self.settings()["workload"], low
        )

    # Views

    def view(self) -> dict[str, Any]:
        selected = self.selected()
        names = {t["id"]: t["name"] for t in self.tools.tools}
        return {
            "settings": self.settings(),
            "device": {
                "id": self.device["id"],
                "name": f"{self.device.get('vendor', '')} {self.device.get('model', '')}".strip(),
                "apu": self.device.get("apu", ""),
                "display": self.device.get("display", {}),
                "how": self.device_how,
                "generic": bool(self.device.get("generic")),
                "verified": bool(self.device.get("verified")),
                "facts": devices.public_facts(self.facts),
            },
            "devices": [{"id": p["id"], "name": f"{p['vendor']} {p['model']} ({p['apu']})"} for p in self.profiles],
            "os": self.detected["os"],
            "stack": {
                "detected": self.detected["tools"],
                "selected": selected,
                "names": names,
                "categories": self.tools.categories,
                "options": {c: [t["id"] for t in self.tools.tools_for(c)] for c in self.tools.categories},
            },
            "conflicts": stack.conflicts(self.tools, self.detected, self.device),
            "game": self.game,
            "source": self.source_state,
            "anticheat": self.ac_state,
            "recommendations": self.recommendations(),
            "attribution": [deckverified.ATTRIBUTION, anticheat.ATTRIBUTION],
        }

    def health(self) -> list[dict[str, Any]]:
        generic = bool(self.device.get("generic"))
        checks: list[dict[str, Any]] = [
            {
                "id": "advisor-device",
                "label": "Device profile",
                "status": "warn" if generic else "ok",
                "detail": "This device is not in the registry, so advice is general. Choose a device in Advisor."
                if generic
                else f"{self.device.get('vendor')} {self.device.get('model')} ({self.device_how}).",
                "items": [],
            }
        ]
        error = self.source_state.get("error")
        checks.append(
            {
                "id": "advisor-sources",
                "label": "Community reports",
                "status": "warn" if error else "ok",
                "detail": error or "Deck Verified answered, or its cached reports are in use.",
                "items": [],
            }
        )
        return checks
