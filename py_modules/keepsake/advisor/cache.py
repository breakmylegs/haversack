"""Source reply cache in the Advisor's own folder (ported from Tuning Advisor, ADR-0013).

Keyed by source and game. Entries live 7 days. A stale entry is still returned
when the source cannot be reached, marked as cached.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from typing import Any

from ..fsutil import atomic_write_json, read_json

TTL = 7 * 24 * 60 * 60


class SourceCache:
    def __init__(self, folder: str, now: Callable[[], float] = time.time) -> None:
        self.folder = folder
        self._now = now

    def _path(self, source: str, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return os.path.join(self.folder, f"{source}-{digest}.json")

    def get(self, source: str, key: str) -> tuple[Any, float] | None:
        try:
            raw = read_json(self._path(source, key), default=None)
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict) or "stored_at" not in raw or raw.get("key") != key:
            return None
        return raw.get("data"), float(raw["stored_at"])

    def fresh(self, stored_at: float) -> bool:
        return self._now() - stored_at < TTL

    def put(self, source: str, key: str, data: Any) -> None:
        os.makedirs(self.folder, exist_ok=True)
        atomic_write_json(self._path(source, key), {"key": key, "stored_at": self._now(), "data": data})
