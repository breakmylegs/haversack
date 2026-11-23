"""Which games are on which SD card or drive, including cards not inserted (R29 stage 4, ADR-0096).

Read only. Steam lists every library it knows in ``steamapps/libraryfolders.vdf``: each entry has
its ``path``, a ``label``, a ``contentid`` that stays with the card, and ``apps`` (the app IDs it
holds), and Steam keeps the entry while the card is out. Haversack adds what only a mounted card can
say: the games' names from their app manifests, and the non-Steam shortcuts whose program is on the
card. It keeps those names in its own small record (``sdcards.json``), so a card that is not
inserted still shows its games by name. Nothing on the card or in Steam's files is changed.

The card labels stay on this device: they are shown here and never sent anywhere (P10).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from . import discovery
from .fsutil import atomic_write_json
from .vdf import VdfError, loads_text

RECORD = "sdcards.json"
MAX_NAMES = 500


def _entries(steam_root: str) -> list[dict[str, Any]]:
    """Every library Steam lists, except Steam's own folder: path, label, contentid and app IDs."""
    path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            data = loads_text(handle.read())
    except (OSError, VdfError):
        return []
    folders = data.get("libraryfolders") or data.get("LibraryFolders") or {}
    root = os.path.realpath(steam_root)
    out = []
    for value in folders.values() if isinstance(folders, dict) else []:
        if not isinstance(value, dict) or not value.get("path"):
            continue
        folder = str(value["path"])
        if os.path.realpath(folder) == root:
            continue  # the internal library is not a card
        raw_apps = value.get("apps")
        apps: dict[str, Any] = raw_apps if isinstance(raw_apps, dict) else {}
        ids = sorted({int(k) for k in apps if str(k).isdigit()})
        key = str(value.get("contentid") or "") or f"path:{folder}"
        out.append({"key": key, "path": folder, "label": str(value.get("label") or ""), "apps": ids})
    return out


class SdCards:
    def __init__(self, runtime_dir: str, clock: Any = time.time) -> None:
        self.path = os.path.join(runtime_dir, RECORD)
        self.clock = clock

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                found = json.load(handle)
            return found if isinstance(found, dict) else {}
        except (OSError, ValueError):
            return {}

    def scan(self, steam_roots: list[str], shortcuts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Each card: its label, whether it is in, when it was last seen, and its games by name.

        ``shortcuts`` are the non-Steam games found on this device (``name`` and ``exe``)."""
        record = self._load()
        cards: list[dict[str, Any]] = []
        seen: set[str] = set()
        for steam_root in steam_roots:
            for entry in _entries(steam_root):
                if entry["key"] in seen:
                    continue
                seen.add(entry["key"])
                raw = record.get(entry["key"])
                known: dict[str, Any] = raw if isinstance(raw, dict) else {}
                names: dict[str, str] = {str(k): str(v) for k, v in (known.get("names") or {}).items()}
                mounted = os.path.isdir(os.path.join(entry["path"], "steamapps"))
                others = list(known.get("shortcuts") or [])
                if mounted:
                    for app in discovery.read_app_manifests(entry["path"]):
                        names[str(app.appid)] = app.name[:120]  # tools are left out of the list below
                    base = os.path.realpath(entry["path"]) + os.sep
                    others = sorted(
                        {
                            str(s.get("name") or "")[:120]
                            for s in shortcuts
                            if s.get("exe") and os.path.realpath(str(s["exe"]).strip('"')).startswith(base)
                        }
                        - {""}
                    )
                    known = {"lastSeen": int(self.clock())}
                games = sorted(
                    (
                        names.get(str(a), f"App {a}")
                        for a in entry["apps"]
                        if not discovery.is_tool(a, names.get(str(a), ""))
                    ),
                    key=str.lower,
                )
                record[entry["key"]] = {
                    "label": entry["label"],
                    "lastSeen": known.get("lastSeen"),
                    "names": dict(list(names.items())[:MAX_NAMES]),
                    "shortcuts": others[:MAX_NAMES],
                }
                cards.append(
                    {
                        "label": entry["label"] or "Unnamed card",
                        "inserted": mounted,
                        "lastSeen": record[entry["key"]]["lastSeen"],
                        "games": games,
                        "shortcuts": others,
                    }
                )
        try:
            atomic_write_json(self.path, record)
        except OSError:
            pass  # the list is still right this time; the names are kept next time
        return sorted(cards, key=lambda c: (not c["inserted"], c["label"].lower()))
