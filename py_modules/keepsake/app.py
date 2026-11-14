"""Backend application core.

``main.py`` creates one :class:`KeepsakeApp` and forwards each frontend call to
it. Keeping the logic here means it can be tested without Decky.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from . import diagnostics
from .freeze import Freezer
from .log import log_event, setup_logging, tail
from .paths import PluginPaths
from .procs import find_game_processes
from .settings import SettingsStore

EmitFn = Callable[..., Awaitable[None]]

FREEZE_TEST_MIN = 1
FREEZE_TEST_MAX = 10


async def _no_emit(event: str, *args: Any) -> None:
    return None


class KeepsakeApp:
    def __init__(self, paths: PluginPaths, emit: EmitFn | None = None, proc_root: str = "/proc") -> None:
        self.paths = paths
        self.emit = emit or _no_emit
        self.proc_root = proc_root
        paths.ensure()
        setup_logging(paths.log_dir)
        self.settings = SettingsStore(paths.settings_dir)
        self.freezer = Freezer(paths.runtime_dir, proc_root=proc_root)
        self._freeze_lock = asyncio.Lock()

    async def start(self) -> None:
        # Crash recovery for principle 11: release anything a previous run left frozen.
        if self.freezer.recorded():
            resumed = await asyncio.to_thread(self.freezer.resume_all, "startup")
            log_event(logging.WARNING, "freeze.startup_release", "Released processes left frozen", count=len(resumed))
        log_event(logging.INFO, "app.start", "Keepsake backend started", version=os.environ.get("DECKY_PLUGIN_VERSION"))

    async def stop(self) -> None:
        await asyncio.to_thread(self.freezer.resume_all, "unload")
        log_event(logging.INFO, "app.stop", "Keepsake backend stopped")

    # Settings

    async def get_settings(self) -> dict[str, Any]:
        return self.settings.all()

    async def set_setting(self, key: str, value: Any) -> dict[str, Any]:
        result = self.settings.set(key, value)
        log_event(logging.INFO, "settings.changed", "Setting changed", key=key)
        return result

    # Logs

    async def get_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        return await asyncio.to_thread(tail, self.paths.log_dir, limit)

    # Diagnostics

    async def get_environment(self) -> dict[str, Any]:
        return await asyncio.to_thread(diagnostics.environment)

    async def get_steam_probe(self) -> dict[str, Any]:
        return await asyncio.to_thread(diagnostics.steam)

    async def get_game_processes(self, appid: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(diagnostics.game_processes, int(appid))

    async def https_test(self) -> dict[str, Any]:
        result = await asyncio.to_thread(diagnostics.https_test)
        log_event(logging.INFO, "diagnostics.https_test", "HTTPS test finished", ok=result.get("ok"))
        return result

    async def record_probe_event(self, kind: str, payload: Any) -> int:
        return await asyncio.to_thread(diagnostics.record_probe_event, self.paths.runtime_dir, kind, payload)

    async def export_diagnostics(self, frontend: dict[str, Any] | None = None) -> str:
        path = await asyncio.to_thread(
            diagnostics.export,
            self.paths.settings_dir,
            self.paths.runtime_dir,
            self.paths.log_dir,
            frontend,
            {"freezer": self.freezer.status()},
        )
        log_event(logging.INFO, "diagnostics.export", "Diagnostics exported", file=os.path.basename(path))
        return path

    async def freeze_test(self, appid: int, seconds: int = 5) -> dict[str, Any]:
        """Freeze the running game for a few seconds behind the watchdog."""
        seconds = max(FREEZE_TEST_MIN, min(int(seconds), FREEZE_TEST_MAX))
        if self._freeze_lock.locked():
            return {"ok": False, "reason": "busy"}
        async with self._freeze_lock:
            procs = await asyncio.to_thread(find_game_processes, int(appid), None, self.proc_root)
            if not procs:
                return {"ok": False, "reason": "no-processes"}
            try:
                stopped = await asyncio.to_thread(self.freezer.freeze, procs)
                await asyncio.sleep(seconds)
            finally:
                resumed = await asyncio.to_thread(self.freezer.resume_all, "normal")
            return {"ok": bool(stopped), "stopped": len(stopped), "resumed": len(resumed), "seconds": seconds}
