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

from . import diagnostics, discovery, manifest, net, resolve, restore
from .engine import SnapshotEngine
from .freeze import Freezer
from .fsutil import atomic_write_json, read_json
from .gameconfig import GameConfigStore, custom_path_from_absolute
from .jobs import JobTracker
from .log import log_event, setup_logging, tail
from .paths import PluginPaths
from .procs import find_game_processes
from .settings import SettingsStore
from .store import LocalFolderStore
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
        download: manifest.Downloader = net.fetch_to_file,
        auto_refresh_manifest: bool = True,
    ) -> None:
        self.paths = paths
        self.home = home
        self._games: dict[str, Any] | None = None
        self.manifest = manifest.ManifestStore(paths.runtime_dir, download=download)
        self.game_configs = GameConfigStore(paths.settings_dir)
        self._auto_refresh_manifest = auto_refresh_manifest
        self._manifest_lock = asyncio.Lock()
        self._background: list[asyncio.Task[Any]] = []
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
        # Principle 3: finish or undo any restore a crash interrupted, before anything else touches saves.
        try:
            for outcome in await asyncio.to_thread(restore.recover, self.paths.runtime_dir):
                log_event(logging.WARNING, "restore.recovered", "Recovered an interrupted restore", **outcome)
        except restore.RestoreError as exc:
            log_event(logging.ERROR, "restore.recover_failed", str(exc))
        self._notice = await asyncio.to_thread(startup_notice, self.paths.runtime_dir, self.version)
        if self._notice:
            log_event(logging.INFO, "update.applied", "Running a new version", **self._notice)
        if self.settings.read_only:
            log_event(logging.WARNING, "settings.safe_mode", "Settings were written by a newer version; read-only")
        log_event(logging.INFO, "app.start", "Keepsake backend started", version=self.version)
        if self._auto_refresh_manifest:
            # Weekly refresh in the background; never blocks start-up.
            self._background.append(asyncio.create_task(self.refresh_manifest(False)))

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

    # Manifest, matching and preview

    async def manifest_status(self) -> dict[str, Any]:
        return await asyncio.to_thread(self.manifest.status)

    async def refresh_manifest(self, force: bool = False) -> dict[str, Any]:
        if self._manifest_lock.locked():
            return {"ok": False, "reason": "busy"}
        async with self._manifest_lock:
            result = await asyncio.to_thread(self.manifest.refresh, bool(force))
        log_event(
            logging.INFO,
            "manifest.refresh",
            "Manifest refresh finished",
            **{
                k: v
                for k, v in result.items()
                if k in ("ok", "changed", "reason", "games", "parseSeconds", "peakRssMb")
            },
        )
        return result

    async def _game(self, key: str) -> dict[str, Any]:
        games = (await self.discover_games())["games"]
        game = next((g for g in games if g["key"] == key), None)
        if game is None:
            raise ValueError("unknown game; rescan the games list")
        return dict(game)

    async def match_games(self) -> list[dict[str, Any]]:
        """Every discovered game with its manifest match."""
        games = (await self.discover_games())["games"]
        index = await asyncio.to_thread(self.manifest.load)
        out = []
        for game in games:
            config = self.game_configs.get(game["key"])
            match = manifest.match_game(index, game, config)
            out.append({"key": game["key"], "name": game["name"], "kind": game["kind"], **match})
        return out

    async def search_titles(self, query: str) -> list[str]:
        index = await asyncio.to_thread(self.manifest.load)
        return manifest.search_titles(index, str(query)[:200]) if index else []

    async def get_game(self, key: str) -> dict[str, Any]:
        game = await self._game(key)
        config = self.game_configs.get(key)
        index = await asyncio.to_thread(self.manifest.load)
        return {"game": game, "config": config, "match": manifest.match_game(index, game, config)}

    async def update_game_config(self, key: str, changes: dict[str, Any]) -> dict[str, Any]:
        await self._game(key)
        if "matchTitle" in changes and changes["matchTitle"] is not None:
            index = await asyncio.to_thread(self.manifest.load)
            if not index or changes["matchTitle"] not in index.get("games", {}):
                raise ValueError("that title is not in the manifest")
        config = await asyncio.to_thread(self.game_configs.update, key, dict(changes))
        log_event(logging.INFO, "game.config", "Game settings changed", key=key, fields=sorted(changes))
        return config

    async def add_custom_path(self, key: str, absolute_path: str) -> dict[str, Any]:
        """Add a folder chosen in the file picker, as a path relative to one of the game's roots."""
        game = await self._game(key)
        entry = custom_path_from_absolute(str(absolute_path), resolve.logical_roots(game, home=self.home))
        config = self.game_configs.get(key)
        return await self.update_game_config(key, {"customPaths": [*config["customPaths"], entry]})

    async def preview_game(self, key: str) -> dict[str, Any]:
        game = await self._game(key)
        config = self.game_configs.get(key)
        index = await asyncio.to_thread(self.manifest.load)
        match = manifest.match_game(index, game, config)
        title = match.get("title")
        record = index["games"].get(title) if index and title else None
        result = await asyncio.to_thread(resolve.preview, game, title, record, config, self.home)
        return {**result, "match": match, "gameKey": match.get("gameKey")}

    # Snapshots against the local test store (slice 5; slice 6 adds the cloud store)

    def _engine(self) -> SnapshotEngine:
        settings = self.settings.all()
        return SnapshotEngine(
            LocalFolderStore(os.path.join(self.paths.runtime_dir, "local-test-store")),
            self.paths.runtime_dir,
            self.paths.settings_dir,
            device_id=str(settings["deviceId"]),
            device_name=str(settings["deviceName"] or "Unnamed device"),
            plugin_version=self.version,
            settings=self.settings.all,
        )

    def _bases(self) -> dict[str, str]:
        data = read_json(os.path.join(self.paths.runtime_dir, "snapshot-bases.json"), default={})
        return data if isinstance(data, dict) else {}

    def _set_base(self, game_key: str, snap_id: str) -> None:
        bases = self._bases()
        bases[game_key] = snap_id
        atomic_write_json(os.path.join(self.paths.runtime_dir, "snapshot-bases.json"), bases)

    async def _snapshot_context(self, key: str) -> dict[str, Any]:
        """Everything needed to snapshot or restore a game, failing closed when anything is uncertain."""
        if self.settings.read_only:
            raise ValueError("settings are in read-only safe mode; update Keepsake first")
        game = await self._game(key)
        if discovery.sync_blocked(self.paths.runtime_dir, key):
            raise ValueError("the running prefix did not match; snapshots are blocked for this game")
        config = self.game_configs.get(key)
        index = await asyncio.to_thread(self.manifest.load)
        match = manifest.match_game(index, game, config)
        if not match.get("gameKey") or not index:
            raise ValueError("match the game to a manifest entry first")
        record = index["games"].get(match["title"])
        scan = await asyncio.to_thread(resolve.preview, game, match["title"], record, config, self.home, 0, True)
        if scan.get("truncated"):
            raise ValueError("too many files to snapshot safely; add exclusions")
        roots = resolve.logical_roots(game, home=self.home)
        procs = await asyncio.to_thread(find_game_processes, int(game["appid"]), game.get("prefix"), self.proc_root)
        return {
            "game": game,
            "gameKey": match["gameKey"],
            "files": scan.get("files", {}),
            "roots": roots,
            "running": bool(procs),
        }

    async def snapshot_game(self, key: str) -> dict[str, Any]:
        ctx = await self._snapshot_context(key)
        eng = self._engine()
        with self.jobs.job("snapshot"):
            base_id = self._bases().get(ctx["gameKey"])
            base = await asyncio.to_thread(eng.get_meta, ctx["gameKey"], base_id) if base_id else None
            result = await asyncio.to_thread(eng.take, ctx["gameKey"], ctx["files"], ctx["roots"], "manual", base)
        if result["status"] == "published":
            self._set_base(ctx["gameKey"], result["snapId"])
        log_event(logging.INFO, "snapshot.take", "Snapshot taken", gameKey=ctx["gameKey"], status=result["status"])
        result.pop("meta", None)
        return result

    async def list_snapshots(self, key: str) -> dict[str, Any]:
        game = await self._game(key)
        index = await asyncio.to_thread(self.manifest.load)
        match = manifest.match_game(index, game, self.game_configs.get(key))
        game_key = match.get("gameKey")
        if not game_key:
            return {"snapshots": [], "quarantine": [], "prerestore": []}
        eng = self._engine()
        metas = await asyncio.to_thread(eng.list_metas, game_key)
        pruned = await asyncio.to_thread(eng.pruned, game_key)
        pins = {p["snapId"] for p in await asyncio.to_thread(eng.pins, game_key)}
        base = self._bases().get(game_key)

        def summary(meta: dict[str, Any]) -> dict[str, Any]:
            return {
                "snapId": meta["snapId"],
                "created": meta["created"],
                "kind": meta["kind"],
                "device": meta.get("deviceName"),
                "files": len(meta["files"]),
                "bytes": sum(f["size"] for f in meta["files"]),
            }

        return {
            "gameKey": game_key,
            "snapshots": [
                {
                    **summary(m),
                    "pinned": m["snapId"] in pins,
                    "pruned": m["snapId"] in pruned,
                    "base": m["snapId"] == base,
                }
                for m in reversed(metas)
            ],
            "quarantine": [
                {**summary(r["meta"]), "reasons": r.get("reasons", [])} for r in eng.quarantine.list(game_key)
            ],
            "prerestore": [summary(r["meta"]) for r in eng.prerestore.list(game_key)],
        }

    async def restore_snapshot(self, key: str, snap_id: str) -> dict[str, Any]:
        ctx = await self._snapshot_context(key)
        eng = self._engine()
        with self.jobs.job("restore"):
            result = await asyncio.to_thread(
                eng.restore, ctx["gameKey"], str(snap_id), ctx["files"], ctx["roots"], ctx["running"]
            )
        self._set_base(ctx["gameKey"], str(snap_id))
        log_event(
            logging.INFO, "snapshot.restore", "Snapshot restored", gameKey=ctx["gameKey"], status=result["status"]
        )
        return result

    async def undo_restore(self, key: str, prerestore_id: str) -> dict[str, Any]:
        ctx = await self._snapshot_context(key)
        eng = self._engine()
        with self.jobs.job("restore"):
            result = await asyncio.to_thread(
                eng.restore_prerestore, ctx["gameKey"], str(prerestore_id), ctx["files"], ctx["roots"], ctx["running"]
            )
        log_event(logging.INFO, "snapshot.undo", "Restore undone", gameKey=ctx["gameKey"], status=result["status"])
        return result

    async def pin_snapshot(self, key: str, snap_id: str) -> dict[str, Any]:
        game_key = (await self._snapshot_context(key))["gameKey"]
        await asyncio.to_thread(self._engine().pin, game_key, str(snap_id))
        return {"ok": True}

    async def release_quarantine(self, key: str, snap_id: str, confirmed: bool) -> dict[str, Any]:
        game_key = (await self._snapshot_context(key))["gameKey"]
        with self.jobs.job("snapshot"):
            result = await asyncio.to_thread(
                self._engine().release_quarantined, game_key, str(snap_id), bool(confirmed)
            )
        if result["status"] == "published":
            self._set_base(game_key, str(snap_id))
        log_event(
            logging.WARNING,
            "snapshot.release",
            "Quarantined snapshot released",
            gameKey=game_key,
            status=result["status"],
        )
        return result

    async def run_retention(self, key: str) -> dict[str, Any]:
        game_key = (await self._snapshot_context(key))["gameKey"]
        with self.jobs.job("retention"):
            result = await asyncio.to_thread(self._engine().apply_retention, game_key, set(self._bases().values()))
        log_event(
            logging.INFO, "snapshot.retention", "Retention applied", gameKey=game_key, pruned=len(result["prune"])
        )
        return {"pruned": result["prune"], "kept": len(result["keep"]), "orphansDeleted": result["orphansDeleted"]}

    async def simulate_sync_job(self, seconds: int = 30) -> dict[str, Any]:
        """Diagnostics only: hold a fake sync job so the update guard can be tested."""
        seconds = max(1, min(int(seconds), SIMULATED_JOB_MAX))
        with self.jobs.job("simulated"):
            log_event(logging.INFO, "jobs.simulated", "Simulated sync job started", seconds=seconds)
            await asyncio.sleep(seconds)
        return {"ok": True, "seconds": seconds}

    async def stop(self) -> None:
        for task in self._background:
            task.cancel()
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
            {"freezer": self.freezer.status(), "manifest": self.manifest.status()},
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
