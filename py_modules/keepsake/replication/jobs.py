"""Running transfers: start, pause, resume, stop, and carry on after a restart (slice 18b, ADR-0058).

A small registry (``replication-jobs.json``) lists each job's staging folder. At startup every
listed job is recovered (``transfer.recover``); one the user did not pause resumes by itself.

While any transfer runs, the sleep guard is held. A transfer waits, and resumes by itself:
- while a game runs on this device (P6, and so the game keeps its bandwidth and disk);
- below 30 percent battery unless on mains power (ADR-0045 rule 5).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
from collections.abc import Callable
from typing import Any

from ..fsutil import atomic_write_json, read_json
from . import transfer
from .sleepguard import SleepGuard

BATTERY_FLOOR = 30
HOLD_CHECK_SECONDS = 60.0
MAX_JOBS = 32
STOP_ATTEMPTS = 20
STOP_RETRY_SECONDS = 0.1

ConnectFor = Callable[[str], transfer.Connect]  # a paired device's ID to a connection maker


def hold_reason(percent: int | None, mains: bool | None, game_running: bool) -> str | None:
    """Why transfers should wait now, or None."""
    if game_running:
        return "waiting while a game runs on this device"
    if mains is False and percent is not None and percent < BATTERY_FLOOR:
        return f"waiting: the battery is below {BATTERY_FLOOR} percent; plug in to carry on"
    return None


class Transfers:
    def __init__(
        self,
        registry_path: str,
        connect_for: ConnectFor,
        conditions: Callable[[], str | None] = lambda: None,
        guard: SleepGuard | None = None,
        on_change: Callable[[], None] | None = None,
        retries: int | None = None,
        on_finished: Callable[[transfer.Job], None] | None = None,
    ) -> None:
        self.registry_path = registry_path
        self.connect_for = connect_for
        self.conditions = conditions
        self.guard = guard or SleepGuard()
        self.on_change = on_change
        self.retries = retries
        self.on_finished = on_finished  # told about every job that ends: done, failed or paused
        self.jobs: dict[str, transfer.Job] = {}
        self.tasks: dict[str, asyncio.Task[transfer.Job]] = {}
        self._lock = threading.Lock()
        self._watch: asyncio.Task[None] | None = None

    # The registry of staging folders

    def _registry(self) -> dict[str, str]:
        with self._lock:
            data = read_json(self.registry_path, default={})
        jobs = data.get("jobs") if isinstance(data, dict) else None
        return {str(k): str(v) for k, v in jobs.items()} if isinstance(jobs, dict) else {}

    def _save_registry(self, jobs: dict[str, str]) -> None:
        with self._lock:
            atomic_write_json(self.registry_path, {"version": 1, "jobs": jobs})

    def _remember(self, job: transfer.Job) -> None:
        jobs = self._registry()
        if job.id not in jobs and len(jobs) >= MAX_JOBS:
            raise transfer.TransferError(f"at most {MAX_JOBS} transfers can be kept; stop one first")
        jobs[job.id] = job.staging
        self._save_registry(jobs)

    def _forget(self, job_id: str) -> None:
        jobs = self._registry()
        if jobs.pop(job_id, None) is not None:
            self._save_registry(jobs)

    # Life cycle

    async def start_up(self) -> list[str]:
        """Recover every listed job; resume those the user did not pause. Returns the resumed IDs."""
        resumed = []
        for job_id, staging in self._registry().items():
            job = await asyncio.to_thread(transfer.recover, staging)
            if job is None or job.state == "done":
                self._forget(job_id)
                continue
            self.jobs[job.id] = job
            if job.state == "paused" and not job.by_user:
                self._run(job)
                resumed.append(job.id)
        self._watch = asyncio.create_task(self._watch_holds())
        return resumed

    async def shut_down(self) -> None:
        if self._watch is not None:
            self._watch.cancel()
            self._watch = None
        for task in list(self.tasks.values()):
            task.cancel()
        for task in list(self.tasks.values()):
            with contextlib.suppress(BaseException):
                await task
        self.tasks.clear()
        self.guard.release()

    def start(self, job: transfer.Job) -> dict[str, Any]:
        """Begin a new transfer. Only from a user action (slice 19 makes the offer)."""
        if job.id in self.jobs:
            raise transfer.TransferError("that transfer already exists")
        os.makedirs(job.staging, exist_ok=True)
        self._remember(job)
        self.jobs[job.id] = job
        try:
            self._run(job)
        except RuntimeError:
            # Off the event loop (the v0.30.1 stall): nothing may stay listed as if it were running.
            self.jobs.pop(job.id, None)
            self._forget(job.id)
            transfer.remove_staging(job.staging)
            raise
        return job.public()

    def _run(self, job: transfer.Job) -> None:
        sources = [self.connect_for(peer) for peer in (job.peers or [job.peer_id])]
        receiver = transfer.Receiver(
            job, sources, retries=self.retries, on_progress=lambda _job: self._changed(), hold=self.conditions
        )
        run = receiver.run()
        try:
            task = asyncio.create_task(run)
        except RuntimeError:
            run.close()
            raise
        self.guard.acquire()
        self.tasks[job.id] = task
        job_id = job.id

        def finished(_task: asyncio.Task[transfer.Job]) -> None:
            self._finished(job_id)

        task.add_done_callback(finished)
        self._changed()

    def _finished(self, job_id: str) -> None:
        self.tasks.pop(job_id, None)
        job = self.jobs.get(job_id)
        if job is not None and self.on_finished:
            self.on_finished(job)
        if job is not None and job.state == "done":
            self.jobs.pop(job_id, None)
            self._forget(job_id)
        if not self.tasks:
            self.guard.release()
        self._changed()

    async def _stop_task(self, job_id: str) -> None:
        task = self.tasks.pop(job_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        if not self.tasks:
            self.guard.release()

    def _job(self, job_id: str) -> transfer.Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise transfer.TransferError("that transfer has ended")
        return job

    async def pause(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        await self._stop_task(job_id)
        job.state, job.reason, job.by_user, job.held = "paused", "Paused.", True, False
        await asyncio.to_thread(transfer.save_journal, job)
        self._changed()
        return job.public()

    async def resume(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        if job_id in self.tasks:
            return job.public()
        if job.state not in ("paused", "failed", "waiting"):
            raise transfer.TransferError("that transfer cannot be resumed")
        job.by_user = False
        self._run(job)
        return job.public()

    async def stop(self, job_id: str) -> None:
        """The user's "Stop and remove", after they confirmed it."""
        job = self._job(job_id)
        await self._stop_task(job_id)
        # A write handed to a worker thread can still finish after the task is cancelled, and on
        # Windows an open file blocks the delete: retry briefly, then sweep once more.
        for attempt in range(STOP_ATTEMPTS):
            try:
                await asyncio.to_thread(transfer.stop_and_remove, job)
                break
            except OSError:  # PermissionError, or "not empty" when a late write lands mid-delete
                if attempt == STOP_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(STOP_RETRY_SECONDS)
        await asyncio.sleep(STOP_RETRY_SECONDS)
        await asyncio.to_thread(transfer.remove_staging, job.staging)
        self.jobs.pop(job_id, None)
        self._forget(job_id)
        self._changed()

    async def _watch_holds(self) -> None:
        """Resume transfers that waited for the battery or a game, once the reason has gone."""
        while True:
            await asyncio.sleep(HOLD_CHECK_SECONDS)
            self.check_holds()

    def check_holds(self) -> list[str]:
        if self.conditions():
            return []
        resumed = []
        for job in list(self.jobs.values()):
            if job.held and job.state == "paused" and job.id not in self.tasks:
                job.held = False
                self._run(job)
                resumed.append(job.id)
        return resumed

    def status(self) -> dict[str, Any]:
        return {
            "jobs": [j.public() for j in sorted(self.jobs.values(), key=lambda j: j.id)],
            "awake": self.guard.held,
            "sleepProblem": self.guard.problem,
            "waitingFor": self.conditions(),
        }

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()
