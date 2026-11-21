"""Steam Remote Play's streaming entries: games you can stream from another device (ADR-0064).

When another device on the same Steam account runs Steam, Steam Remote Play lists the games
installed there in this device's library. For a non-Steam game the tile offers Stream, not
Play. Those entries come from the other device's Steam, not from this device's
``shortcuts.vdf``, and Keepsake never treats one as a game on this device.

Steam's own view decides, as reported by the frontend from ``appStore``: whether this client
has the app installed and which other clients do (``SteamAppOverview.per_client_data``).
- An entry only in Steam's report, installed on another client and not here, is a
  streaming entry (``remote``).
- A shortcut in ``shortcuts.vdf`` is never ``remote``, whatever its paths: it is ``local``,
  or ``unsure`` when nothing of it is found here or Steam says it streams. Unsure shortcuts
  stay in every list, so a real game is never lost from them.

Hiding streaming entries (the tidy-up) stays off and unseen until a device run shows that a
hide on one device does not hide the real game on the other (A201, setting
``streamTidyVerified``). Device names in the report stay on this device (P10).
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from .discovery import LOCAL, REMOTE, UNSURE
from .fsutil import atomic_write_json, read_json

REPORT_FILE = "remote-copies.json"
TIDY_FILE = "tidy-log.json"
MAX_REPORT = 5000
MAX_NAME = 200
CLIENT_NAMES = 8
STEAM_STATES = (LOCAL, REMOTE, UNSURE)


def combine(file_presence: str, steam: str | None) -> str:
    """The final presence of a shortcut found in ``shortcuts.vdf``: never ``remote`` (ADR-0064)."""
    if steam == LOCAL:
        return LOCAL
    if steam == REMOTE:
        return UNSURE  # in this device's file, yet Steam says it streams: listed, labelled, never hidden
    return LOCAL if file_presence == LOCAL else UNSURE


def clean_report(entries: Any) -> list[dict[str, Any]]:
    """The frontend's report, checked: app ID, name, Steam's verdict, other clients, hidden."""
    if not isinstance(entries, list):
        raise ValueError("the report is a list")
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entry in entries[:MAX_REPORT]:
        if not isinstance(entry, dict):
            continue
        appid = entry.get("appid")
        if not isinstance(appid, int) or isinstance(appid, bool) or not 0 < appid < 2**32 or appid in seen:
            continue
        steam = entry.get("steam")
        if steam not in STEAM_STATES:
            continue
        raw = entry.get("clients")
        clients: list[Any] = raw if isinstance(raw, list) else []
        seen.add(appid)
        out.append(
            {
                "appid": appid,
                "name": str(entry.get("name") or "")[:MAX_NAME],
                "steam": steam,
                "clients": [str(c)[:60] for c in clients if isinstance(c, str) and c.strip()][:CLIENT_NAMES],
                "hidden": entry.get("hidden") is True,
            }
        )
    return out


def _fold(name: str) -> str:
    return " ".join(str(name).casefold().split())


class RemoteCopies:
    """The latest report from Steam, the tidy-up log, and the hidden local shortcuts seen."""

    def __init__(self, runtime_dir: str, clock: Callable[[], float] = time.time) -> None:
        self._report_path = os.path.join(runtime_dir, REPORT_FILE)
        self._tidy_path = os.path.join(runtime_dir, TIDY_FILE)
        self.clock = clock
        self._lock = threading.Lock()

    # The report

    def report(self) -> dict[str, Any]:
        data = read_json(self._report_path, default={})
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            return {"at": None, "entries": []}
        return data

    def save_report(self, entries: Any) -> dict[str, Any]:
        """Store a new report. Returns local shortcuts newly hidden since the last one (the guard)."""
        clean = clean_report(entries)
        with self._lock:
            previous = {e["appid"]: e for e in self.report()["entries"]}
            atomic_write_json(self._report_path, {"at": self.clock(), "entries": clean})
            tidy = self._tidy()
            ours = {int(k) for k, v in tidy.get("hidden", {}).items() if v.get("state") in ("pending", "hidden")}
            newly = [
                e
                for e in clean
                if e["steam"] == LOCAL
                and e["hidden"]
                and e["appid"] in previous
                and not previous[e["appid"]]["hidden"]
                and e["appid"] not in ours
            ]
            for entry in clean:  # a hidden streaming entry that shows again counts as "came back"
                record = tidy.get("hidden", {}).get(str(entry["appid"]))
                if record and record.get("state") == "hidden" and not entry["hidden"]:
                    record["state"], record["cameBack"] = "came-back", self.clock()
            self._save_tidy(tidy)
        return {"newlyHidden": [{"appid": e["appid"], "name": e["name"]} for e in newly]}

    def steam_verdicts(self) -> dict[int, dict[str, Any]]:
        return {e["appid"]: e for e in self.report()["entries"]}

    # Presence of discovered games

    def apply(self, games: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Each game with its final ``presence``. Shortcuts in the file are local or unsure, never remote."""
        verdicts = self.steam_verdicts()
        out = []
        for game in games:
            if game.get("kind") != "shortcut":
                out.append(game)
                continue
            steam = verdicts.get(int(game.get("appid") or 0), {}).get("steam")
            out.append({**game, "presence": combine(str(game.get("presence") or UNSURE), steam)})
        return out

    def copies(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Streaming entries (only in Steam's report), and shortcuts here that Steam says stream."""
        verdicts = self.steam_verdicts()
        local_names = {_fold(g["name"]) for g in games if g.get("kind") == "shortcut" and g.get("presence") == LOCAL}
        in_file = {int(g["appid"]) for g in games if g.get("kind") == "shortcut"}
        found: list[dict[str, Any]] = []
        for game in games:
            verdict = verdicts.get(int(game.get("appid") or 0), {})
            if game.get("kind") == "shortcut" and verdict.get("steam") == REMOTE:
                found.append(self._copy(int(game["appid"]), game["name"], UNSURE, verdict, local_names))
        for appid, verdict in verdicts.items():
            if appid not in in_file and verdict["steam"] in (REMOTE, UNSURE):
                found.append(self._copy(appid, verdict["name"], verdict["steam"], verdict, local_names))
        return sorted(found, key=lambda c: (c["presence"] != REMOTE, _fold(c["name"])))

    @staticmethod
    def _copy(appid: int, name: str, presence: str, verdict: dict[str, Any], local_names: set[str]) -> dict[str, Any]:
        # Certain only when Steam says another client has it, this one does not, and it is not in the file.
        certain = presence == REMOTE and verdict.get("steam") == REMOTE
        return {
            "appid": appid,
            "name": name,
            "presence": REMOTE if certain else UNSURE,
            "from": list(verdict.get("clients") or []),
            "clash": _fold(name) in local_names,
            "hidden": bool(verdict.get("hidden")),
        }

    # The tidy-up log (Undo works across restarts)

    def _tidy(self) -> dict[str, Any]:
        data = read_json(self._tidy_path, default={})
        if not isinstance(data, dict) or not isinstance(data.get("hidden"), dict):
            return {"hidden": {}}
        return data

    def _save_tidy(self, data: dict[str, Any]) -> None:
        atomic_write_json(self._tidy_path, data)

    def tidy_log(self) -> dict[str, Any]:
        with self._lock:
            return self._tidy()

    def record(self, appid: int, name: str, state: str, op_id: int | None = None) -> None:
        with self._lock:
            data = self._tidy()
            entry = data["hidden"].get(str(appid), {})
            entry.update({"name": name, "state": state, "at": self.clock()})
            if op_id is not None:
                entry["op"] = op_id
            data["hidden"][str(appid)] = entry
            self._save_tidy(data)

    def forget(self, appid: int) -> None:
        with self._lock:
            data = self._tidy()
            data["hidden"].pop(str(appid), None)
            self._save_tidy(data)


def check(
    copies: list[dict[str, Any]], games: list[dict[str, Any]], synced: Callable[[str], bool], log: dict[str, Any]
) -> dict[str, Any]:
    """The device check's findings (ADR-0062): counts, clashing names, and synced games Steam says stream."""
    shortcuts = [g for g in games if g.get("kind") == "shortcut"]
    local = [g for g in shortcuts if g.get("presence") == LOCAL]
    remote = [c for c in copies if c["presence"] == REMOTE]
    unsure = [c for c in copies if c["presence"] == UNSURE]
    clashes = sorted({c["name"] for c in copies if c["clash"]}, key=_fold)
    streaming = {c["appid"] for c in copies}
    on_copy = [g["name"] for g in shortcuts if int(g.get("appid") or 0) in streaming and synced(g["key"])]
    states = [v.get("state") for v in log.get("hidden", {}).values()]
    return {
        "local": len(local),
        "remote": len(remote),
        "unsure": len(unsure),
        "clashes": clashes,
        "syncedOnCopy": on_copy,
        "hidden": states.count("hidden"),
        "cameBack": states.count("came-back"),
    }
