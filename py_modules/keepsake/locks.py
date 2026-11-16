"""One lock per game across all modules (P19, ADR-0012).

No module writes a game's files, prefix or saves while another holds that
game's lock. The lock records its holder so the UI and health checks can say
who is busy with a game.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class GameLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._holders: dict[str, str] = {}

    def _lock(self, game_key: str) -> asyncio.Lock:
        return self._locks.setdefault(game_key, asyncio.Lock())

    @asynccontextmanager
    async def hold(self, game_key: str, owner: str) -> AsyncIterator[None]:
        lock = self._lock(game_key)
        async with lock:
            self._holders[game_key] = owner
            try:
                yield
            finally:
                self._holders.pop(game_key, None)

    def holder(self, game_key: str) -> str | None:
        return self._holders.get(game_key)

    def held(self) -> dict[str, str]:
        return dict(self._holders)
