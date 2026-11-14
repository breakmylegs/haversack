"""Freeze and release of game processes (principle 11, threat model T6).

Rules:

* The PID list is persisted before any process is stopped, so a crash between
  stop and resume can be repaired on the next start.
* Every freeze has a watchdog thread with a hard ceiling that resumes
  everything, independent of the asyncio loop.
* A recorded PID is only resumed if its start time still matches, so a reused
  PID belonging to another process is never signalled.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from collections.abc import Callable, Iterable
from typing import Any

from .fsutil import atomic_write_json, read_json
from .log import log_event
from .procs import ProcInfo, read_proc

FROZEN_FILE = "frozen.json"
HARD_CEILING_SECONDS = 30.0

SIGSTOP = getattr(signal, "SIGSTOP", 19)
SIGCONT = getattr(signal, "SIGCONT", 18)

KillFn = Callable[[int, int], None]


class Freezer:
    def __init__(
        self,
        runtime_dir: str,
        proc_root: str = "/proc",
        kill: KillFn | None = None,
        ceiling: float = HARD_CEILING_SECONDS,
    ) -> None:
        self._path = os.path.join(runtime_dir, FROZEN_FILE)
        self._proc_root = proc_root
        self._kill: KillFn = kill or os.kill
        self._ceiling = min(float(ceiling), HARD_CEILING_SECONDS)
        self._lock = threading.RLock()
        self._watchdog: threading.Timer | None = None
        # In-memory copy, so a corrupt or unwritable state file never blocks a resume.
        self._memory: list[dict[str, int]] = []

    # Persistence

    def _load(self) -> list[dict[str, int]]:
        try:
            data = read_json(self._path, default=[])
        except (OSError, ValueError):
            data = []
        entries = list(self._memory)
        if isinstance(data, list):
            for d in data:
                if isinstance(d, dict) and isinstance(d.get("pid"), int) and isinstance(d.get("starttime"), int):
                    entry = {"pid": d["pid"], "starttime": d["starttime"]}
                    if entry not in entries:
                        entries.append(entry)
        return entries

    def _save(self, entries: list[dict[str, int]]) -> bool:
        self._memory = list(entries)
        try:
            atomic_write_json(self._path, entries)
            return True
        except OSError:
            log_event(logging.ERROR, "freeze.persist_failed", "Could not record frozen processes")
            return False

    def recorded(self) -> list[dict[str, int]]:
        with self._lock:
            return self._load()

    # Freeze and resume

    def freeze(self, procs: Iterable[ProcInfo]) -> list[int]:
        """Stop ``procs``. Returns the PIDs actually stopped.

        Fails closed: if the PID list cannot be persisted, nothing is stopped.
        The watchdog starts before the first signal is sent.
        """
        targets = list(procs)
        with self._lock:
            entries = self._load()
            known = {(e["pid"], e["starttime"]) for e in entries}
            for proc in targets:
                if (proc.pid, proc.starttime) not in known:
                    entries.append({"pid": proc.pid, "starttime": proc.starttime})
            if not self._save(entries):
                return []
            self._arm_watchdog()
            stopped: list[int] = []
            for proc in targets:
                try:
                    self._kill(proc.pid, SIGSTOP)
                    stopped.append(proc.pid)
                except ProcessLookupError:
                    continue
                except PermissionError:
                    log_event(logging.WARNING, "freeze.denied", "Could not stop a process", pid=proc.pid)
            log_event(logging.INFO, "freeze.stopped", "Stopped game processes", count=len(stopped))
            return stopped

    def resume_all(self, reason: str = "normal") -> list[int]:
        """Resume every recorded PID whose start time still matches. Idempotent."""
        with self._lock:
            self._disarm_watchdog()
            entries = self._load()
            resumed: list[int] = []
            failed: list[dict[str, int]] = []
            for entry in reversed(entries):
                pid, starttime = int(entry["pid"]), int(entry["starttime"])
                info = read_proc(pid, self._proc_root)
                if info is None or info.starttime != starttime:
                    continue
                try:
                    self._kill(pid, SIGCONT)
                    resumed.append(pid)
                except ProcessLookupError:
                    continue
                except OSError:
                    failed.append(entry)
            self._save(failed)
            if entries:
                log_event(
                    logging.WARNING if reason != "normal" else logging.INFO,
                    "freeze.resumed",
                    "Resumed game processes",
                    count=len(resumed),
                    reason=reason,
                    failed=len(failed),
                )
            if failed:
                self._arm_watchdog()
            return resumed

    # Watchdog

    def _arm_watchdog(self) -> None:
        self._disarm_watchdog()
        timer = threading.Timer(self._ceiling, self._watchdog_fire)
        timer.daemon = True
        timer.start()
        self._watchdog = timer

    def _disarm_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None

    def _watchdog_fire(self) -> None:
        try:
            self.resume_all(reason="watchdog")
        except Exception:  # noqa: BLE001 - the watchdog must never die silently
            log_event(logging.ERROR, "freeze.watchdog_error", "Watchdog failed to resume processes")

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"recorded": len(self._load()), "watchdogArmed": self._watchdog is not None}
