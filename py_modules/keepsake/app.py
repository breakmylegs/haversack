"""Backend application core.

``main.py`` creates one :class:`KeepsakeApp` and forwards each frontend call to
it. Keeping the logic here means it can be tested without Decky.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable, Coroutine
from typing import Any

from . import diagnostics, discovery, identity, lifecycle, manifest, net, resolve, restore
from .auth import AuthError, DeviceCodeFlow, TokenManager, TokenStore
from .engine import SnapshotEngine
from .freeze import Freezer
from .fsutil import atomic_write_json, read_json
from .gameconfig import GameConfigStore, custom_path_from_absolute
from .jobs import JobTracker
from .log import log_event, setup_logging, tail
from .paths import PluginPaths
from .procs import find_game_processes
from .settings import SettingsStore
from .snapshot import SnapshotError
from .store import AlreadyExistsError, LocalFolderStore, Store, StoreError
from .store.graph import GraphStore
from .sync import GameContext, SyncEngine
from .update import Updater, startup_notice

EmitFn = Callable[..., Coroutine[Any, Any, None]]
IDLE_INTERVAL_SECONDS = 30 * 60
IDENTITY_CACHE_SECONDS = 600
UNRESOLVED_METHODS = ("none", "ambiguous", "no-save-data", "no-manifest")

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
        transport: net.Transport = net.request,
        graph_base_url: str | None = None,
    ) -> None:
        self._graph_base_url = graph_base_url
        self.paths = paths
        self.home = home
        self._games: dict[str, Any] | None = None
        self.manifest = manifest.ManifestStore(paths.runtime_dir, download=download)
        self.game_configs = GameConfigStore(paths.settings_dir)
        self._auto_refresh_manifest = auto_refresh_manifest
        self._manifest_lock = asyncio.Lock()
        self._background: list[asyncio.Task[Any]] = []
        self.token_store = TokenStore(paths.settings_dir)
        self.tokens = TokenManager(
            self.token_store, lambda: str(self.settings.get("onedriveClientId")), transport=transport
        )
        self._transport = transport
        self._signin: DeviceCodeFlow | None = None
        self._launching: set[str] = set()
        self._identity_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._auth_lock = asyncio.Lock()
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
            # Idle sync, whose first pass (a minute after start) also recovers missed exit pushes.
            self._background.append(asyncio.create_task(self._idle_loop()))

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
        """Every discovered game with its match, applying strong cross-device matches (ADR-0011)."""
        games = (await self.discover_games())["games"]
        index = await asyncio.to_thread(self.manifest.load)
        out = []
        for game in games:
            config = self.game_configs.get(game["key"])
            match = manifest.match_game(index, game, config)
            proposal = None
            if match["method"] in UNRESOLVED_METHODS and game["kind"] == "shortcut":
                applied = await self._apply_identity_match(game, games, index)
                if applied:
                    match = manifest.match_game(index, game, self.game_configs.get(game["key"]))
                else:
                    proposal = self._proposals().get("open", {}).get(game["key"])
            elif game["key"] in self._proposals().get("open", {}):
                self._clear_proposal(game["key"])  # resolved some other way
            out.append({"key": game["key"], "name": game["name"], "kind": game["kind"], **match, "proposal": proposal})
        return out

    # Match proposals: likely but uncertain matches wait for the user's approval.

    def _proposals_path(self) -> str:
        return os.path.join(self.paths.runtime_dir, "match-proposals.json")

    def _proposals(self) -> dict[str, Any]:
        data = read_json(self._proposals_path(), default={})
        return data if isinstance(data, dict) else {}

    def _save_proposals(self, data: dict[str, Any]) -> None:
        atomic_write_json(self._proposals_path(), data)

    def _clear_proposal(self, key: str) -> None:
        data = self._proposals()
        data.setdefault("open", {}).pop(key, None)
        self._save_proposals(data)

    async def _raise_proposal(self, game: dict[str, Any], found: dict[str, Any]) -> None:
        data = self._proposals()
        open_proposals = data.setdefault("open", {})
        previous = open_proposals.get(game["key"], {})
        is_new = previous.get("candidate", {}).get("gameKey") != found["candidate"]["gameKey"]
        open_proposals[game["key"]] = {
            **found,
            "raised": previous.get("raised", time.time()) if not is_new else time.time(),
        }
        self._save_proposals(data)
        if is_new:
            label = found["candidate"].get("title") or found["candidate"]["gameKey"]
            await self.emit(
                "keepsake_toast",
                f"{game['name']} looks like {label}. Open Keepsake to approve or choose another match.",
            )
            log_event(
                logging.INFO,
                "identity.proposed",
                "Proposed a match for approval",
                gameKey=found["candidate"]["gameKey"],
                score=found["candidate"]["score"],
            )

    async def approve_match(self, key: str) -> dict[str, Any]:
        """Accept the proposed match."""
        found = self._proposals().get("open", {}).get(key)
        if not found:
            raise ValueError("there is no match waiting for approval")
        candidate = found["candidate"]
        index = await asyncio.to_thread(self.manifest.load)
        title = candidate.get("title") if index and candidate.get("title") in index.get("games", {}) else None
        config = await self.set_game_key(key, candidate["gameKey"], title)
        self._clear_proposal(key)
        return config

    async def reject_match(self, key: str) -> dict[str, Any]:
        """'Not this game': never propose this candidate for this game again."""
        data = self._proposals()
        found = data.setdefault("open", {}).pop(key, None)
        if found:
            rejected = data.setdefault("rejected", {}).setdefault(key, [])
            if found["candidate"]["gameKey"] not in rejected:
                rejected.append(found["candidate"]["gameKey"])
        self._save_proposals(data)
        return {"ok": True}

    async def _identities(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._identity_cache and now - self._identity_cache[0] < IDENTITY_CACHE_SECONDS:
            return self._identity_cache[1]
        try:
            records = await asyncio.to_thread(identity.cloud_identities, self._store())
        except StoreError:
            records = []  # offline or signed out: match with the manifest only
        self._identity_cache = (now, records)
        return records

    async def identity_candidates(self, game: dict[str, Any], index: dict[str, Any] | None) -> list[dict[str, Any]]:
        roots = resolve.logical_roots(game, home=self.home)
        proton = resolve.platform_of(game) == "proton"
        probe = identity.probe_for(roots, lambda root: proton and root in resolve.WIN_ROOTS, resolve.expand)
        records = await self._identities()
        device_id = str(self.settings.get("deviceId"))
        return await asyncio.to_thread(
            identity.candidates, identity.local_hints(game), index, records, probe, device_id
        )

    def _taken_keys(self, games: list[dict[str, Any]], index: dict[str, Any] | None, except_key: str) -> set[str]:
        taken = set()
        for other in games:
            if other["key"] != except_key:
                key = manifest.match_game(index, other, self.game_configs.get(other["key"])).get("gameKey")
                if key:
                    taken.add(key)
        return taken

    async def _apply_identity_match(
        self, game: dict[str, Any], games: list[dict[str, Any]], index: dict[str, Any] | None
    ) -> bool:
        ranked = await self.identity_candidates(game, index)
        taken = self._taken_keys(games, index, game["key"])
        choice = identity.automatic_choice(ranked, taken)
        if choice is None:
            # Not certain: if a match is likely, ask the user instead of guessing.
            rejected = set(self._proposals().get("rejected", {}).get(game["key"], []))
            found = identity.proposal(ranked, taken, rejected)
            if found:
                await self._raise_proposal(game, found)
            elif game["key"] in self._proposals().get("open", {}):
                self._clear_proposal(game["key"])
            return False
        changes: dict[str, Any] = {"gameKey": choice["gameKey"], "gameKeySource": "auto"}
        if choice.get("title") and index and choice["title"] in index.get("games", {}):
            changes["matchTitle"] = choice["title"]
        await asyncio.to_thread(self.game_configs.update, game["key"], changes)
        log_event(
            logging.INFO,
            "identity.auto_match",
            "Matched a game to another device's copy",
            gameKey=choice["gameKey"],
            signals=choice["signals"],
            score=choice["score"],
        )
        return True

    async def set_game_key(self, key: str, game_key_value: str | None, title: str | None = None) -> dict[str, Any]:
        """Use a suggested or new game key (or clear it). Chosen by the user, so any proposal is settled."""
        changes: dict[str, Any] = {"gameKey": game_key_value, "gameKeySource": "user" if game_key_value else None}
        if title is not None:
            changes["matchTitle"] = title
        config = await self.update_game_config(key, changes)
        if game_key_value:
            self._clear_proposal(key)
        return config

    async def new_game_key(self, key: str) -> dict[str, Any]:
        """Give a game the manifest does not know its own key, from its name."""
        game = await self._game(key)
        return await self.set_game_key(key, manifest.game_key(str(game["name"])))

    async def search_titles(self, query: str) -> list[str]:
        index = await asyncio.to_thread(self.manifest.load)
        return manifest.search_titles(index, str(query)[:200]) if index else []

    async def get_game(self, key: str) -> dict[str, Any]:
        game = await self._game(key)
        config = self.game_configs.get(key)
        index = await asyncio.to_thread(self.manifest.load)
        match = manifest.match_game(index, game, config)
        suggestions: list[dict[str, Any]] = []
        if game["kind"] == "shortcut" and (
            match["method"] in UNRESOLVED_METHODS or config.get("gameKeySource") == "auto"
        ):
            suggestions = [c for c in await self.identity_candidates(game, index) if c["score"] >= 3][:5]
        proposal = self._proposals().get("open", {}).get(key)
        return {"game": game, "config": config, "match": match, "suggestions": suggestions, "proposal": proposal}

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

    # OneDrive sign-in (slice 6)

    async def cloud_status(self) -> dict[str, Any]:
        return {
            "clientIdSet": bool(self.settings.get("onedriveClientId")),
            "signedIn": await asyncio.to_thread(self.tokens.signed_in),
            "signingIn": self._signin is not None,
            "problem": self.tokens.last_error,
            "store": self.settings.get("snapshotStore"),
        }

    async def start_signin(self) -> dict[str, Any]:
        """Begin the device code flow. Only ever called from a user action (threat model T2)."""
        async with self._auth_lock:
            if self._signin is not None:
                self._signin.cancelled.set()
            flow = DeviceCodeFlow(
                str(self.settings.get("onedriveClientId")), self.token_store, transport=self._transport
            )
            shown = await asyncio.to_thread(flow.start)
            self._signin = flow
        log_event(logging.INFO, "auth.signin_started", "OneDrive sign-in started")
        self._background.append(asyncio.create_task(self._finish_signin(flow)))
        return shown

    async def _finish_signin(self, flow: DeviceCodeFlow) -> None:
        try:
            await asyncio.to_thread(flow.poll)
        except AuthError as exc:
            if self._signin is flow:
                self._signin = None
            log_event(logging.WARNING, "auth.signin_failed", "OneDrive sign-in did not complete", reason=exc.reason)
            await self.emit("keepsake_signin", {"status": "failed", "reason": exc.reason})
            return
        if self._signin is flow:
            self._signin = None
        self.tokens.last_error = None
        log_event(logging.INFO, "auth.signed_in", "Signed in to OneDrive")
        registered = await self.register_device()
        await self.emit("keepsake_signin", {"status": "signed-in", "registered": registered})

    async def cancel_signin(self) -> dict[str, Any]:
        if self._signin is not None:
            self._signin.cancelled.set()
            self._signin = None
        return {"ok": True}

    async def sign_out(self) -> dict[str, Any]:
        await self.cancel_signin()
        await asyncio.to_thread(self.token_store.clear)
        log_event(logging.INFO, "auth.signed_out", "Signed out of OneDrive")
        return {"ok": True}

    def _graph(self) -> GraphStore:
        if self._graph_base_url:  # tests point this at a fake Graph
            return GraphStore(self.tokens, transport=self._transport, base_url=self._graph_base_url)
        return GraphStore(self.tokens, transport=self._transport)

    async def test_cloud(self) -> dict[str, Any]:
        try:
            folder = await asyncio.to_thread(self._graph().check)
        except StoreError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "folder": folder.get("name")}

    async def register_device(self) -> bool:
        """Write this device's registry entry once (``registry/devices/<deviceId>.json``)."""
        settings = self.settings.all()
        entry = {
            "schemaVersion": 1,
            "deviceId": settings["deviceId"],
            "deviceName": settings["deviceName"],
            "registered": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pluginVersion": self.version,
        }
        key = f"registry/devices/{settings['deviceId']}.json"
        try:
            await asyncio.to_thread(self._graph().put_new, key, json.dumps(entry, sort_keys=True).encode())
        except AlreadyExistsError:
            return True
        except StoreError as exc:
            log_event(logging.WARNING, "registry.failed", "Could not register this device", error=str(exc))
            return False
        return True

    # Snapshots against the local test store or OneDrive

    def _store(self) -> Store:
        if self.settings.get("snapshotStore") == "onedrive":
            return self._graph()
        return LocalFolderStore(os.path.join(self.paths.runtime_dir, "local-test-store"))

    def _engine(self) -> SnapshotEngine:
        settings = self.settings.all()
        return SnapshotEngine(
            self._store(),
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
        if not match.get("gameKey"):
            raise ValueError("match the game to a manifest entry or give it a game key first")
        record = index["games"].get(match["title"]) if index and match.get("title") else None
        if record is None and not config.get("customPaths"):
            raise ValueError("no save folders are known for this game: match it or add custom folders")
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

    # Sync (slice 7). Slice 8 calls pull and push from the launch gate and the exit event.

    def _sync(self) -> SyncEngine:
        return SyncEngine(self._engine(), self.paths.runtime_dir)

    async def _sync_context(self, key: str, running: Callable[[], bool] | None = None) -> GameContext:
        ctx = await self._snapshot_context(key)  # fails closed on mismatch, safe mode, no match
        game = ctx["game"]
        config = self.game_configs.get(key)
        index = self.manifest.load() or {}
        match = manifest.match_game(index, game, config)
        record = index.get("games", {}).get(match["title"]) if match.get("title") else None

        def files() -> dict[str, list[str]]:
            scan = resolve.preview(game, match["title"], record, config, self.home, 0, True)
            if scan.get("truncated"):
                raise SnapshotError("too many files to sync safely; add exclusions")
            return dict(scan.get("files", {}))

        def processes_running() -> bool:
            return bool(find_game_processes(int(game["appid"]), game.get("prefix"), self.proc_root))

        def identity_record() -> dict[str, Any]:
            return identity.identity_record(
                ctx["gameKey"],
                str(self.settings.get("deviceId")),
                match.get("title"),
                identity.local_hints(game),
                identity.save_dirs(files()),
            )

        return GameContext(
            ctx["gameKey"],
            files=files,
            roots=ctx["roots"],
            running=running or processes_running,
            identity=identity_record,
        )

    # Lifecycle (slice 8): launch gate and exit push

    def _sessions(self) -> dict[str, Any]:
        data = read_json(os.path.join(self.paths.runtime_dir, "sessions.json"), default={})
        return data if isinstance(data, dict) else {}

    def _record_session(self, game_key: str, **changes: float) -> None:
        sessions = self._sessions()
        sessions[game_key] = {**sessions.get(game_key, {}), **changes}
        atomic_write_json(os.path.join(self.paths.runtime_dir, "sessions.json"), sessions)

    async def _games_for_appid(self, raw_id: Any) -> list[dict[str, Any]]:
        appid = lifecycle.normalise_appid(raw_id)
        games = (await self.discover_games())["games"]
        return [g for g in games if g["appid"] == appid and self.game_configs.get(g["key"]).get("enabled")]

    async def on_game_event(self, kind: str, raw_id: Any) -> dict[str, Any]:
        """Frontend lifetime events. Returns at once; the work runs as a task."""
        try:
            games = await self._games_for_appid(raw_id)
        except (ValueError, TypeError):
            return {"handled": 0}
        for game in games:
            if kind == "start" and game["key"] not in self._launching:
                self._launching.add(game["key"])
                self._background.append(asyncio.create_task(self._launch(game)))
            elif kind == "exit":
                self._background.append(asyncio.create_task(self._exit(game)))
        return {"handled": len(games)}

    async def _launch(self, game: dict[str, Any]) -> dict[str, Any]:
        key = game["key"]
        mode = self.game_configs.get(key).get("launchGate", "freeze")
        timeout = float(self.settings.get("launchPullTimeout"))
        abort = lifecycle.Abort()
        frozen = False
        token: str | None = None
        try:
            ctx_probe = await self._sync_context(key)
            self._record_session(ctx_probe.game_key, lastStart=time.time())
            gate_files = lifecycle.GateFiles(self.paths.runtime_dir)
            if mode == "strict":
                await asyncio.to_thread(gate_files.write_timeout, int(timeout))
                found = await asyncio.to_thread(
                    lifecycle.wait_for,
                    lambda: gate_files.waiting_token(game["appid"]) is not None,
                    lifecycle.FIND_PROCESS_SECONDS,
                )
                token = gate_files.waiting_token(game["appid"]) if found else None
            procs = []
            if token is None and mode != "off":
                procs = await asyncio.to_thread(self._wait_for_processes, game)
                if procs:
                    stopped = await asyncio.to_thread(self.freezer.freeze, procs)
                    frozen = bool(stopped)
            if token is not None or frozen:
                # Blocked in the gate script or frozen: safe to restore until the pull is abandoned.
                running: Callable[[], bool] = abort.is_set
            else:
                running = lambda: True  # noqa: E731 - could not hold the game: never restore under it
            ctx = await self._sync_context(key, running=running)
            with self.jobs.job("sync"):
                try:
                    result = await asyncio.wait_for(asyncio.to_thread(self._sync().pull, ctx), timeout)
                except TimeoutError:
                    abort.set()
                    self._sync().state.update(ctx.game_key, pending=True)
                    await self.emit("keepsake_toast", lifecycle.TOAST_TIMEOUT)
                    result = {"action": "launch", "pending": True, "reason": "timeout"}
            await self._announce_pull(game, result)
            log_event(
                logging.INFO,
                "lifecycle.launch",
                "Launch check finished",
                gameKey=ctx.game_key,
                mode=mode,
                frozen=frozen,
                strict=token is not None,
                action=result.get("action"),
                reason=result.get("reason"),
            )
            return result
        except (ValueError, SnapshotError, StoreError) as exc:
            log_event(logging.WARNING, "lifecycle.launch_skipped", "Launch check skipped", key=key, error=str(exc))
            return {"action": "launch", "error": str(exc)}
        finally:
            if frozen:
                await asyncio.to_thread(self.freezer.resume_all, "normal")
            if token is not None:
                await asyncio.to_thread(lifecycle.GateFiles(self.paths.runtime_dir).release, game["appid"], token)
            self._launching.discard(key)

    def _wait_for_processes(self, game: dict[str, Any]) -> list[Any]:
        found: list[Any] = []

        def check() -> bool:
            nonlocal found
            found = find_game_processes(int(game["appid"]), game.get("prefix"), self.proc_root)
            return bool(found)

        lifecycle.wait_for(check, lifecycle.FIND_PROCESS_SECONDS)
        return found

    async def _announce_pull(self, game: dict[str, Any], result: dict[str, Any]) -> None:
        if result.get("action") == "conflict":
            await self.emit("keepsake_toast", f"Save conflict for {game['name']}. Open Keepsake to choose.")
        elif result.get("reason") == "cloud-newer-game-running":
            await self.emit("keepsake_toast", lifecycle.TOAST_CLOUD_NEWER)

    async def _exit(self, game: dict[str, Any]) -> dict[str, Any]:
        key = game["key"]
        try:
            gone = await asyncio.to_thread(
                lifecycle.wait_for,
                lambda: not find_game_processes(int(game["appid"]), game.get("prefix"), self.proc_root),
                lifecycle.EXIT_WAIT_SECONDS,
            )
            if not gone:
                log_event(
                    logging.WARNING, "lifecycle.exit_waiting", "Game still running; the idle pass will save it", key=key
                )
                return {"status": "deferred"}
            ctx = await self._sync_context(key)
            with self.jobs.job("sync"):
                result = await asyncio.to_thread(self._sync().push, ctx)
            self._record_session(ctx.game_key, lastEnd=time.time())
        except (ValueError, SnapshotError, StoreError) as exc:
            log_event(logging.WARNING, "lifecycle.exit_failed", "Exit save failed", key=key, error=str(exc))
            return {"status": "error", "error": str(exc)}
        status = result.get("status")
        if status == "published" and self.settings.get("toastOnSync"):
            await self.emit("keepsake_toast", f"Saved {game['name']} to the cloud.")
        elif status == "published-fork":
            await self.emit("keepsake_toast", f"Save conflict for {game['name']}. Open Keepsake to choose.")
        elif status == "quarantined":
            await self.emit(
                "keepsake_toast", f"{game['name']}: a suspicious save was kept on this device, not uploaded."
            )
        log_event(logging.INFO, "lifecycle.exit", "Exit save finished", key=key, status=status)
        return result

    # Strict wrapper: the frontend reads and writes launch options; the backend keeps the originals.

    async def strict_wrap(self, key: str, current_options: str) -> dict[str, Any]:
        game = await self._game(key)
        store = lifecycle.LaunchOptionsStore(self.paths.runtime_dir)
        await asyncio.to_thread(store.save_original, game["appid"], str(current_options))
        await self.update_game_config(key, {"launchGate": "strict"})
        return {
            "appid": game["appid"],
            "options": lifecycle.wrap_launch_options(str(current_options), self.paths.plugin_dir),
        }

    async def strict_unwrap(self, key: str, mode: str = "freeze") -> dict[str, Any]:
        game = await self._game(key)
        store = lifecycle.LaunchOptionsStore(self.paths.runtime_dir)
        original = await asyncio.to_thread(store.original, game["appid"])
        if original is None:
            raise ValueError("no saved launch options for this game")
        await asyncio.to_thread(store.forget, game["appid"])
        await self.update_game_config(key, {"launchGate": mode})
        return {"appid": game["appid"], "options": original}

    async def sync_pull(self, key: str) -> dict[str, Any]:
        ctx = await self._sync_context(key)
        with self.jobs.job("sync"):
            result = await asyncio.to_thread(self._sync().pull, ctx)
        log_event(
            logging.INFO,
            "sync.pull",
            "Checked the cloud before play",
            gameKey=ctx.game_key,
            action=result.get("action"),
            reason=result.get("reason"),
        )
        return result

    async def sync_push(self, key: str) -> dict[str, Any]:
        ctx = await self._sync_context(key)
        with self.jobs.job("sync"):
            result = await asyncio.to_thread(self._sync().push, ctx)
        log_event(
            logging.INFO,
            "sync.push",
            "Saved to the cloud after play",
            gameKey=ctx.game_key,
            status=result.get("status"),
        )
        return result

    async def resolve_conflict(self, key: str, choice: str, head: str | None = None) -> dict[str, Any]:
        ctx = await self._sync_context(key)
        with self.jobs.job("sync"):
            result = await asyncio.to_thread(self._sync().resolve, ctx, str(choice), head)
        log_event(logging.WARNING, "sync.resolve", "Conflict resolved", gameKey=ctx.game_key, choice=choice)
        return result

    async def sync_status(self, key: str) -> dict[str, Any]:
        try:
            ctx = await self._sync_context(key)
        except ValueError as exc:
            return {"available": False, "reason": str(exc)}
        return {"available": True, "gameKey": ctx.game_key, **self._sync().status(ctx.game_key)}

    async def idle_pass(self) -> list[dict[str, Any]]:
        """Prefetch and push for every enabled game with no open session (section 9)."""
        outcomes = []
        for game in (await self.discover_games())["games"]:
            if not self.game_configs.get(game["key"]).get("enabled"):
                continue
            try:
                ctx = await self._sync_context(game["key"])
                with self.jobs.job("sync"):
                    sync = self._sync()
                    recovered = await asyncio.to_thread(sync.recover_session, ctx)
                    outcome = await asyncio.to_thread(sync.idle, ctx)
                if recovered:
                    await self.emit("keepsake_toast", f"Recovered missed exit backup for {game['name']}")
                session = self._sessions().get(ctx.game_key, {})
                if lifecycle.played_without_keepsake(int(game.get("last_played") or 0), session.get("lastStart")):
                    # Section 10: Steam saw a play Keepsake missed; the push above saved it. Warn once per play.
                    if session.get("warnedFor") != game.get("last_played"):
                        self._record_session(ctx.game_key, warnedFor=float(game.get("last_played") or 0))
                        await self.emit(
                            "keepsake_toast", f"{game['name']} was played while Keepsake was not running. Saved now."
                        )
                    outcome = {**outcome, "playedWithoutKeepsake": True}
                outcomes.append({"key": game["key"], **outcome})
            except (ValueError, SnapshotError, StoreError) as exc:
                outcomes.append({"key": game["key"], "status": "error", "error": str(exc)})
        log_event(logging.INFO, "sync.idle", "Idle pass finished", games=len(outcomes))
        return outcomes

    async def _idle_loop(self) -> None:
        delay = 60.0
        while True:
            await asyncio.sleep(delay)
            delay = IDLE_INTERVAL_SECONDS
            if self.jobs.busy_reason() is None:
                try:
                    await self.idle_pass()
                except Exception:  # noqa: BLE001 - the loop must survive any single failure
                    log_event(logging.ERROR, "sync.idle_failed", "Idle pass failed")

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
