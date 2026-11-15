"""Backend application core.

``main.py`` creates one :class:`KeepsakeApp` and forwards each frontend call to
it. Keeping the logic here means it can be tested without Decky.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Coroutine
from typing import Any

from . import diagnostics, discovery, net
from .freeze import Freezer
from .jobs import JobTracker
from .log import log_event, setup_logging, tail
from .paths import PluginPaths
from .procs import find_game_processes
from .settings import SettingsStore
from .update import Updater, startup_notice

EmitFn = Callable[..., Coroutine[Any, Any, None]]

FREEZE_TEST_MIN = 1
FREEZE_TEST_MAX = 10
SIMULATED_JOB_MAX = 120
IDLE_EVENT = "keepsake_idle"


async def _no_emit(event: str, *args: Any) -> None:
    return None


class KeepsakeApp:
    def __init__(
        self,
        paths: PluginPaths,
        emit: EmitFn | None = None,
        proc_root: str = "/proc",
        version: str | None = None,
        fetch: net.Fetcher = net.fetch,
        home: str | None = None,
    ) -> None:
        self.paths = paths
        self.home = home
        self._games: dict[str, Any] | None = None
        self.emit = emit or _no_emit
        self.proc_root = proc_root
        self.version = version or os.environ.get("DECKY_PLUGIN_VERSION") or "0.0.0"
        paths.ensure()
        setup_logging(paths.log_dir)
        self.settings = SettingsStore(paths.settings_dir)
        self.freezer = Freezer(paths.runtime_dir, proc_root=proc_root)
        self.jobs = JobTracker(on_idle=self._on_idle)
        self.updater = Updater(paths.runtime_dir, self.version, fetch)
        self._freeze_lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._notice: dict[str, Any] | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        # Crash recovery for principle 11: release anything a previous run left frozen.
        if self.freezer.recorded():
            resumed = await asyncio.to_thread(self.freezer.resume_all, "startup")
            log_event(logging.WARNING, "freeze.startup_release", "Released processes left frozen", count=len(resumed))
        self._notice = await asyncio.to_thread(startup_notice, self.paths.runtime_dir, self.version)
        if self._notice:
            log_event(logging.INFO, "update.applied", "Running a new version", **self._notice)
        if self.settings.read_only:
            log_event(logging.WARNING, "settings.safe_mode", "Settings were written by a newer version; read-only")
        log_event(logging.INFO, "app.start", "Keepsake backend started", version=self.version)

    def _on_idle(self) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(lambda: loop.create_task(self.emit(IDLE_EVENT)))

    # Status and updates

    async def get_status(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "safeMode": self.settings.read_only,
            "busy": self.jobs.busy_reason(),
        }

    async def take_startup_notice(self) -> dict[str, Any] | None:
        notice, self._notice = self._notice, None
        return notice

    async def check_for_updates(self, force: bool = False) -> dict[str, Any]:
        async with self._update_lock:
            channel = str(self.settings.get("updateChannel"))
            result = await asyncio.to_thread(self.updater.check, channel, bool(force))
        if result.get("error"):
            log_event(logging.INFO, "update.check_failed", "Update check failed quietly", error=result["error"])
        return result

    async def prepare_update(self, tag: str) -> dict[str, Any]:
        """Verify a release and return the arguments for Decky's installer."""
        async with self._update_lock:
            result = await asyncio.to_thread(self.updater.prepare, str(tag), self.jobs.busy_reason())
        log_event(
            logging.INFO,
            "update.prepare",
            "Prepared update hand-off",
            tag=tag,
            ok=result.get("ok"),
            reason=result.get("reason"),
        )
        return result

    # Discovery

    async def discover_games(self, refresh: bool = False) -> dict[str, Any]:
        """Scan Steam on this device. Cached until ``refresh``."""
        if self._games is None or refresh:
            self._games = await asyncio.to_thread(discovery.discover, self.home)
            counts: dict[str, int] = {}
            for game in self._games["games"]:
                counts[game["kind"]] = counts.get(game["kind"], 0) + 1
            log_event(logging.INFO, "discovery.scan", "Scanned games", roots=len(self._games["roots"]), **counts)
        mismatches = await asyncio.to_thread(discovery.load_mismatches, self.paths.runtime_dir)
        return {**self._games, "mismatches": mismatches}

    async def check_running_prefix(self, key: str) -> dict[str, Any]:
        """Cross-check a running game's ``STEAM_COMPAT_DATA_PATH`` with its discovered prefix."""
        games = (await self.discover_games())["games"]
        game = next((g for g in games if g["key"] == key), None)
        if game is None:
            return {"status": "unknown", "reason": "unknown-game"}
        procs = await asyncio.to_thread(find_game_processes, int(game["appid"]), game["prefix"], self.proc_root)
        observed = [p.env["STEAM_COMPAT_DATA_PATH"] for p in procs if p.env.get("STEAM_COMPAT_DATA_PATH")]
        result = discovery.cross_check(game["prefix"], observed)
        await asyncio.to_thread(discovery.record_cross_check, self.paths.runtime_dir, key, result, game["prefix"])
        if result["status"] == "mismatch":
            log_event(
                logging.WARNING,
                "discovery.prefix_mismatch",
                "Running prefix differs; sync blocked",
                key=key,
                reason=result.get("reason"),
            )
        return result

    async def simulate_sync_job(self, seconds: int = 30) -> dict[str, Any]:
        """Diagnostics only: hold a fake sync job so the update guard can be tested."""
        seconds = max(1, min(int(seconds), SIMULATED_JOB_MAX))
        with self.jobs.job("simulated"):
            log_event(logging.INFO, "jobs.simulated", "Simulated sync job started", seconds=seconds)
            await asyncio.sleep(seconds)
        return {"ok": True, "seconds": seconds}

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
