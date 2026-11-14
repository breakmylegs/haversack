"""Tracks running sync jobs and open game sessions.

Updates are refused while anything here is active (build prompt section 12).
Slice 7 registers real sync jobs and slice 8 real sessions; slice 2 adds a
simulated job so the guard can be tested on device.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class JobTracker:
    def __init__(self, on_idle: Callable[[], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[int, str] = {}
        self._sessions: set[str] = set()
        self._next = 0
        self._on_idle = on_idle

    @contextmanager
    def job(self, label: str) -> Iterator[None]:
        with self._lock:
            self._next += 1
            job_id = self._next
            self._jobs[job_id] = label
        try:
            yield
        finally:
            with self._lock:
                self._jobs.pop(job_id, None)
                idle = not self._jobs and not self._sessions
            if idle and self._on_idle:
                self._on_idle()

    def open_session(self, game_key: str) -> None:
        with self._lock:
            self._sessions.add(game_key)

    def close_session(self, game_key: str) -> None:
        with self._lock:
            self._sessions.discard(game_key)
            idle = not self._jobs and not self._sessions
        if idle and self._on_idle:
            self._on_idle()

    def busy_reason(self) -> str | None:
        with self._lock:
            if self._jobs:
                return "sync"
            if self._sessions:
                return "session"
            return None
