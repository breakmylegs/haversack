"""Telling a paired device about games moving between them, over one reused connection (v0.31.0).

Progress goes from the receiving device to the sending one about once a second while a copy
runs. Only the newest message per offer is kept, so a slow link never builds a queue: progress
that a newer message replaced is dropped, and a final one (done, failed, removed) is tried
again a few times. The connection is closed after a short idle spell.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

from ..log import log_event

GAP_SECONDS = 1.0  # between rounds of news to one device
IDLE_SECONDS = 20.0  # an idle connection is closed after this
FINAL_TRIES = 3
RETRY_SECONDS = (2.0, 10.0)


class PeerNews:
    def __init__(
        self,
        connect_for: Callable[[str], Callable[[], Any]],
        gap: float = GAP_SECONDS,
        idle: float = IDLE_SECONDS,
        retry: tuple[float, ...] = RETRY_SECONDS,
    ) -> None:
        self.connect_for = connect_for
        self.gap, self.idle, self.retry = gap, idle, retry
        self.pending: dict[str, dict[str, tuple[dict[str, Any], bool, int]]] = {}
        self.workers: dict[str, asyncio.Task[None]] = {}
        self.sent: list[tuple[str, dict[str, Any]]] = []  # for tests and the export: the last few
        self._wake: dict[str, asyncio.Event] = {}

    def tell(self, peer_id: str, about: str, message: dict[str, Any], final: bool = False) -> None:
        """Queue ``message`` about ``about`` (an offer or a pull) for ``peer_id``. On the event loop."""
        self.pending.setdefault(peer_id, {})[about] = (message, final, 0)
        self._wake.setdefault(peer_id, asyncio.Event()).set()
        worker = self.workers.get(peer_id)
        if worker is None or worker.done():
            self.workers[peer_id] = asyncio.get_running_loop().create_task(self._run(peer_id))

    async def _run(self, peer_id: str) -> None:
        connection = None
        wake = self._wake.setdefault(peer_id, asyncio.Event())
        try:
            while True:
                queue = self.pending.get(peer_id) or {}
                if not queue:
                    wake.clear()
                    try:
                        await asyncio.wait_for(wake.wait(), self.idle)
                    except TimeoutError:
                        return
                    continue
                items, self.pending[peer_id] = list(queue.items()), {}
                for index, (about, (message, final, tries)) in enumerate(items):
                    try:
                        if connection is None:
                            connection = await self.connect_for(peer_id)()
                        await connection.request(message)
                        self.sent = [*self.sent[-19:], (peer_id, message)]
                    except Exception as exc:  # noqa: BLE001 - the other device may be away: news is best effort
                        if connection is not None:
                            with contextlib.suppress(Exception):
                                await connection.close()
                            connection = None
                        log_event(
                            logging.INFO,
                            "replication.news_failed",
                            "Could not tell the other device",
                            error=type(exc).__name__,
                        )
                        pending = self.pending.setdefault(peer_id, {})
                        if final and tries + 1 < FINAL_TRIES and about not in pending:
                            pending[about] = (message, True, tries + 1)  # progress is dropped: newer follows
                        for later, held in items[index + 1 :]:
                            pending.setdefault(later, held)  # the rest of this round waits for the next
                        await asyncio.sleep(self.retry[min(tries, len(self.retry) - 1)])
                        break
                await asyncio.sleep(self.gap)
        finally:
            if connection is not None:
                with contextlib.suppress(Exception):
                    await connection.close()

    async def close(self) -> None:
        for task in self.workers.values():
            task.cancel()
        for task in list(self.workers.values()):
            with contextlib.suppress(BaseException):
                await task
        self.workers.clear()
