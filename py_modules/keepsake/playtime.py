"""Combined playtime across devices (ADR-0049, R2).

Each finished play session becomes one write-once object in the game's cloud folder:

    games/<gameKey>/sessions/<deviceId>/<seq>-<seconds>.json   {"start", "end", "seconds", "deviceId"}

The length sits in the key, so totals come from one listing with no downloads. Objects
are never changed or deleted (P2, outside retention). Times are informational only (P4):
playtime never decides which save wins.

A session that cannot be uploaded (offline) waits in a local queue and is sent on the next
idle pass.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

from .fsutil import atomic_write_json, read_json
from .store import AlreadyExistsError, Store, StoreError

MIN_SECONDS = 60  # shorter is a launch that failed or a menu peek
MAX_SECONDS = 24 * 3600  # longer means a missed exit; never counted
PENDING_FILE = "playtime-pending.json"
_KEY = re.compile(r"^games/[^/]+/sessions/([0-9a-fA-F-]{1,64})/(\d{1,12})-(\d{1,6})\.json$")


def session_key(game_key: str, device_id: str, seq: int, seconds: int) -> str:
    return f"games/{game_key}/sessions/{device_id}/{seq:08d}-{seconds}.json"


def countable(start: float | None, end: float) -> int | None:
    """Whole seconds played, or None when the session is too short, too long or has no start."""
    if start is None or end <= start:
        return None
    seconds = int(end - start)
    return seconds if MIN_SECONDS <= seconds <= MAX_SECONDS else None


def upload(store: Store, game_key: str, device_id: str, seq: int, start: float, end: float) -> None:
    seconds = int(end - start)
    body = {"start": start, "end": end, "seconds": seconds, "deviceId": device_id}
    try:
        store.put_new(session_key(game_key, device_id, seq, seconds), json.dumps(body, sort_keys=True).encode())
    except AlreadyExistsError:
        pass  # sent before; write-once


class Recorder:
    """Records sessions, queueing them locally while the cloud is out of reach."""

    def __init__(self, runtime_dir: str, store: Callable[[], Store], device_id: str, next_seq: Callable[[], int]):
        self._path = os.path.join(runtime_dir, PENDING_FILE)
        self._store, self._device_id, self._next_seq = store, device_id, next_seq

    def _pending(self) -> list[dict[str, Any]]:
        try:
            data = read_json(self._path, default=[])
        except (OSError, ValueError):
            data = []
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []

    def record(self, game_key: str, start: float | None, end: float) -> bool:
        """Queue a finished session (if it counts) and try to send everything queued. True if it counted."""
        if countable(start, end) is None:
            return False
        queue = self._pending()
        queue.append({"gameKey": game_key, "start": start, "end": end, "seq": self._next_seq()})
        atomic_write_json(self._path, queue[-500:])
        self.flush()
        return True

    def flush(self) -> int:
        """Send queued sessions; keep the ones that failed. Returns how many were sent."""
        queue = self._pending()
        if not queue:
            return 0
        left, sent = [], 0
        try:
            store = self._store()
        except StoreError:
            return 0
        for item in queue:
            try:
                upload(store, str(item["gameKey"]), self._device_id, int(item["seq"]), item["start"], item["end"])
                sent += 1
            except (StoreError, KeyError, TypeError, ValueError):
                left.append(item)
        atomic_write_json(self._path, left)
        return sent


def totals(store: Store, game_key: str) -> dict[str, Any]:
    """Seconds played per device and in all, from one listing."""
    by_device: dict[str, int] = {}
    sessions = 0
    for info in store.list(f"games/{game_key}/sessions/"):
        match = _KEY.match(info.key)
        if not match:
            continue
        seconds = int(match.group(3))
        if not MIN_SECONDS <= seconds <= MAX_SECONDS:
            continue
        by_device[match.group(1)] = by_device.get(match.group(1), 0) + seconds
        sessions += 1
    return {"totalSeconds": sum(by_device.values()), "byDevice": by_device, "sessions": sessions}
