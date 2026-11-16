"""Backend application core.

``main.py`` creates one :class:`KeepsakeApp` and forwards each frontend call to
it. Keeping the logic here means it can be tested without Decky.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
import uuid
import zipfile
from collections.abc import Callable, Coroutine
from typing import Any

from . import (
    configrev,
    diagnostics,
    discovery,
    health,
    identity,
    lifecycle,
    manifest,
    net,
    registry,
    resolve,
    restore,
    steamcloud,
)
from .auth import GOOGLE, AuthError, DeviceCodeFlow, TokenManager, TokenStore
from .backends import BackendConfigError, CredentialStore
from .bus import EventBus
from .engine import SnapshotEngine
from .freeze import Freezer
from .fsutil import atomic_write_json, read_json
from .gameconfig import DEFAULT as GAME_DEFAULTS
from .gameconfig import GameConfigStore, custom_path_from_absolute
from .importers import ludusavi
from .jobs import JobTracker
from .locks import GameLocks
from .log import log_event, setup_logging, tail
from .modules import Module, ModuleRegistry
from .paths import PluginPaths
from .procs import find_game_processes
from .settings import SettingsStore
from .snapshot import SnapshotError, content_hash, scan_entries
from .statedb import StateDB, StateError, open_db
from .steamops import SteamOps
from .store import AlreadyExistsError, LocalFolderStore, Store, StoreError
from .store.gdrive import GoogleDriveStore
from .store.graph import GraphStore
from .store.s3 import S3Store
from .store.webdav import WebDavStore
from .sync import GameContext, SyncEngine
from .update import Updater, startup_notice

EmitFn = Callable[..., Coroutine[Any, Any, None]]
IDENTITY_CACHE_SECONDS = 600
HISTORY_MAX = 200
CONFIG_STATE_FILE = "config-revisions.json"
TOAST_SIGNIN = "{name} sign-in needs attention. Open Keepsake, Settings, to sign in again."
BACKEND_NAMES = {
    "local": "Test store on this device",
    "onedrive": "OneDrive",
    "gdrive": "Google Drive",
    "webdav": "WebDAV",
    "s3": "S3",
}
IMPORT_STAGING = "import-staging"
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
        google_transport: net.Transport = net.google_request,
        google_api: tuple[str, str] | None = None,
        endpoint_transport: Callable[[str], net.Transport] = net.endpoint_transport,
    ) -> None:
        self._graph_base_url = graph_base_url
        self._google_transport = google_transport
        self._google_api = google_api  # tests point this at a fake Drive
        self._endpoint_transport = endpoint_transport
        self.credentials = CredentialStore(paths.settings_dir)
        self.google_tokens = TokenManager(
            TokenStore(paths.settings_dir, GOOGLE.token_file),
            lambda: str(self.credentials.load("gdrive")["clientId"]),
            transport=google_transport,
            provider=GOOGLE,
            client_secret=lambda: str(self.credentials.load("gdrive")["clientSecret"]),
        )
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
        self._signin_warned = False
        # v2 Core (slice 13, ADR-0012, ADR-0024): lifecycle bus, per-game locks, module registry, state database.
        self.bus = EventBus()
        self.locks = GameLocks()
        self.registry = ModuleRegistry(self.bus, lambda: dict(self.settings.get("moduleFlags")))
        self.db: StateDB | None = None
        self.steam_ops: SteamOps | None = None
        self._register_modules()

    def _register_modules(self) -> None:
        async def saves_health() -> list[dict[str, Any]]:
            return await self._health(probe=False)

        self.registry.register(
            Module(
                "saves",
                "Saves",
                "Keeps game saves in step between your devices through the cloud.",
                "Save files of the games you choose, their registry keys if you allow it, and Keepsake's own settings.",
                health=saves_health,
            )
        )
        for name, title, description, writes in (
            ("advisor", "Advisor", "Recommends settings for the game you play.", "Nothing. It only recommends."),
            ("replication", "Replication", "Copies games between your devices.", "Games you send between devices."),
            ("installer", "Installer", "Helps install games from ISOs and installers.", "Games you install with it."),
            (
                "desktop",
                "Desktop",
                "Keepsake in Desktop Mode, with a tray icon.",
                "Desktop Mode shortcuts for Keepsake.",
            ),
        ):
            self.registry.register(Module(name, title, description, writes, available=False))

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
        elif not self.settings.get("setupComplete") and self.game_configs.any_enabled():
            # Upgraded from a version without the setup wizard: games are already set up.
            self.settings.set("setupComplete", True)
        log_event(logging.INFO, "app.start", "Keepsake backend started", version=self.version)
        try:
            self.db = await asyncio.to_thread(open_db, self.paths.runtime_dir)
            self.steam_ops = SteamOps(self.db) if self.db else None
        except (StateError, OSError) as exc:  # modules needing state stay off; Saves is unaffected (P13)
            log_event(logging.ERROR, "state.unavailable", "State database unavailable", error=str(exc))
            self.db, self.steam_ops = None, None
        await self.registry.start_all()
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
        states = self._sync().state.games()
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
            config = self.game_configs.get(game["key"])
            state = states.get(match.get("gameKey") or "") or {}
            out.append(
                {
                    "key": game["key"],
                    "name": game["name"],
                    "kind": game["kind"],
                    **match,
                    "proposal": proposal,
                    "enabled": bool(config.get("enabled")),
                    "sync": status_word(state) if config.get("enabled") else "off",
                    "steamCloud": self._steam_cloud(game),
                    "hasRegistry": bool(
                        index and match.get("title") and index["games"].get(match["title"], {}).get("r")
                    ),
                }
            )
        return out

    def _steam_cloud(self, game: dict[str, Any]) -> str | None:
        """Steam Cloud state for Steam apps when detection is on (slice 11), else None."""
        if game["kind"] != "steam" or not self.settings.get("steamCloudDetection"):
            return None
        return steamcloud.cloud_state(
            game.get("steam_root"), game.get("default_user"), int(game["appid"]), int(game.get("last_played") or 0)
        )

    async def enable_steam_without_cloud(self) -> dict[str, Any]:
        """Turn on sync for every matched Steam app that has been played and has no Steam Cloud saves."""
        if not self.settings.get("steamCloudDetection"):
            raise ValueError("Steam Cloud detection is off in Settings")
        enabled = []
        for game, config, gk in await self._matched():
            if gk and not config.get("enabled") and self._steam_cloud(game) == steamcloud.NO_CLOUD:
                await self.update_game_config(game["key"], {"enabled": True})
                enabled.append(game["name"])
        log_event(logging.INFO, "steamcloud.bulk_enable", "Enabled Steam games without Steam Cloud", count=len(enabled))
        return {"enabled": enabled}

    # Suspend snapshots (slice 11, ADR-0022)

    async def on_suspend(self) -> dict[str, Any]:
        """The device is about to sleep: snapshot running synced games as provisional snapshots."""
        if not self.settings.get("suspendSnapshots") or not self.registry.enabled("saves"):
            return {"started": 0}
        states = self._sync().state.games()
        started = 0
        for game, config, gk in await self._matched():
            if config.get("enabled") and gk and (states.get(gk) or {}).get("sessionOpen"):
                self._background.append(asyncio.create_task(self._suspend_snapshot(game)))
                started += 1
        return {"started": started}

    async def _suspend_snapshot(self, game: dict[str, Any]) -> dict[str, Any]:
        try:
            ctx = await self._sync_context(game["key"], running=lambda: True)  # never restore here
            with self.jobs.job("sync"):
                result = await asyncio.to_thread(self._sync().provisional, ctx)
        except (ValueError, SnapshotError, StoreError) as exc:
            log_event(
                logging.WARNING, "suspend.snapshot_failed", "Suspend snapshot skipped", key=game["key"], error=str(exc)
            )
            return {"status": "error", "error": str(exc)}
        log_event(logging.INFO, "suspend.snapshot", "Suspend snapshot", key=game["key"], status=result.get("status"))
        return result

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
        record = index["games"].get(match["title"]) if index and match.get("title") else None
        return {
            "game": game,
            "config": config,
            "match": match,
            "suggestions": suggestions,
            "proposal": proposal,
            "hasRegistry": bool(record and record.get("r") and game.get("prefix")),
            "steamCloud": self._steam_cloud(game),
        }

    async def update_game_config(self, key: str, changes: dict[str, Any]) -> dict[str, Any]:
        await self._game(key)
        if "matchTitle" in changes and changes["matchTitle"] is not None:
            index = await asyncio.to_thread(self.manifest.load)
            if not index or changes["matchTitle"] not in index.get("games", {}):
                raise ValueError("that title is not in the manifest")
        config = await asyncio.to_thread(self.game_configs.update, key, dict(changes))
        log_event(logging.INFO, "game.config", "Game settings changed", key=key, fields=sorted(changes))
        if config.get("enabled") and (changes.get("enabled") or set(changes) & set(configrev.SHARED_FIELDS)):
            game_key = await self._game_key_of(key)
            if game_key:
                if changes.get("enabled"):
                    await self._sync_config(key, game_key)  # pick up settings another device shared
                else:
                    await self._publish_config(key, game_key)
                config = self.game_configs.get(key)
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

    # Cloud sign-in: OneDrive (slice 6) and Google Drive (slice 10); WebDAV and S3 use saved settings

    def _token_manager(self, backend: str) -> TokenManager:
        return self.google_tokens if backend == "gdrive" else self.tokens

    async def cloud_status(self) -> dict[str, Any]:
        store = str(self.settings.get("snapshotStore"))
        if store in ("webdav", "s3"):
            configured = self.credentials.configured(store)
            client_set, signed_in, problem = configured, configured, None
        else:
            manager = self._token_manager(store)
            client_set = bool(
                self.credentials.configured("gdrive") if store == "gdrive" else self.settings.get("onedriveClientId")
            )
            signed_in = await asyncio.to_thread(manager.signed_in)
            problem = manager.last_error
        return {
            "clientIdSet": client_set,
            "signedIn": signed_in,
            "signingIn": self._signin is not None,
            "problem": problem,
            "store": store,
            "name": BACKEND_NAMES.get(store, store),
            "onedriveSignedIn": await asyncio.to_thread(self.tokens.signed_in),
            "googleSignedIn": await asyncio.to_thread(self.google_tokens.signed_in),
        }

    async def start_signin(self, backend: str = "onedrive") -> dict[str, Any]:
        """Begin a device code flow. Only ever called from a user action (threat model T2)."""
        backend = "gdrive" if backend == "gdrive" else "onedrive"
        async with self._auth_lock:
            if self._signin is not None:
                self._signin.cancelled.set()
            if backend == "gdrive":
                client = self.credentials.load("gdrive")
                flow = DeviceCodeFlow(
                    str(client["clientId"]),
                    self.google_tokens.store,
                    transport=self._google_transport,
                    provider=GOOGLE,
                    client_secret=str(client["clientSecret"]),
                )
            else:
                flow = DeviceCodeFlow(
                    str(self.settings.get("onedriveClientId")), self.token_store, transport=self._transport
                )
            shown = await asyncio.to_thread(flow.start)
            self._signin = flow
        log_event(logging.INFO, "auth.signin_started", "Sign-in started", backend=backend)
        self._background.append(asyncio.create_task(self._finish_signin(flow, backend)))
        return shown

    async def _finish_signin(self, flow: DeviceCodeFlow, backend: str = "onedrive") -> None:
        try:
            await asyncio.to_thread(flow.poll)
        except AuthError as exc:
            if self._signin is flow:
                self._signin = None
            log_event(logging.WARNING, "auth.signin_failed", "Sign-in did not complete", reason=exc.reason)
            await self.emit("keepsake_signin", {"status": "failed", "reason": exc.reason})
            return
        if self._signin is flow:
            self._signin = None
        self._token_manager(backend).last_error = None
        log_event(logging.INFO, "auth.signed_in", "Signed in", backend=backend)
        registered = await self.register_device(self._gdrive() if backend == "gdrive" else self._graph())
        await self.emit("keepsake_signin", {"status": "signed-in", "registered": registered})

    async def cancel_signin(self) -> dict[str, Any]:
        if self._signin is not None:
            self._signin.cancelled.set()
            self._signin = None
        return {"ok": True}

    async def sign_out(self, backend: str = "onedrive") -> dict[str, Any]:
        await self.cancel_signin()
        manager = self._token_manager(backend)
        await asyncio.to_thread(manager.store.clear)
        log_event(logging.INFO, "auth.signed_out", "Signed out", backend=backend)
        return {"ok": True}

    def _graph(self) -> GraphStore:
        if self._graph_base_url:  # tests point this at a fake Graph
            return GraphStore(self.tokens, transport=self._transport, base_url=self._graph_base_url)
        return GraphStore(self.tokens, transport=self._transport)

    def _gdrive(self) -> GoogleDriveStore:
        if self._google_api:  # tests point this at a fake Drive
            api, upload = self._google_api
            return GoogleDriveStore(self.google_tokens, transport=self._google_transport, api=api, upload=upload)
        return GoogleDriveStore(self.google_tokens, transport=self._google_transport)

    def _webdav(self) -> WebDavStore:
        c = self.credentials.load("webdav")
        if not self.credentials.configured("webdav"):
            raise StoreError("enter the WebDAV address, user name and password first")
        return WebDavStore(c["url"], c["username"], c["password"], transport=self._endpoint_transport(c["url"]))

    def _s3(self) -> S3Store:
        c = self.credentials.load("s3")
        if not self.credentials.configured("s3"):
            raise StoreError("enter the S3 endpoint, bucket and access key first")
        path_style = bool(c["pathStyle"])
        return S3Store(
            c["endpoint"],
            c["region"],
            c["bucket"],
            c["accessKey"],
            c["secretKey"],
            prefix=c["prefix"],
            path_style=path_style,
            transport=self._endpoint_transport(S3Store.origin_for(c["endpoint"], c["bucket"], path_style)),
        )

    async def test_cloud(self, backend: str | None = None) -> dict[str, Any]:
        """Check the chosen backend. WebDAV and S3 must prove create-only writes (fail closed)."""
        backend = backend or str(self.settings.get("snapshotStore"))
        device_id = str(self.settings.get("deviceId"))
        try:
            store: Store
            if backend == "webdav":
                webdav = store = self._webdav()
                await asyncio.to_thread(webdav.check, device_id)
            elif backend == "s3":
                s3 = store = self._s3()
                await asyncio.to_thread(s3.check, device_id)
            elif backend == "gdrive":
                gdrive = store = self._gdrive()
                await asyncio.to_thread(gdrive.check)
            else:
                folder = await asyncio.to_thread(self._graph().check)
                return {"ok": True, "folder": folder.get("name")}
        except StoreError as exc:
            return {"ok": False, "error": str(exc)}
        registered = await self.register_device(store)
        return {"ok": True, "registered": registered}

    async def backend_config(self, backend: str) -> dict[str, Any]:
        return self.credentials.public(str(backend))

    async def set_backend_config(self, backend: str, values: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(self.credentials.save, str(backend), dict(values))
        except BackendConfigError as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "backend.config", "Backend settings saved", backend=backend)
        return result

    async def register_device(self, store: Store | None = None) -> bool:
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
        target = store if store is not None else self._graph()
        try:
            await asyncio.to_thread(target.put_new, key, json.dumps(entry, sort_keys=True).encode())
        except AlreadyExistsError:
            return True
        except StoreError as exc:
            log_event(logging.WARNING, "registry.failed", "Could not register this device", error=str(exc))
            return False
        return True

    # Snapshots against the local test store or the chosen cloud backend

    def _store(self) -> Store:
        backend = self.settings.get("snapshotStore")
        if backend == "onedrive":
            return self._graph()
        if backend == "gdrive":
            return self._gdrive()
        if backend == "webdav":
            return self._webdav()
        if backend == "s3":
            return self._s3()
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
        roots: dict[str, str | None] = dict(resolve.logical_roots(game, home=self.home))
        files = dict(scan.get("files", {}))
        reg_keys = self._registry_keys(game, record, config)
        if reg_keys:
            roots["registry"] = self._registry_dir(match["gameKey"])
            exported = await asyncio.to_thread(self._export_registry, game, reg_keys, match["gameKey"])
            if exported:
                files["registry"] = exported
        procs = await asyncio.to_thread(find_game_processes, int(game["appid"]), game.get("prefix"), self.proc_root)
        return {
            "game": game,
            "gameKey": match["gameKey"],
            "files": files,
            "roots": roots,
            "running": bool(procs),
            "registryKeys": reg_keys,
        }

    # Registry keys (slice 11, ADR-0022): exported into a fragment for snapshots, merged back after restores

    def _registry_keys(self, game: dict[str, Any], record: dict[str, Any] | None, config: dict[str, Any]) -> list[str]:
        if (
            not self.settings.get("registrySync")
            or not config.get("syncRegistry")
            or not record
            or not game.get("prefix")
        ):
            return []
        keys = []
        for entry in record.get("r", []):
            path, tags = str(entry[0]), str(entry[1])
            if "s" in tags or (config.get("includeConfig") and "c" in tags):
                mapped = registry.hive_and_key(path)
                if mapped and mapped[0] == "user.reg":
                    keys.append(mapped[1])
        return sorted(set(keys))

    def _registry_dir(self, game_key: str) -> str:
        path = os.path.join(self.paths.runtime_dir, "registry", game_key)
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def _user_reg(game: dict[str, Any]) -> str:
        return os.path.join(str(game["prefix"]), "pfx", "user.reg")

    def _export_registry(self, game: dict[str, Any], keys: list[str], game_key: str) -> list[str]:
        """Write the managed keys' fragment to Keepsake's staging folder. Fails closed on an unreadable file."""
        target = os.path.join(self._registry_dir(game_key), "user.reg")
        source = self._user_reg(game)
        fragment = None
        if os.path.isfile(source):
            try:
                fragment = registry.export(registry.read_text(source), keys)
            except registry.RegistryError as exc:
                raise SnapshotError(f"user.reg could not be read safely: {exc}") from exc
        if fragment is None:
            if os.path.exists(target):
                os.unlink(target)
            return []
        current = None
        if os.path.exists(target):
            with open(target, encoding="utf-8") as handle:
                current = handle.read()
        if current != fragment:
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(fragment)
        return ["user.reg"]

    def _merge_registry(self, game: dict[str, Any], keys: list[str], game_key: str) -> dict[str, str]:
        """Apply a restored fragment to user.reg. A snapshot without registry keys changes nothing."""
        fragment_path = os.path.join(self._registry_dir(game_key), "user.reg")
        target = self._user_reg(game)
        if not keys or not os.path.isfile(fragment_path) or not os.path.isfile(target):
            return {"status": "skipped"}
        if find_game_processes(int(game["appid"]), game.get("prefix"), self.proc_root):
            raise SnapshotError("the game is running; registry keys are only written while it is closed")
        with open(fragment_path, encoding="utf-8") as handle:
            fragment = handle.read()
        backups = os.path.join(self.paths.runtime_dir, "registry-backups", game_key)
        result = registry.merge_file(target, fragment, keys, backups)
        log_event(logging.INFO, "registry.merge", "Registry keys restored", gameKey=game_key, status=result["status"])
        return result

    async def _after_restore(self, ctx: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        if not ctx.get("registryKeys"):
            return result
        try:
            merged = await asyncio.to_thread(self._merge_registry, ctx["game"], ctx["registryKeys"], ctx["gameKey"])
        except (registry.RegistryError, SnapshotError, OSError) as exc:
            log_event(logging.WARNING, "registry.merge_failed", "Registry keys not restored", error=str(exc))
            await self.emit("keepsake_toast", f"Save files restored, but registry keys were left unchanged: {exc}")
            return {**result, "registry": "failed"}
        return {**result, "registry": merged["status"]}

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
        summary = snap_summary
        latest: dict[str, dict[str, Any]] = {}
        for meta in metas:
            device = str(meta.get("deviceId") or meta.get("deviceName"))
            if device not in latest or meta["created"] > latest[device]["created"]:
                latest[device] = meta

        return {
            "lastByDevice": [
                {"device": m.get("deviceName"), "created": m["created"], "kind": m["kind"], "snapId": m["snapId"]}
                for m in sorted(latest.values(), key=lambda m: m["created"], reverse=True)
            ],
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
        async with self.locks.hold(ctx["gameKey"], "saves"):
            with self.jobs.job("restore"):
                result = await asyncio.to_thread(
                    eng.restore, ctx["gameKey"], str(snap_id), ctx["files"], ctx["roots"], ctx["running"]
                )
                result = await self._after_restore(ctx, result)
        self._set_base(ctx["gameKey"], str(snap_id))
        log_event(
            logging.INFO, "snapshot.restore", "Snapshot restored", gameKey=ctx["gameKey"], status=result["status"]
        )
        return result

    async def undo_restore(self, key: str, prerestore_id: str) -> dict[str, Any]:
        ctx = await self._snapshot_context(key)
        eng = self._engine()
        async with self.locks.hold(ctx["gameKey"], "saves"):
            with self.jobs.job("restore"):
                result = await asyncio.to_thread(
                    eng.restore_prerestore,
                    ctx["gameKey"],
                    str(prerestore_id),
                    ctx["files"],
                    ctx["roots"],
                    ctx["running"],
                )
                result = await self._after_restore(ctx, result)
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
        state = self._sync().state
        if result["status"] == "published" and state.get(game_key).get("quarantined") == str(snap_id):
            state.update(game_key, quarantined=None)
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

        reg_keys = ctx["registryKeys"]

        def files() -> dict[str, list[str]]:
            scan = resolve.preview(game, match["title"], record, config, self.home, 0, True)
            if scan.get("truncated"):
                raise SnapshotError("too many files to sync safely; add exclusions")
            found = dict(scan.get("files", {}))
            if reg_keys:
                exported = self._export_registry(game, reg_keys, ctx["gameKey"])
                if exported:
                    found["registry"] = exported
            return found

        def after_restore() -> None:
            if reg_keys:
                self._merge_registry(game, reg_keys, ctx["gameKey"])

        def processes_running() -> bool:
            return bool(find_game_processes(int(game["appid"]), game.get("prefix"), self.proc_root))

        def identity_record() -> dict[str, Any]:
            return identity.identity_record(
                ctx["gameKey"],
                str(self.settings.get("deviceId")),
                match.get("title"),
                identity.local_hints(game),
                identity.save_dirs({root: rels for root, rels in files().items() if root != "registry"}),
            )

        return GameContext(
            ctx["gameKey"],
            files=files,
            roots=ctx["roots"],
            running=running or processes_running,
            identity=identity_record,
            after_restore=after_restore,
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
        if not self.registry.enabled("saves"):
            return {"handled": 0}  # Saves switched off: no launch gate, no exit save
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
        game_key: str | None = None
        try:
            ctx_probe = await self._sync_context(key)
            game_key = ctx_probe.game_key
            self._record_session(ctx_probe.game_key, lastStart=time.time())
            await self.bus.publish("game_started", {"gameKey": game_key, "appid": game["appid"]})
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
                    if frozen:
                        await self.bus.publish("game_frozen", {"gameKey": game_key, "appid": game["appid"]})
            if token is not None or frozen:
                # Blocked in the gate script or frozen: safe to restore until the pull is abandoned.
                running: Callable[[], bool] = abort.is_set
            else:
                running = lambda: True  # noqa: E731 - could not hold the game: never restore under it
            ctx = await self._sync_context(key, running=running)
            async with self.locks.hold(ctx.game_key, "saves"):
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
            if game_key and (frozen or token is not None):
                await self.bus.publish("game_released", {"gameKey": game_key, "appid": game["appid"]})

    def _wait_for_processes(self, game: dict[str, Any]) -> list[Any]:
        found: list[Any] = []

        def check() -> bool:
            nonlocal found
            found = find_game_processes(int(game["appid"]), game.get("prefix"), self.proc_root)
            return bool(found)

        lifecycle.wait_for(check, lifecycle.FIND_PROCESS_SECONDS)
        return found

    async def _announce_pull(self, game: dict[str, Any], result: dict[str, Any]) -> None:
        suspended = result.get("suspended")
        if suspended:
            # Never adopted without the user: they choose to restore it from History.
            await self.emit(
                "keepsake_toast",
                f"{suspended.get('device') or 'Another device'} went to sleep while playing {game['name']}. "
                "Its unsaved progress is in History as a suspend snapshot.",
            )
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
            await self.bus.publish("game_exited", {"gameKey": ctx.game_key, "appid": game["appid"]})
            async with self.locks.hold(ctx.game_key, "saves"):
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
        async with self.locks.hold(ctx.game_key, "saves"):
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
        async with self.locks.hold(ctx.game_key, "saves"):
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
        async with self.locks.hold(ctx.game_key, "saves"):
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
                async with self.locks.hold(ctx.game_key, "saves"):
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
                if outcome.get("status") == "conflict" or outcome.get("push") == "published-fork":
                    await self.emit("keepsake_toast", f"Save conflict for {game['name']}. Open Keepsake to choose.")
                elif outcome.get("push") == "quarantined":
                    await self.emit(
                        "keepsake_toast", f"{game['name']}: a suspicious save was kept on this device, not uploaded."
                    )
                try:
                    outcome = {**outcome, "config": await self._sync_config(game["key"], ctx.game_key)}
                except StoreError:
                    pass  # shared settings wait for the next pass
                outcomes.append({"key": game["key"], **outcome})
            except (ValueError, SnapshotError, StoreError) as exc:
                outcomes.append({"key": game["key"], "status": "error", "error": str(exc)})
        await self._warn_signin()
        log_event(logging.INFO, "sync.idle", "Idle pass finished", games=len(outcomes))
        return outcomes

    async def _warn_signin(self) -> None:
        """Toast once when OneDrive sign-in stops working; again only after it has recovered."""
        store = str(self.settings.get("snapshotStore"))
        problem = store in ("onedrive", "gdrive") and bool(self._token_manager(store).last_error)
        if problem and not self._signin_warned:
            await self.emit("keepsake_toast", TOAST_SIGNIN.format(name=BACKEND_NAMES[store]))
        self._signin_warned = problem

    async def _idle_loop(self) -> None:
        delay = 60.0
        while True:
            await asyncio.sleep(delay)
            delay = float(self.settings.get("idleSyncMinutes")) * 60
            if self.jobs.busy_reason() is None and self.registry.enabled("saves"):
                try:
                    await self.idle_pass()
                except Exception:  # noqa: BLE001 - the loop must survive any single failure
                    log_event(logging.ERROR, "sync.idle_failed", "Idle pass failed")

    # Gaming Mode UX (slice 9): views across games, setup wizard, health and shared game settings

    async def _matched(self) -> list[tuple[dict[str, Any], dict[str, Any], str | None]]:
        """``(game, config, gameKey)`` for every discovered game, from local data only."""
        games = (await self.discover_games())["games"]
        index = await asyncio.to_thread(self.manifest.load)
        out = []
        for game in games:
            config = self.game_configs.get(game["key"])
            out.append((game, config, manifest.match_game(index, game, config).get("gameKey")))
        return out

    async def _game_key_of(self, key: str) -> str | None:
        game = await self._game(key)
        index = await asyncio.to_thread(self.manifest.load)
        found = manifest.match_game(index, game, self.game_configs.get(key)).get("gameKey")
        return str(found) if found else None

    async def qam_summary(self) -> dict[str, Any]:
        """Everything the Quick Access Menu shows, without network calls."""
        states = self._sync().state.games()
        enabled = [(g, gk) for g, c, gk in await self._matched() if c.get("enabled") and gk]
        last = max(
            (
                max(float(s.get("lastPush") or 0), float(s.get("lastPull") or 0))
                for s in states.values()
                if isinstance(s, dict)
            ),
            default=0.0,
        )
        current = None
        for game, gk in enabled:
            state = states.get(gk) or {}
            if state.get("sessionOpen"):
                current = {"key": game["key"], "name": game["name"], "status": status_word(state)}
                break
        cloud = await self.cloud_status()
        checks = await self._health(probe=False)
        return {
            "store": cloud["store"],
            "signedIn": cloud["signedIn"],
            "deviceName": self.settings.get("deviceName"),
            "lastSync": last or None,
            "health": health.summary(checks),
            "problems": [c["label"] for c in checks if c["status"] in (health.WARN, health.FAIL)],
            "conflicts": sum(1 for _, gk in enabled if (states.get(gk) or {}).get("conflict")),
            "enabledGames": len(enabled),
            "currentGame": current,
            "setupComplete": bool(self.settings.get("setupComplete")),
            "busy": self.jobs.busy_reason(),
        }

    async def sync_now(self) -> dict[str, Any]:
        """The "Sync now" button: run the idle pass at once."""
        if self.jobs.busy_reason() is not None:
            return {"ok": False, "reason": "busy"}
        outcomes = await self.idle_pass()
        counts: dict[str, int] = {}
        for outcome in outcomes:
            status = str(outcome.get("status"))
            counts[status] = counts.get(status, 0) + 1
        return {"ok": True, "games": len(outcomes), "counts": counts}

    async def list_conflicts(self) -> list[dict[str, Any]]:
        states = self._sync().state.games()
        out = []
        for game, _config, gk in await self._matched():
            conflict = (states.get(gk) or {}).get("conflict") if gk else None
            if conflict:
                out.append({"key": game["key"], "name": game["name"], "gameKey": gk, "conflict": conflict})
        return out

    async def conflict_details(self, key: str) -> dict[str, Any]:
        game = await self._game(key)
        ctx = await self._sync_context(key)
        details = await asyncio.to_thread(self._sync().conflict_details, ctx)
        return {"key": key, "name": game["name"], "gameKey": ctx.game_key, **details}

    async def recent_history(self, limit: int = 50) -> dict[str, Any]:
        """Recent snapshots across synced games, newest first, including quarantined ones."""
        states = self._sync().state.games()
        bases = self._bases()
        eng = self._engine()
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        seen: set[str] = set()
        for game, config, gk in await self._matched():
            if not gk or gk in seen or not (config.get("enabled") or gk in states or gk in bases):
                continue
            seen.add(gk)
            try:
                metas = await asyncio.to_thread(eng.list_metas, gk)
                pins = {p["snapId"] for p in await asyncio.to_thread(eng.pins, gk)}
                pruned = await asyncio.to_thread(eng.pruned, gk)
            except StoreError as exc:
                errors.append(f"{game['name']}: {exc}")
                continue
            base = (states.get(gk) or {}).get("base") or bases.get(gk)
            owner = {"key": game["key"], "name": game["name"], "gameKey": gk}
            for meta in metas:
                items.append(
                    {
                        **snap_summary(meta),
                        **owner,
                        "pinned": meta["snapId"] in pins,
                        "pruned": meta["snapId"] in pruned,
                        "base": meta["snapId"] == base,
                        "quarantined": False,
                    }
                )
            for record in eng.quarantine.list(gk):
                items.append(
                    {**snap_summary(record["meta"]), **owner, "quarantined": True, "reasons": record.get("reasons", [])}
                )
        items.sort(key=lambda i: (i["created"], i["snapId"]), reverse=True)
        return {"snapshots": items[: max(1, min(int(limit), HISTORY_MAX))], "errors": errors}

    async def plan_sync(self, keys: list[str]) -> list[dict[str, Any]]:
        """Setup wizard dry run: what the first sync would do for each game. Changes nothing."""
        out = []
        for key in [str(k) for k in keys][:HISTORY_MAX]:
            name = key
            try:
                name = (await self._game(key))["name"]
                ctx = await self._sync_context(key)
                plan = await asyncio.to_thread(self._sync().plan, ctx)
            except (ValueError, SnapshotError, StoreError, OSError) as exc:
                plan = {"action": "error", "reason": str(exc)}
            out.append({"key": key, "name": name, **plan})
        return out

    async def finish_setup(self, keys: list[str]) -> dict[str, Any]:
        """Setup wizard confirm: enable the chosen games, mark setup done and start the first sync."""
        enabled = 0
        for key in [str(k) for k in keys][:HISTORY_MAX]:
            await self.update_game_config(key, {"enabled": True})
            enabled += 1
        self.settings.set("setupComplete", True)
        log_event(logging.INFO, "setup.finished", "Setup wizard finished", games=enabled)
        if enabled:
            self._background.append(asyncio.create_task(self.sync_now()))
        return {"ok": True, "enabled": enabled}

    async def health_checks(self, probe: bool = True) -> dict[str, Any]:
        checks = await self._health(probe=bool(probe))
        return {"checks": checks, "summary": health.summary(checks)}

    async def _health(self, probe: bool) -> list[dict[str, Any]]:
        cloud: dict[str, Any] = dict(await self.cloud_status())
        if probe and cloud["store"] != "local" and cloud["signedIn"]:
            tested = await self.test_cloud()
            cloud.update(reachable=tested["ok"], error=tested.get("error"))
        states = self._sync().state.games()
        sessions = self._sessions()
        matched = await self._matched()
        games = []
        for game, config, gk in matched:
            if not config.get("enabled") or not gk:
                continue
            state = states.get(gk) or {}
            running = False
            if state.get("sessionOpen"):
                procs = await asyncio.to_thread(
                    find_game_processes, int(game["appid"]), game.get("prefix"), self.proc_root
                )
                running = bool(procs)
            games.append(
                {
                    "name": game["name"],
                    "state": state,
                    "running": running,
                    "playedWithoutKeepsake": lifecycle.played_without_keepsake(
                        int(game.get("last_played") or 0), sessions.get(gk, {}).get("lastStart")
                    ),
                }
            )
        names = {g["key"]: g["name"] for g, _c, _k in matched}
        mismatches = await asyncio.to_thread(discovery.load_mismatches, self.paths.runtime_dir)
        facts = {
            "now": time.time(),
            "cloud": cloud,
            "games": games,
            "mismatches": [names.get(k, "Unreadable mismatch record") for k in mismatches],
            "manifest": await asyncio.to_thread(self.manifest.status),
            "ludusavi": await asyncio.to_thread(health.detect_decky_plugin, os.environ.get("DECKY_HOME"), "ludusavi"),
        }
        return health.run(facts)

    # Shared game settings (config revisions in the cloud)

    def _config_state(self) -> dict[str, Any]:
        data = read_json(os.path.join(self.paths.runtime_dir, CONFIG_STATE_FILE), default={})
        return data if isinstance(data, dict) else {}

    def _update_config_state(self, game_key: str, **changes: Any) -> dict[str, Any]:
        data = self._config_state()
        record = {**(data.get(game_key) or {}), **changes}
        data[game_key] = record
        atomic_write_json(os.path.join(self.paths.runtime_dir, CONFIG_STATE_FILE), data)
        return record

    async def _publish_config(self, key: str, game_key: str) -> bool:
        """Share this device's settings for a game. Left pending and retried by the idle pass if offline."""
        based_on = self._config_state().get(game_key, {}).get("applied")
        self._update_config_state(game_key, pending=True)
        device_name = str(self.settings.get("deviceName") or "Unnamed device")
        try:
            name = await asyncio.to_thread(
                configrev.publish,
                self._store(),
                game_key,
                str(self.settings.get("deviceId")),
                device_name,
                self.game_configs.get(key),
                based_on,
            )
        except StoreError as exc:
            log_event(logging.INFO, "config.publish_pending", "Game settings will be shared later", error=str(exc))
            return False
        self._update_config_state(
            game_key, applied=name, pending=False, appliedFrom=device_name, appliedAt=time.time(), concurrent=[]
        )
        log_event(logging.INFO, "config.published", "Shared game settings", gameKey=game_key)
        return True

    async def _sync_config(self, key: str, game_key: str) -> dict[str, Any]:
        """Publish a pending local change, then apply the newest revision from any device."""
        if self._config_state().get(game_key, {}).get("pending") and not await self._publish_config(key, game_key):
            return {"applied": False, "pending": True}
        revisions = await asyncio.to_thread(configrev.list_revisions, self._store(), game_key)
        chosen = configrev.newest(revisions)
        local = configrev.shared_part(self.game_configs.get(key))
        if chosen is None:
            if local != configrev.shared_part(GAME_DEFAULTS):
                await self._publish_config(key, game_key)
            return {"applied": False}
        applied = False
        if chosen["name"] != self._config_state().get(game_key, {}).get("applied") and local != chosen["config"]:
            await asyncio.to_thread(self.game_configs.update, key, dict(chosen["config"]))
            applied = True
            log_event(logging.INFO, "config.applied", "Applied game settings from another device", gameKey=game_key)
        self._update_config_state(
            game_key,
            applied=chosen["name"],
            appliedFrom=chosen["deviceName"],
            appliedAt=chosen["createdTs"],
            concurrent=sorted({r["deviceName"] or r["deviceId"] for r in configrev.concurrent_with(revisions, chosen)}),
        )
        return {"applied": applied}

    async def game_config_sync(self, key: str) -> dict[str, Any]:
        """Where this game's shared settings came from, for the game page. No network."""
        game_key = await self._game_key_of(key)
        record = self._config_state().get(game_key or "", {})
        return {
            "gameKey": game_key,
            "appliedFrom": record.get("appliedFrom"),
            "appliedAt": record.get("appliedAt"),
            "pending": bool(record.get("pending")),
            "concurrent": list(record.get("concurrent") or []),
        }

    # Ludusavi import (slice 10, ADR-0021)

    async def ludusavi_scan(self, root: str) -> dict[str, Any]:
        """Games in a Ludusavi backup folder on this device, each with a suggested game key."""
        root = str(root).strip()
        if root == "~" or root.startswith("~/"):
            root = os.path.join(self.home or os.path.expanduser("~"), root[2:])
        try:
            games = await asyncio.to_thread(ludusavi.scan, root)
        except ludusavi.LudusaviError as exc:
            raise ValueError(str(exc)) from exc
        index = await asyncio.to_thread(self.manifest.load)
        local = {gk: game for game, _c, gk in await self._matched() if gk}
        for entry in games:
            name = entry["name"]
            known = bool(index and name in index.get("games", {}))
            suggested = manifest.game_key(name)
            entry["gameKey"] = suggested
            entry["inManifest"] = known
            entry["localGame"] = local[suggested]["name"] if suggested in local else None
        return {"root": root, "games": games}

    async def ludusavi_import(self, root: str, folder: str, backup_ids: list[str], game_key: str) -> dict[str, Any]:
        """Import chosen Ludusavi backups of one game as ``import`` snapshots. Never touches local saves."""
        if not isinstance(game_key, str) or not re.match(r"^[a-z0-9][a-z0-9-]{0,99}$", game_key):
            raise ValueError("choose a game key: lower-case letters, digits and hyphens")
        game_folder = os.path.join(str(root), str(folder))
        if os.sep in str(folder) or "/" in str(folder) or str(folder) in ("", ".", ".."):
            raise ValueError("invalid game folder")
        eng = self._engine()
        results = []
        with self.jobs.job("import"):
            existing = {
                (m["contentHash"], m["created"])
                for m in await asyncio.to_thread(eng.list_metas, game_key)
                if m.get("kind") == "import"
            }
            for backup_id in [str(b) for b in backup_ids][:HISTORY_MAX]:
                staging = os.path.join(self.paths.runtime_dir, IMPORT_STAGING, uuid.uuid4().hex)
                try:
                    extracted = await asyncio.to_thread(ludusavi.extract, game_folder, backup_id, staging)
                    if not extracted["files"]:
                        results.append({"backup": backup_id, "status": "nothing-to-import", **_skips(extracted)})
                        continue
                    created = extracted["created"]
                    entries = await asyncio.to_thread(scan_entries, extracted["files"], extracted["roots"])
                    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created if created else time.time()))
                    if (content_hash(entries), stamp) in existing:
                        results.append({"backup": backup_id, "status": "already-imported", **_skips(extracted)})
                        continue
                    outcome = await asyncio.to_thread(
                        eng.take,
                        game_key,
                        extracted["files"],
                        extracted["roots"],
                        "import",
                        None,
                        parents=[],
                        force=True,
                        gate=False,
                        flags=["ludusavi"],
                        created=created,
                    )
                    results.append(
                        {
                            "backup": backup_id,
                            "status": outcome["status"],
                            "snapId": outcome.get("snapId"),
                            **_skips(extracted),
                        }
                    )
                except (ludusavi.LudusaviError, SnapshotError, OSError, zipfile.BadZipFile) as exc:
                    results.append({"backup": backup_id, "status": "error", "error": str(exc), "skipped": []})
                except StoreError as exc:
                    results.append({"backup": backup_id, "status": "error", "error": str(exc), "skipped": []})
                    break  # the cloud is unreachable: stop rather than fail every backup
                finally:
                    await asyncio.to_thread(shutil.rmtree, staging, True)
        log_event(
            logging.INFO,
            "import.ludusavi",
            "Ludusavi import finished",
            gameKey=game_key,
            imported=sum(1 for r in results if r["status"] == "published"),
            failed=sum(1 for r in results if r["status"] == "error"),
        )
        return {"gameKey": game_key, "results": results}

    # Modules and the Steam Operations Executor (slice 13)

    async def modules_status(self) -> dict[str, Any]:
        return {
            "modules": await self.registry.status(),
            "stateDatabase": self.db is not None,
            "locks": self.locks.held(),
            "steamOpsPending": await asyncio.to_thread(self.steam_ops.pending_count) if self.steam_ops else 0,
        }

    async def set_module_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        if name not in self.registry.modules:
            raise ValueError("unknown module")
        flags = dict(self.settings.get("moduleFlags"))
        flags[name] = bool(enabled)
        self.settings.set("moduleFlags", flags)
        await self.registry.apply_flags()
        log_event(logging.INFO, "module.flag", "Module switched", module=name, enabled=bool(enabled))
        return await self.modules_status()

    async def reset_module(self, name: str) -> dict[str, Any]:
        if name not in self.registry.modules:
            raise ValueError("unknown module")
        await self.registry.reset(name)
        return await self.modules_status()

    def _ops(self) -> SteamOps:
        if self.steam_ops is None:
            raise ValueError("the state database is not available, so Steam operations are off")
        return self.steam_ops

    async def steam_probe(self) -> dict[str, Any]:
        """Diagnostics button: ask the frontend which Steam client functions exist (writes nothing)."""
        op_id = await asyncio.to_thread(self._ops().enqueue, "core", "probe", {})
        await self.emit("keepsake_steam_ops")
        return {"id": op_id}

    async def steam_ops_claim(self) -> dict[str, Any] | None:
        if self.steam_ops is None:
            return None
        return await asyncio.to_thread(self.steam_ops.claim)

    async def steam_ops_finish(self, op_id: int, ok: bool, result: dict[str, Any]) -> dict[str, Any]:
        await asyncio.to_thread(self._ops().finish, int(op_id), bool(ok), dict(result))
        log_event(logging.INFO, "steamops.finished", "Steam operation finished", id=int(op_id), ok=bool(ok))
        return {"ok": True}

    async def steam_ops_list(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.steam_ops.list) if self.steam_ops else []

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
        await self.registry.stop_all()
        if self.db is not None:
            self.db.close()
            self.db, self.steam_ops = None, None
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
            {
                "freezer": self.freezer.status(),
                "manifest": self.manifest.status(),
                "health": await self._health(probe=False),
            },
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


def status_word(state: dict[str, Any]) -> str:
    """One word for a game's sync state, used for list icons and the current game card."""
    if state.get("conflict"):
        return "conflict"
    if state.get("quarantined"):
        return "quarantined"
    if state.get("pending"):
        return "pending"
    if state.get("base"):
        return "synced"
    return "not-synced"


def _skips(extracted: dict[str, Any]) -> dict[str, Any]:
    return {"skipped": extracted.get("skipped", [])[:50], "skippedCount": len(extracted.get("skipped", []))}


def snap_summary(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapId": meta["snapId"],
        "created": meta["created"],
        "kind": meta["kind"],
        "device": meta.get("deviceName"),
        "files": len(meta["files"]),
        "bytes": sum(f["size"] for f in meta["files"]),
    }
