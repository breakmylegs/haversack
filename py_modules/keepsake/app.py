"""Backend application core.

``main.py`` creates one :class:`KeepsakeApp` and forwards each frontend call to
it. Keeping the logic here means it can be tested without Decky.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import json
import logging
import os
import re
import secrets
import shutil
import sys
import time
import uuid
import zipfile
from collections.abc import Callable, Coroutine, Mapping
from typing import Any
from urllib.parse import urlsplit

from . import (
    activity,
    clients,
    configrev,
    devicechecks,
    diagnostics,
    directsync,
    discovery,
    health,
    hosts,
    identity,
    launchers,
    lifecycle,
    manifest,
    net,
    ordering,
    pcwatch,
    playtime,
    power,
    procs,
    registry,
    remotecopies,
    resolve,
    restore,
    retention,
    steamcloud,
    storage,
    uninstall,
)
from .advisor import anticheat, deckverified
from .advisor import compat as advisor_compat
from .advisor.pcgw import PcgwClient
from .advisor.service import Advisor, AdvisorError
from .auth import GOOGLE, AuthError, DeviceCodeFlow, TokenManager, TokenStore
from .backends import BackendConfigError, CredentialStore
from .bus import EventBus
from .engine import SnapshotEngine
from .freeze import Freezer
from .fsutil import atomic_write_json, read_json
from .gameconfig import DEFAULT as GAME_DEFAULTS
from .gameconfig import GameConfigStore, custom_path_from_absolute
from .importers import ludusavi
from .installer import artwork, inplace, lanfind, netfuse, remote, smbshare, udisks, webdav
from .installer import files as installer_files
from .installer.artwork import SteamGridDB
from .installer.service import InPlaceFailed, Installer, InstallerError
from .installer.service import health_checks as installer_health_checks
from .jobs import JobTracker
from .locks import GameLocks
from .log import log_event, setup_logging, tail
from .loopback_auth import BrowserProbe, LoopbackFlow
from .modules import Module, ModuleRegistry
from .paths import PluginPaths
from .procs import find_game_processes
from .replication import link as replication_link
from .replication import netinfo, transfer
from .replication.jobs import Transfers, hold_reason
from .replication.offers import Incoming, OfferError, Outgoing, send_offer
from .replication.ongoing import GameLinks, keep_relative
from .replication.ongoing import LinkError as LinkStoreError
from .replication.ongoing import scan as scan_game
from .replication.peers import PeerStore
from .replication.sendgame import SendError
from .replication.sendgame import plan as send_plan
from .replication.service import Links, ReplicationError, parse_address
from .replication.service import health_checks as replication_health_checks
from .replication.source import Shares
from .resolve import ALL_ROOTS
from .safepath import PathEscapeError, validate_relative
from .settings import SettingsStore
from .snapshot import SnapshotError, content_hash, scan_entries
from .statedb import StateDB, StateError, open_db
from .statedb import sqlite_available as statedb_sqlite_available
from .steamops import SteamOps
from .store import AlreadyExistsError, LocalFolderStore, Store, StoreError, httpcall
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
    "direct": "Directly between my devices",
}
IMPORT_STAGING = "import-staging"
UNRESOLVED_METHODS = ("none", "ambiguous", "no-save-data", "no-manifest")

FREEZE_TEST_MIN = 1
FREEZE_TEST_MAX = 10
SIMULATED_JOB_MAX = 120
IDLE_EVENT = "keepsake_idle"
MANIFEST_PROGRESS_EVENT = "keepsake_manifest_progress"
ADVISOR_EVENT = "keepsake_advisor"
IMPORT_PROGRESS_EVENT = "keepsake_import_progress"
REPLICATION_EVENT = "keepsake_replication"
MANIFEST_PROGRESS_SECONDS = 0.5
RETARGET_KINDS = ("set-shortcut-name", "set-shortcut-exe", "set-shortcut-start-dir", "set-launch-options")


def import_verdict(results: list[dict[str, Any]], error: str | None) -> str:
    """One game's outcome in an import of every game: failed, imported, already imported or nothing to import."""
    statuses = {r.get("status") for r in results}
    if error or "error" in statuses:
        return "failed"
    if "published" in statuses:
        return "imported"
    if statuses == {"already-imported"}:
        return "already-imported"
    return "nothing-to-import"


async def _no_emit(event: str, *args: Any) -> None:
    return None


# Games whose launch Keepsake cannot see: newer saves come in from the idle pass (ADR-0051).
AUTO_PULL_KINDS = ("heroic", "lutris", "bottles", "emulator")
AUTO_SYNC_METHODS = ("steam-id", "title", "manual")  # matches with known save locations (ADR-0063)
SCRUB_FILE = "integrity.json"
SCRUB_INTERVAL = 7 * 24 * 3600
EXPORT_README = """Keepsake export

Each folder holds one game. Each zip is one snapshot of that game's save files, named by
date and snapshot id, and checked against Keepsake's records when it was exported.

Inside a zip, files sit under neutral folder names rather than paths from one device:
  winLocalAppData  Windows %LOCALAPPDATA% (in a Proton prefix: AppData/Local)
  winAppData       Windows %APPDATA% (AppData/Roaming)
  winLocalAppDataLow  AppData/LocalLow
  winDocuments     Documents
  winSavedGames    Saved Games
  winPublic        C:/Users/Public
  winProgramData   C:/ProgramData
  base             the game's install folder
  home, xdgConfig, xdgData  Linux home, ~/.config and ~/.local/share
  steamUserdata    the game's folder in Steam's userdata
  registry         the game's registry keys, as a user.reg fragment
To use a save elsewhere, copy the files from that folder to the same place for the game.

index.json lists every snapshot, its game, device, time and files.
"""
WINDOWS_NAME_CHARS = set('<>:"/\\|?*')


def export_folder(folder: Any) -> str:
    """The folder an export goes into: an existing, absolute, writable folder the user chose."""
    path = str(folder or "").strip()
    if not path or not os.path.isabs(path) or "\x00" in path:
        raise ValueError("choose a folder to export to")
    path = os.path.realpath(path)
    if not os.path.isdir(path):
        raise ValueError("that folder does not exist")
    if not os.access(path, os.W_OK):
        raise ValueError("Keepsake cannot write to that folder")
    return path


def safe_name(name: Any) -> str:
    """A folder name that works on FAT, exFAT, NTFS and ext4: no reserved characters, no trailing dot."""
    text = "".join("_" if ch in WINDOWS_NAME_CHARS or ord(ch) < 32 else ch for ch in str(name)).strip(" .")
    return text[:80] or "Unnamed game"


def _new_folder(parent: str, name: str) -> str:
    """Create a new folder ``name`` in ``parent``, numbered if one already exists; never reuses one."""
    for attempt in range(1, 100):
        path = os.path.join(parent, name if attempt == 1 else f"{name} ({attempt})")
        try:
            os.makedirs(path)
            return path
        except FileExistsError:
            continue
    raise ValueError("too many exports in that folder this minute")


def _write_new(path: str, text: str) -> None:
    with open(path, "x", encoding="utf-8", newline="\n") as handle:  # never overwrites
        handle.write(text)


CHECKPOINT_LABEL_MAX = 60


def checkpoint_label(label: Any) -> str:
    """A checkpoint's name: one line of plain text, 1 to 60 characters (ADR-0048)."""
    text = " ".join(str(label).split())
    if not text or len(text) > CHECKPOINT_LABEL_MAX or any(ord(ch) < 32 for ch in text):
        raise ValueError(f"give the checkpoint a name of 1 to {CHECKPOINT_LABEL_MAX} characters")
    return text


def restore_paths(paths: Any) -> set[tuple[str, str]]:
    """``root/rel`` strings from a restore preview, checked: a known root and a safe relative path."""
    if not isinstance(paths, list) or not paths or len(paths) > 10_000:
        raise ValueError("choose at least one file to restore")
    chosen: set[tuple[str, str]] = set()
    for item in paths:
        root, _, rel = str(item).partition("/")
        if root not in ALL_ROOTS or not rel:
            raise ValueError(f"not a file from this snapshot: {item}")
        try:
            validate_relative(rel)
        except PathEscapeError as exc:
            raise ValueError(f"not a file from this snapshot: {item}") from exc
        chosen.add((root, rel))
    return chosen


WHATS_NEW_MAX = 4000


def whats_new(changelog: str, version: str) -> str:
    """The ``## [version]`` section of the changelog, without its heading, at most 4000 characters."""
    lines = changelog.splitlines()
    heading = f"## [{version}]"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().startswith(heading))
    except StopIteration:
        return ""
    section = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        section.append(line)
    text = "\n".join(section).strip()
    return text if len(text) <= WHATS_NEW_MAX else text[: WHATS_NEW_MAX - 1].rstrip() + "…"


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(512 * 1024)
    except OSError:
        return ""


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


class KeepsakeApp:
    UNINSTALL_OP_TIMEOUT = 300.0  # seconds to wait for Steam to remove a shortcut before giving up (nothing deleted)

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
        host: str = "decky",
    ) -> None:
        # Which host runs this core (ADR-0038). Decky's main.py keeps the default; keepsake.host passes its own.
        self.host = host if host in hosts.HOSTS else "decky"
        self._graph_base_url = graph_base_url
        self._google_transport = google_transport
        self._google_api = google_api  # tests point this at a fake Drive
        self._endpoint_transport = endpoint_transport
        self.credentials = CredentialStore(paths.settings_dir)
        self.google_tokens = TokenManager(
            TokenStore(paths.settings_dir, GOOGLE.token_file),
            lambda: clients.google_client(self.credentials.load("gdrive"))[0],
            transport=google_transport,
            provider=GOOGLE,
            client_secret=lambda client_id: clients.google_secret_for(client_id, self.credentials.load("gdrive")),
        )
        self.paths = paths
        self.home = home
        self._games: dict[str, Any] | None = None
        self.remote_copies = remotecopies.RemoteCopies(paths.runtime_dir)
        self.manifest = manifest.ManifestStore(paths.runtime_dir, download=download)
        self.game_configs = GameConfigStore(paths.settings_dir)
        self._auto_refresh_manifest = auto_refresh_manifest
        self._manifest_lock = asyncio.Lock()
        self._import_all: dict[str, Any] = {"running": False, "done": 0, "total": 0, "games": {}, "summary": {}}
        self._import_cancel = False
        self.net_locations = remote.LocationStore(paths.settings_dir, self.credentials)
        self._net: dict[str, Any] = {"running": False}
        self._net_cancel = False
        self._net_connect: remote.Connector = remote._connect  # tests use a scripted server
        self._smb_connect: smbshare.Connector = smbshare._connect  # and a fake share
        self._lan_sockets: lanfind.SocketFactory = lanfind._udp  # and fake answers (ADR-0066)
        # Network ISOs used in place (ADR-0067): open mounts by id, and seams for tests.
        self._net_mounts: dict[str, netfuse.Mount] = {}
        self._netfuse_available: Callable[[], str | None] = netfuse.available
        self._netfuse_mount: Callable[[str, netfuse.Handler], netfuse.Mount] = netfuse.Mount
        self._udisks_runner: udisks.Runner = udisks.run
        self._net_resolve: remote.Resolver = remote._resolve
        self._pc_processes: Callable[[], list[str]] = pcwatch.list_processes  # PC hosts only; tests use a fake
        self._manifest_progress: dict[str, Any] = {"stage": "idle", "running": False}
        self._background: list[asyncio.Task[Any]] = []
        self.token_store = TokenStore(paths.settings_dir)
        self.tokens = TokenManager(
            self.token_store,
            lambda: clients.onedrive_client_id(self.settings.get("onedriveClientId")),
            transport=transport,
        )
        self._transport = transport
        self._signin: DeviceCodeFlow | LoopbackFlow | None = None
        self._signin_probe: BrowserProbe | None = None
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
        self._fetch = fetch  # Advisor's sources use the same injected fetcher, so tests never reach the network
        self._freeze_lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._notice: dict[str, Any] | None = None
        self._signin_warned = False
        # v2 Core (slice 13, ADR-0012, ADR-0024): lifecycle bus, per-game locks, module registry, state database.
        self.bus = EventBus()
        self.locks = GameLocks()
        self._uninstall_job: dict[str, Any] | None = None
        self._uninstall_cancel = False
        self._op_waiters: dict[int, asyncio.Future[tuple[bool, dict[str, Any]]]] = {}
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
        self.advisor: Advisor | None = None

        async def advisor_start() -> None:
            home = discovery.real_home(self.home)
            advisor = Advisor(
                self.paths.settings_dir,
                os.path.join(self.paths.runtime_dir, "advisor-cache"),
                os.environ.get("DECKY_HOME") or os.path.join(home, "homebrew"),
                home,
                os.environ.get("DECKY_USER") or os.path.basename(home.rstrip("/")),
                self._advisor_map_game,
                fetch_reports=lambda appid, name: deckverified.fetch(appid, name, self._fetch),
                anticheat_fetch=lambda: anticheat.download(self._fetch),
                installed_tools=lambda: advisor_compat.installed_ge_proton(discovery.steam_roots(self.home, self.host)),
                ai_key=lambda provider: str(self.credentials.load(provider)["apiKey"]),
                pcgw_client=self._pcgw_client,
            )
            await asyncio.to_thread(advisor.detect)
            self.advisor = advisor

        async def advisor_stop() -> None:
            self.advisor = None

        async def advisor_load(advisor: Advisor, appid: int) -> None:
            try:
                await asyncio.to_thread(advisor.set_game, appid)
            except Exception as exc:  # noqa: BLE001 - advice must never disturb the game or Saves
                log_event(logging.WARNING, "advisor.load_failed", "Advisor could not load the game", error=str(exc))
                return
            await self.emit(ADVISOR_EVENT)

        async def advisor_game_started(payload: dict[str, Any]) -> None:
            # The running game, from the lifecycle bus (spec 8.1). Saves publishes this inside its launch
            # gate, so the work runs as a task and the handler returns at once: advice never delays a game.
            if self.advisor is not None:
                self._background.append(asyncio.create_task(advisor_load(self.advisor, int(payload["appid"]))))

        async def advisor_health() -> list[dict[str, Any]]:
            return self.advisor.health() if self.advisor else []

        self.registry.register(
            Module(
                "advisor",
                "Advisor",
                "Recommends settings for the game you play, from your device and community reports.",
                "Nothing outside its own settings and cache. It only recommends; you copy or apply advice yourself.",
                start=advisor_start,
                stop=advisor_stop,
                health=advisor_health,
                listeners={"game_started": advisor_game_started},
                # Its advice is built on handheld power and screen profiles: off by default on PCs (ADR-0038).
                default=None if self.host == "decky" else False,
            )
        )
        self.links: Links | None = None
        self.transfers: Transfers | None = None
        self.incoming: Incoming | None = None
        self.outgoing: Outgoing | None = None
        self.game_links: GameLinks | None = None
        self._sending: dict[str, dict[str, Any]] = {}  # games being prepared to send, by game key
        self.sys_root = "/sys"
        self.power_root = "/"  # where /sys/class/power_supply is read (tests point it elsewhere)
        self._games_running: set[int] = set()
        self._direct_last: dict[str, Any] | None = None
        self._device_results: dict[str, dict[str, Any]] = {}
        self.replication_port = replication_link.DEFAULT_PORT

        async def replication_start() -> None:
            me = replication_link.Identity(
                str(self.settings.get("deviceId")),
                str(self.settings.get("deviceName") or "Unnamed device"),
                await asyncio.to_thread(netinfo.own_macs, self.sys_root),
            )
            self.links = Links(
                me,
                PeerStore(os.path.join(self.paths.settings_dir, "replication-peers.json")),
                lambda: netinfo.bind_hosts(
                    str(self.settings.get("replicationAddress")), netinfo.local_addresses(self.proc_root)
                ),
                self.replication_port,
                discovery=True,
                on_change=self._replication_changed,
            )
            if self.settings.get("replicationListener") and replication_link.available():
                try:
                    await self.links.set_listener(True)
                except (ReplicationError, replication_link.LinkError, OSError) as exc:
                    log_event(logging.WARNING, "replication.listener_failed", "Listener not started", error=str(exc))
            self.transfers = Transfers(
                os.path.join(self.paths.runtime_dir, "replication-jobs.json"),
                self._replication_connect_for,
                conditions=self._replication_hold,
                on_change=self._replication_changed,
                on_finished=lambda job: self.incoming.job_finished(job) if self.incoming else None,
            )
            shares = Shares()
            self.outgoing = Outgoing(
                os.path.join(self.paths.runtime_dir, "replication-outgoing.json"),
                os.path.join(self.paths.runtime_dir, "replication-outgoing"),
                shares,
            )
            self.incoming = Incoming(
                os.path.join(self.paths.runtime_dir, "replication-incoming.json"),
                self.transfers,
                lambda kind, payload: self._ops().enqueue("replication", kind, payload),
                self._replication_places,
                on_done=self._replication_update_done,
                on_change=self._replication_changed,
                on_offer=self._replication_offer_arrived,
            )
            self.game_links = GameLinks(os.path.join(self.paths.runtime_dir, "replication-games.json"))
            restored = await asyncio.to_thread(self.outgoing.restore)
            self.links.handlers.update(
                {
                    **shares.handlers(),
                    "offer": self.incoming.handle_offer,
                    **directsync.handlers(self._direct_store, on_changed=self._direct_peer_changed),
                    "speed": devicechecks.serve_speed,  # the other side of the link speed check (ADR-0062)
                }
            )
            if restored:
                log_event(logging.INFO, "replication.offers_restored", "Offered games available again", count=restored)
            resumed = await self.transfers.start_up()
            if resumed:
                log_event(logging.INFO, "replication.resumed", "Transfers resumed after a restart", count=len(resumed))

        async def replication_stop() -> None:
            self.incoming = self.outgoing = None
            self.game_links = None
            transfers, self.transfers = self.transfers, None
            if transfers is not None:
                await transfers.shut_down()
            links, self.links = self.links, None
            if links is not None:
                await links.close()

        async def replication_game_started(payload: dict[str, Any]) -> None:
            self._games_running.add(int(payload.get("appid") or 0))

        async def replication_game_exited(payload: dict[str, Any]) -> None:
            self._games_running.discard(int(payload.get("appid") or 0))
            if self.transfers is not None:
                self.transfers.check_holds()  # a transfer that waited for the game carries on now
            found = self.game_links.for_appid(int(payload.get("appid") or 0)) if self.game_links else None
            if found and found[1].get("policy") != "off":
                try:
                    game = await self._linked_game(found[1])
                except ValueError:
                    return
                self._background.append(asyncio.create_task(self._scan_link(found[0], game)))

        async def replication_health() -> list[dict[str, Any]]:
            return replication_health_checks(self.links, self.host, self.proc_root)

        self.registry.register(
            Module(
                "replication",
                "Replication",
                "Links your own devices directly, never through the cloud: pair them once, then send games between "
                "them.",
                "Its own list of paired devices and their link keys. Later: games you send, into the folders you "
                "choose.",
                start=replication_start,
                stop=replication_stop,
                health=replication_health,
                listeners={"game_started": replication_game_started, "game_exited": replication_game_exited},
            )
        )
        self.registry.register(
            Module(
                "desktop",
                "Desktop",
                "Keepsake in Desktop Mode, with a tray icon.",
                "Desktop Mode shortcuts for Keepsake.",
                available=False,
            )
        )
        self.installer: Installer | None = None

        async def installer_start() -> None:
            if self.db is None or self.steam_ops is None:
                raise RuntimeError("the state database is not available")
            self.installer = Installer(
                self.db,
                self.steam_ops,
                self._library_root,
                self._prefix_for,
                home=lambda: discovery.real_home(self.home),
                running=lambda appid, prefix: bool(find_game_processes(appid, prefix, self.proc_root)),
                work_dir=os.path.join(self.paths.runtime_dir, "installer"),
                art=SteamGridDB(lambda: str(self.credentials.load("steamgriddb")["apiKey"])),
            )
            self.installer.on_released = self._net_mount_released
            removed = await asyncio.to_thread(self.installer.clean_downloads)
            if removed:
                log_event(logging.INFO, "installer.net_cleaned", "Left-over downloads removed", count=len(removed))
            try:
                resumed = await asyncio.to_thread(self.installer.resume)  # discs after a restart, then the queue
            except (InstallerError, udisks.UdisksError, OSError) as exc:
                log_event(logging.WARNING, "installer.resume_failed", "Installs not resumed", error=str(exc))
            else:
                if resumed:
                    log_event(logging.INFO, "installer.resumed", "Installs resumed after a restart", count=len(resumed))

        async def installer_stop() -> None:
            self._net_cancel = True
            self.installer = None

        async def installer_exit(payload: dict[str, Any]) -> None:
            if self.installer and payload.get("gameKey") is None:
                job = await asyncio.to_thread(self.installer.installer_exited, int(payload["appid"]))
                if job:
                    await self.emit(
                        "keepsake_toast", f"{job['title']}: choose the game's program in Keepsake, Installer."
                    )

        async def installer_health() -> list[dict[str, Any]]:
            ok = udisks.available()
            checks: list[dict[str, Any]] = [
                {
                    "id": "udisksctl",
                    "label": "ISO support",
                    "status": "ok" if ok else "warn",
                    "detail": "udisksctl found." if ok else "udisksctl is missing: install from folders only.",
                    "items": [],
                }
            ]
            if self.installer is None:
                return checks
            jobs = await asyncio.to_thread(self.installer.jobs)
            ops = await asyncio.to_thread(self._ops().list)
            checks.extend(installer_health_checks(jobs, ops, time.time()))
            return checks

        self.registry.register(
            Module(
                "installer",
                "Installer",
                "Installs games from ISO files, folders and installers into their own Steam shortcut.",
                "A temporary installer shortcut in Steam, then the same shortcut pointed at the game. The installer "
                "program itself writes the game into the folder you choose and the shortcut's prefix.",
                start=installer_start,
                stop=installer_stop,
                health=installer_health,
                listeners={"game_exited": installer_exit},
                # It creates Steam shortcuts through SteamClient, which only Decky reaches (P15, ADR-0038).
                available=self.host == "decky",
                unavailable_reason=None
                if self.host == "decky"
                else "The Installer needs Decky: it creates the game's Steam shortcut through Steam itself.",
            )
        )

    def _library_root(self) -> str:
        configured = str(self.settings.get("libraryRoot") or "").strip()
        return configured or os.path.join(discovery.real_home(self.home), "Games").replace(os.sep, "/")

    def _pcgw_client(self) -> PcgwClient | None:
        """The user's own PCGamingWiki bot login, or None until it is entered."""
        if not self.credentials.configured("pcgw"):
            return None
        c = self.credentials.load("pcgw")
        user_agent = f"Keepsake/{self.version} (+https://github.com/breakmylegs/keepsake)"
        return PcgwClient(str(c["username"]), str(c["password"]), user_agent)

    def _advisor_map_game(self, appid: int) -> dict[str, Any]:
        """For Advisor (worker thread): a game's name and, for a shortcut, the Steam app ID of its manifest entry."""
        games = (self._games or discovery.discover(self.home, self.host))["games"]
        # A streaming entry (ADR-0064) is not in shortcuts.vdf, so its app ID finds nothing here.
        game = next((g for g in games if g["appid"] == appid), None)
        if game is None and self._games is not None:
            # Installed since the last scan, perhaps: look once more before giving up.
            game = next((g for g in discovery.discover(self.home, self.host)["games"] if g["appid"] == appid), None)
        if game is None:
            return {"name": "", "kind": "unknown"}  # not in the Games list: general advice only, nothing looked up
        out: dict[str, Any] = {
            "name": game["name"],
            "kind": game["kind"],
            "launchOptions": game.get("launch_options") or "",
            "compatTool": game.get("compat_tool") or "",
        }
        if game["kind"] == "steam":
            out["steamAppid"] = appid
            return out
        index = self.manifest.load()
        match = manifest.match_game(index, game, self.game_configs.get(game["key"]))
        title = match.get("title")
        record = (index or {}).get("games", {}).get(title) if title else None
        out["manifestTitle"] = title
        if isinstance(record, dict) and isinstance(record.get("s"), int):
            out["steamAppid"] = record["s"]
        return out

    def _prefix_for(self, appid: int) -> str | None:
        for root in discovery.steam_roots(self.home, self.host):
            found = discovery.find_compatdata(int(appid), discovery.library_folders(root))
            if found:
                return found
        return None

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
        """Once after an update: the versions and that version's changelog section ("What's new", ADR-0049)."""
        notice, self._notice = self._notice, None
        if notice:
            path = os.path.join(self.paths.plugin_dir, "CHANGELOG.md")
            text = await asyncio.to_thread(_read_text, path)
            notice = {**notice, "notes": whats_new(text, str(notice.get("to", "")))}
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
            self._games = await asyncio.to_thread(discovery.discover, self.home, self.host)
            if self.host != "windows" and self.settings.get("otherLaunchers"):
                found = await asyncio.to_thread(launchers.discover_all, discovery.real_home(self.home))
                self._games = {**self._games, "games": [*self._games["games"], *found]}
                await asyncio.to_thread(self._emulator_defaults, found)
            counts: dict[str, int] = {}
            for game in self._games["games"]:
                counts[game["kind"]] = counts.get(game["kind"], 0) + 1
            log_event(logging.INFO, "discovery.scan", "Scanned games", roots=len(self._games["roots"]), **counts)
        mismatches = await asyncio.to_thread(discovery.load_mismatches, self.paths.runtime_dir)
        # Each shortcut's presence from the file and Steam's install state (ADR-0064). Steam Remote Play's
        # streaming entries are not in shortcuts.vdf, so they never reach this list.
        games = await asyncio.to_thread(self.remote_copies.apply, self._games["games"])
        return {**self._games, "games": games, "mismatches": mismatches}

    def _emulator_defaults(self, games: list[dict[str, Any]]) -> None:
        """An emulator found for the first time gets its save folders and a game key shared by every device.

        Written once, off by default; the user can change them like any game's settings (ADR-0051).
        """
        for game in games:
            if game.get("kind") != launchers.EMULATOR_KIND or self.game_configs.get(game["key"]).get("gameKey"):
                continue
            self.game_configs.update(
                game["key"],
                {
                    "gameKey": launchers.emulator_game_key(game),
                    "gameKeySource": "auto",
                    "customPaths": list(game.get("emulator_paths") or []),
                },
            )

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
        loop = asyncio.get_running_loop()
        last_sent: dict[str, Any] = {"at": 0.0, "stage": None}

        def progress(update: dict[str, Any]) -> None:
            # Runs in the worker thread. Keep the latest for polling. A new stage is sent at once;
            # updates within a stage at most twice a second.
            self._manifest_progress = {**update, "running": True}
            now = time.monotonic()
            if update["stage"] != last_sent["stage"] or now - last_sent["at"] >= MANIFEST_PROGRESS_SECONDS:
                last_sent.update(at=now, stage=update["stage"])
                snapshot = dict(self._manifest_progress)
                loop.call_soon_threadsafe(lambda: loop.create_task(self.emit(MANIFEST_PROGRESS_EVENT, snapshot)))

        async with self._manifest_lock:
            try:
                result = await asyncio.to_thread(self.manifest.refresh, bool(force), progress)
            finally:
                self._manifest_progress = {"stage": "idle", "running": False}
        await self.emit(MANIFEST_PROGRESS_EVENT, {"stage": "finished", "running": False, **result})
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

    async def manifest_progress(self) -> dict[str, Any]:
        """What a manifest refresh is doing now, for a page opened while one runs (the weekly one, say)."""
        return dict(self._manifest_progress)

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
        auto_enabled: list[str] = []
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
            if self._auto_sync_candidate(game, match, config, proposal):
                config = await self.update_game_config(game["key"], {"enabled": True, "enabledSource": "auto"})
                auto_enabled.append(game["name"])
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
                    "newer": newer_save(state) if config.get("enabled") else None,
                    "steamCloud": self._steam_cloud(game),
                    "enabledSource": config.get("enabledSource"),
                    "hasRegistry": bool(
                        index and match.get("title") and index["games"].get(match["title"], {}).get("r")
                    ),
                }
            )
        if auto_enabled:
            count = len(auto_enabled)
            log_event(logging.INFO, "steamcloud.auto_enable", "Synced Steam games without Steam Cloud", count=count)
            names = ", ".join(auto_enabled[:3]) + (f" and {count - 3} more" if count > 3 else "")
            await self.emit(
                "keepsake_toast",
                f"Now syncing {names}: Steam does not back up their saves. Turn any off in Keepsake's Games list.",
            )
        # Games needing attention first, then by name (Peter, 16 November 2026).
        mismatched = await asyncio.to_thread(discovery.load_mismatches, self.paths.runtime_dir)
        return ordering.order(out, mismatched)

    def _steam_cloud(self, game: dict[str, Any]) -> str | None:
        """Steam Cloud state for Steam apps when detection is on (slice 11), else None."""
        if game["kind"] != "steam" or not self.settings.get("steamCloudDetection"):
            return None
        return steamcloud.cloud_state(
            game.get("steam_root"), game.get("default_user"), int(game["appid"]), int(game.get("last_played") or 0)
        )

    def _auto_sync_candidate(
        self, game: dict[str, Any], match: dict[str, Any], config: dict[str, Any], proposal: Any
    ) -> bool:
        """A played Steam game with no Steam Cloud saves and known save locations, never switched by anyone.

        Steam games whose saves Steam Cloud keeps stay off until the user turns them on (ADR-0063).
        Only Steam games have a Steam Cloud state, so ``_steam_cloud`` also limits this to them.
        """
        return bool(
            self.settings.get("steamAutoSync")
            and self.registry.enabled("saves")
            and not config.get("enabled")
            and config.get("enabledSource") is None
            and proposal is None
            and match.get("gameKey")
            and match.get("method") in AUTO_SYNC_METHODS
            and self._steam_cloud(game) == steamcloud.NO_CLOUD
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
        windows_paths = resolve.platform_of(game) in resolve.WINDOWS_PLATFORMS  # case-insensitive names
        probe = identity.probe_for(roots, lambda root: windows_paths and root in resolve.WIN_ROOTS, resolve.expand)
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
        changes = dict(changes)
        if "enabled" in changes:
            changes.setdefault("enabledSource", "user")  # automatic switching on never overrides this (ADR-0063)
        config = await asyncio.to_thread(self.game_configs.update, key, changes)
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
        elif store == "direct":
            # No account: "signed in" means a paired device to sync with (ADR-0061).
            paired = bool(self.links and self.links.store.list())
            client_set, signed_in = True, paired
            problem = (
                None if paired else "Switch on Replication in Settings, Modules, and pair your other device in Devices."
            )
        else:
            manager = self._token_manager(store)
            client_set = bool(
                clients.google_client(self.credentials.load("gdrive"))[0]
                if store == "gdrive"
                else clients.onedrive_client_id(self.settings.get("onedriveClientId"))
            )
            signed_in = await asyncio.to_thread(manager.signed_in)
            problem = manager.last_error
        onedrive_client = bool(clients.onedrive_client_id(self.settings.get("onedriveClientId")))
        return {
            "clientIdSet": client_set,
            "signedIn": signed_in,
            "signingIn": self._signin is not None,
            "problem": problem,
            "store": store,
            "name": BACKEND_NAMES.get(store, store),
            "onedriveSignedIn": await asyncio.to_thread(self.tokens.signed_in),
            "googleSignedIn": await asyncio.to_thread(self.google_tokens.signed_in),
            "direct": self._direct_last,
            "directReady": bool(self.links and self.links.store.list()),
            # ADR-0032: with a built-in client the sign-in screens need no client ID, and
            # "Use my own client ID" moves under Advanced (shown open while one is saved).
            "builtInClient": {"onedrive": clients.onedrive_builtin(), "gdrive": clients.google_builtin()},
            # Which sign-in methods have a client (ADR-0044). Google needs a different client for each.
            "methods": {
                "onedrive": dict.fromkeys(("browser", "phone"), onedrive_client),
                "gdrive": {
                    "browser": clients.google_browser_builtin() or self.credentials.configured("gdrive"),
                    "phone": clients.google_phone_builtin() or self.credentials.configured("gdrive"),
                },
            },
            "ownClient": {
                "onedrive": bool(self.settings.get("onedriveClientId")),
                "gdrive": self.credentials.configured("gdrive"),
            },
        }

    async def start_signin(self, backend: str = "onedrive", method: str = "phone") -> dict[str, Any]:
        """Begin a sign-in. Only ever called from a user action (threat model T2).

        ``method`` "browser" is the authorization code flow with a loopback redirect, for a
        browser on this device (ADR-0044); "phone" is the device code flow with a QR code.
        """
        backend = "gdrive" if backend == "gdrive" else "onedrive"
        async with self._auth_lock:
            if self._signin is not None:
                self._signin.cancelled.set()
            flow: DeviceCodeFlow | LoopbackFlow
            if method == "browser":
                if backend == "gdrive":
                    client_id, secret = clients.google_browser_client(self.credentials.load("gdrive"))
                    flow = LoopbackFlow(
                        client_id,
                        self.google_tokens.store,
                        transport=self._google_transport,
                        provider=GOOGLE,
                        client_secret=secret,
                    )
                else:
                    flow = LoopbackFlow(
                        clients.onedrive_client_id(self.settings.get("onedriveClientId")),
                        self.token_store,
                        transport=self._transport,
                    )
            elif backend == "gdrive":
                client_id, secret = clients.google_client(self.credentials.load("gdrive"))
                flow = DeviceCodeFlow(
                    client_id,
                    self.google_tokens.store,
                    transport=self._google_transport,
                    provider=GOOGLE,
                    client_secret=secret,
                )
            else:
                flow = DeviceCodeFlow(
                    clients.onedrive_client_id(self.settings.get("onedriveClientId")),
                    self.token_store,
                    transport=self._transport,
                )
            shown = await asyncio.to_thread(flow.start)
            self._signin = flow
        log_event(logging.INFO, "auth.signin_started", "Sign-in started", backend=backend, method=method)
        self._background.append(asyncio.create_task(self._finish_signin(flow, backend)))
        return shown

    async def _finish_signin(self, flow: DeviceCodeFlow | LoopbackFlow, backend: str = "onedrive") -> None:
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
        if not httpcall.xml_available():
            raise StoreError(httpcall.XML_MISSING)
        c = self.credentials.load("webdav")
        if not self.credentials.configured("webdav"):
            raise StoreError("enter the WebDAV address, user name and password first")
        return WebDavStore(c["url"], c["username"], c["password"], transport=self._endpoint_transport(c["url"]))

    def _s3(self) -> S3Store:
        if not httpcall.xml_available():
            raise StoreError(httpcall.XML_MISSING)
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
        if backend == "direct":
            return LocalFolderStore(self._direct_root())  # this device's own copy of the history (ADR-0061)
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

    def _playtime(self) -> playtime.Recorder:
        eng = self._engine()
        return playtime.Recorder(self.paths.runtime_dir, self._store, eng.device_id, eng.seq.next)

    async def game_playtime(self, key: str) -> dict[str, Any]:
        """Time played across your devices, by device name (ADR-0049). Informational only (P4)."""
        game_key = (await self._snapshot_context(key))["gameKey"]
        eng = self._engine()
        found = await asyncio.to_thread(playtime.totals, eng.store, game_key)
        names = {
            str(m.get("deviceId")): str(m.get("deviceName")) for m in await asyncio.to_thread(eng.list_metas, game_key)
        }
        names[eng.device_id] = str(self.settings.get("deviceName") or "This device")
        return {
            "totalSeconds": found["totalSeconds"],
            "sessions": found["sessions"],
            "byDevice": sorted(
                ({"device": names.get(d, "Another device"), "seconds": s} for d, s in found["byDevice"].items()),
                key=lambda item: -item["seconds"],
            ),
        }

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
        running = await asyncio.to_thread(self._game_running, game)
        return {
            "game": game,
            "gameKey": match["gameKey"],
            "files": files,
            "roots": roots,
            "running": running,
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
        if self._game_running(game):
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

    async def snapshot_game(self, key: str, label: str | None = None) -> dict[str, Any]:
        """Take a manual snapshot. With a ``label`` it is a checkpoint (ADR-0048): always a new
        snapshot, even when nothing changed, pinned with that label so retention keeps it."""
        name = checkpoint_label(label) if label is not None else None
        ctx = await self._snapshot_context(key)
        eng = self._engine()
        with self.jobs.job("snapshot"):
            base_id = self._bases().get(ctx["gameKey"])
            base = await asyncio.to_thread(eng.get_meta, ctx["gameKey"], base_id) if base_id else None
            result = await asyncio.to_thread(
                eng.take, ctx["gameKey"], ctx["files"], ctx["roots"], "manual", base, force=name is not None
            )
            if name is not None and result["status"] == "published":
                await asyncio.to_thread(eng.pin, ctx["gameKey"], result["snapId"], None, name)
        if result["status"] == "published":
            self._set_base(ctx["gameKey"], result["snapId"])
        event = "snapshot.checkpoint" if name is not None else "snapshot.take"
        log_event(logging.INFO, event, "Snapshot taken", gameKey=ctx["gameKey"], status=result["status"])
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
        pin_records = await asyncio.to_thread(eng.pins, game_key)
        pins = {p["snapId"] for p in pin_records}
        labels = {p["snapId"]: str(p["label"]) for p in pin_records if isinstance(p.get("label"), str)}
        base = self._bases().get(game_key)
        summary = snap_summary
        latest: dict[str, dict[str, Any]] = {}
        for meta in metas:
            device = str(meta.get("deviceId") or meta.get("deviceName"))
            if device not in latest or meta["created"] > latest[device]["created"]:
                latest[device] = meta

        scrub = await asyncio.to_thread(read_json, os.path.join(self.paths.runtime_dir, SCRUB_FILE), {})
        found = ((scrub.get("games") or {}).get(game_key) or {}) if isinstance(scrub, dict) else {}
        return {
            # Snapshots the integrity check found damaged or missing in the cloud (ADR-0050).
            "damaged": sorted(set(found.get("bad") or []) | set(found.get("missing") or [])),
            "lastByDevice": [
                {"device": m.get("deviceName"), "created": m["created"], "kind": m["kind"], "snapId": m["snapId"]}
                for m in sorted(latest.values(), key=lambda m: m["created"], reverse=True)
            ],
            "gameKey": game_key,
            "snapshots": [
                {
                    **summary(m),
                    "pinned": m["snapId"] in pins,
                    "label": labels.get(m["snapId"]),
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

    async def restore_preview(self, key: str, snap_id: str) -> dict[str, Any]:
        """Each file restoring ``snap_id`` would add, replace or remove here. Changes nothing (ADR-0048)."""
        ctx = await self._snapshot_context(key)
        changes = await asyncio.to_thread(
            self._engine().restore_preview, ctx["gameKey"], str(snap_id), ctx["files"], ctx["roots"]
        )
        return {"snapId": str(snap_id), "changes": changes}

    async def restore_snapshot(self, key: str, snap_id: str, paths: list[str] | None = None) -> dict[str, Any]:
        """Restore a snapshot, or with ``paths`` (``root/rel`` as the preview lists them) only those files."""
        only = None if paths is None else restore_paths(paths)
        ctx = await self._snapshot_context(key)
        eng = self._engine()
        async with self.locks.hold(ctx["gameKey"], "saves"):
            with self.jobs.job("restore"):
                result = await asyncio.to_thread(
                    functools.partial(
                        eng.restore, ctx["gameKey"], str(snap_id), ctx["files"], ctx["roots"], ctx["running"], only=only
                    )
                )
                result = await self._after_restore(ctx, result)
        if only is None:
            self._set_base(ctx["gameKey"], str(snap_id))  # a partial restore leaves a mix, so the base stays
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
            return self._game_running(game)

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
        try:
            games = await self._games_for_appid(raw_id)
            appid = lifecycle.normalise_appid(raw_id)
        except (ValueError, TypeError):
            return {"handled": 0}
        # A game waiting for its prefix reset to finish (ADR-0052): no launch gate and no exit
        # save on the fresh, empty prefix; on exit the kept saves go back instead.
        waiting = {
            k
            for k, r in storage.resets(self.paths.runtime_dir).items()
            if r.get("stage") == "waiting" and r.get("appid") == appid
        }
        if waiting:
            if kind == "exit":
                for key in sorted(waiting):
                    self._background.append(asyncio.create_task(self._finish_prefix_reset(key)))
            games = [g for g in games if g["key"] not in waiting]
        if not games:
            # Apps Saves does not sync (an installer shortcut, or any game for Advisor) still reach other modules.
            event = {"start": "game_started", "exit": "game_exited"}.get(kind)
            if event:
                await self.bus.publish(event, {"gameKey": None, "appid": lifecycle.normalise_appid(raw_id)})
        if not self.registry.enabled("saves"):
            return {"handled": 0}  # Saves switched off: no launch gate, no exit save
        if self.host != "decky" and kind == "start":
            # A PC host only learns of a game once it is running (ADR-0038): record it, never pull under it (P6).
            for game in games:
                self._background.append(asyncio.create_task(self._pc_started(game)))
            return {"handled": len(games)}
        for game in games:
            if kind == "start" and game["key"] not in self._launching:
                self._launching.add(game["key"])
                self._background.append(asyncio.create_task(self._launch(game)))
            elif kind == "exit":
                self._background.append(asyncio.create_task(self._exit(game)))
        return {"handled": len(games)}

    async def _pc_started(self, game: dict[str, Any]) -> None:
        try:
            ctx = await self._sync_context(game["key"])
        except (ValueError, SnapshotError) as exc:
            log_event(logging.WARNING, "lifecycle.pc_start", "Game seen running, not synced", error=str(exc))
            return
        self._record_session(ctx.game_key, lastStart=time.time())
        await self.bus.publish("game_started", {"gameKey": ctx.game_key, "appid": game["appid"]})

    def _game_running(self, game: Mapping[str, Any]) -> bool:
        """Whether the game runs now. Decky reads /proc; a PC host lists the user's processes (ADR-0038)."""
        if game.get("kind") in (*launchers.LAUNCHER_KINDS, launchers.EMULATOR_KIND):
            return procs.launcher_running(dict(game), self.proc_root)  # by Wine prefix or emulator (ADR-0051)
        if self.host == "decky":
            return bool(find_game_processes(int(game["appid"]), game.get("prefix"), self.proc_root))
        return pcwatch.game_running(game, self._pc_processes(), discovery.real_home(self.home))

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
            await self._direct_exchange(timeout / 2)  # direct sync: fetch the other device's newest first
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
                lambda: not self._game_running(game),
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
            self._direct_pushed()
            session = self._sessions().get(ctx.game_key, {})
            now = time.time()
            self._record_session(ctx.game_key, lastEnd=now)
            start = float(session.get("lastStart") or 0)
            if start > float(session.get("lastEnd") or 0):
                await self._record_playtime(ctx.game_key, start, now)
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

    async def _record_playtime(self, game_key: str, start: float, end: float) -> None:
        try:
            await asyncio.to_thread(self._playtime().record, game_key, start, end)
        except (OSError, StoreError, SnapshotError) as exc:
            log_event(logging.INFO, "playtime.failed", "Playtime not recorded", error=str(exc))

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

    async def bring_newer(self, key: str) -> dict[str, Any]:
        """The "Get it now" button: bring in the newer save from another device, outside a launch (ADR-0049)."""
        ctx = await self._sync_context(key)
        async with self.locks.hold(ctx.game_key, "saves"):
            with self.jobs.job("sync"):
                result = await asyncio.to_thread(self._sync().fetch_newer, ctx)
        log_event(
            logging.INFO, "sync.pull", "Brought in a newer save", gameKey=ctx.game_key, action=result.get("action")
        )
        return result

    async def sync_push(self, key: str) -> dict[str, Any]:
        ctx = await self._sync_context(key)
        async with self.locks.hold(ctx.game_key, "saves"):
            with self.jobs.job("sync"):
                result = await asyncio.to_thread(self._sync().push, ctx)
        self._direct_pushed()
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
        await self._direct_exchange()
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
                        state = sync.state.get(ctx.game_key)
                        if game["kind"] in AUTO_PULL_KINDS and (newer_save(state) or not state.get("base")):
                            # Keepsake cannot see these games start, so a newer save from another device (or
                            # the first copy, on a device that never synced it) is brought in here, by the
                            # launch decision table: only if nothing changed here and the game is not running;
                            # anything else is a conflict for the user (P1, P6; ADR-0051).
                            pulled = await asyncio.to_thread(sync.fetch_newer, ctx)
                            outcome = {**outcome, "pulled": pulled.get("action")}
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
        try:
            await asyncio.to_thread(self._playtime().flush)  # sessions recorded while offline
        except (OSError, StoreError, SnapshotError):
            pass
        await self._weekly_scrub()
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
        newer = [
            {"key": game["key"], "name": game["name"], **found}
            for game, gk in enabled
            if (found := newer_save(states.get(gk) or {}))
        ]
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
            "newer": newer[:3],  # "Newer save from <device>" before you play (ADR-0049)
            "setupComplete": bool(self.settings.get("setupComplete")),
            "tipsDismissed": bool(self.settings.get("tipsDismissed")),
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
        for side in details.get("sides") or []:
            if side["side"] == "local":
                side["device"] = self.settings.get("deviceName") or "This device"
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
            "pythonModules": {"xml": httpcall.xml_available(), "sqlite3": statedb_sqlite_available()},
            "store": self.settings.get("snapshotStore"),
            "integrity": await asyncio.to_thread(read_json, os.path.join(self.paths.runtime_dir, SCRUB_FILE), {}),
        }
        return health.run(facts)

    # Storage (R5, ADR-0052): disk use, shader cache, reset prefix and keep saves

    def _saves_bytes(self, game: dict[str, Any]) -> int:
        try:
            config = self.game_configs.get(game["key"])
            index = self.manifest.load()
            match = manifest.match_game(index, game, config)
            record = index["games"].get(match["title"]) if index and match.get("title") else None
            if record is None and not config.get("customPaths"):
                return 0
            preview = resolve.preview(game, match.get("title"), record, config, self.home, 0, False)
            return int(preview.get("totalBytes") or preview.get("bytes") or 0)
        except (OSError, ValueError, KeyError):
            return 0

    async def storage_usage(self, key: str | None = None) -> dict[str, Any]:
        """Disk use per game: install, prefix, shader cache and saves. Biggest first; stops after a minute."""
        games = [g for g in (await self.discover_games())["games"] if key is None or g["key"] == key]
        deadline = time.monotonic() + (storage.SIZE_SECONDS if key else 60.0)
        rows, skipped = [], 0
        for game in games:
            if time.monotonic() > deadline:
                skipped += 1
                continue
            saves = await asyncio.to_thread(self._saves_bytes, game)
            left = max(1.0, min(storage.SIZE_SECONDS, deadline - time.monotonic()))
            row = await asyncio.to_thread(storage.usage, game, saves, left, discovery.real_home(self.home))
            row["reset"] = storage.resets(self.paths.runtime_dir).get(game["key"])
            rows.append(row)
        rows.sort(key=lambda r: -r["totalBytes"])
        return {"games": rows, "notMeasured": skipped}

    async def _storage_game(self, key: str) -> dict[str, Any]:
        game = await self._game(key)
        if await asyncio.to_thread(self._game_running, game):
            raise ValueError("quit the game first")
        return game

    async def clear_shader_cache(self, key: str) -> dict[str, Any]:
        """Remove the game's shader cache. Steam rebuilds it at the next launch (ADR-0052)."""
        game = await self._storage_game(key)
        try:
            freed = await asyncio.to_thread(storage.clear_shader_cache, game)
        except storage.StorageError as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "storage.shader_cache", "Shader cache cleared", key=key, freed=freed)
        return {"ok": True, "freed": freed}

    async def reset_prefix(self, key: str) -> dict[str, Any]:
        """Move the game's Proton prefix aside after keeping a verified copy of its saves (ADR-0052)."""
        if key in storage.resets(self.paths.runtime_dir):
            raise ValueError("a reset is already waiting for this game")
        game = await self._storage_game(key)
        if game.get("exe_inside_prefix"):
            raise ValueError("this game is installed inside its prefix, so resetting it would remove the game")
        prefix = storage.compat_prefix(game)
        if prefix is None:
            raise ValueError("only a game in its own Steam Proton prefix can be reset")
        ctx = await self._snapshot_context(key)
        if ctx["running"]:
            raise ValueError("quit the game first")
        folder = os.path.join(self.paths.runtime_dir, "prefix-resets")
        await asyncio.to_thread(os.makedirs, folder, exist_ok=True)
        blob = os.path.join(folder, f"{uuid.uuid4().hex[:12]}.zip")
        eng = self._engine()
        async with self.locks.hold(ctx["gameKey"], "saves"):
            with self.jobs.job("snapshot"):
                try:
                    meta = await asyncio.to_thread(eng.keep_copy, ctx["gameKey"], ctx["files"], ctx["roots"], blob)
                except BaseException:
                    if os.path.exists(blob):
                        os.unlink(blob)  # never leave a half-made or unverified copy behind
                    raise
                try:
                    old = await asyncio.to_thread(storage.move_prefix_aside, prefix)
                except (OSError, storage.StorageError) as exc:
                    os.unlink(blob)
                    raise ValueError(f"the prefix could not be moved: {exc}") from exc
        record = {
            "stage": "waiting",
            "prefix": prefix,
            "old": old,
            "gameKey": ctx["gameKey"],
            "blob": blob,
            "meta": meta,
            "started": time.time(),
            "appid": game["appid"],
        }
        data = storage.resets(self.paths.runtime_dir)
        data[key] = record
        await asyncio.to_thread(storage.save_resets, self.paths.runtime_dir, data)
        log_event(logging.WARNING, "storage.prefix_reset", "Prefix moved aside; saves kept", key=key)
        return {"ok": True, "stage": "waiting"}

    async def cancel_prefix_reset(self, key: str) -> dict[str, Any]:
        """Put the old prefix back, before the saves were restored into a fresh one."""
        record = storage.resets(self.paths.runtime_dir).get(key)
        if not record or record.get("stage") != "waiting":
            raise ValueError("there is no waiting reset for this game")
        await self._storage_game(key)
        try:
            await asyncio.to_thread(storage.put_prefix_back, record["prefix"], record["old"])
        except (OSError, storage.StorageError) as exc:
            raise ValueError(f"the old prefix could not be put back: {exc}") from exc
        await asyncio.to_thread(self._forget_reset, key)
        log_event(logging.INFO, "storage.prefix_reset_cancelled", "Old prefix put back", key=key)
        return {"ok": True}

    async def delete_old_prefix(self, key: str) -> dict[str, Any]:
        """Free the space of a prefix a finished reset moved aside."""
        record = storage.resets(self.paths.runtime_dir).get(key)
        if not record or record.get("stage") != "restored":
            raise ValueError("the reset has not finished yet")
        try:
            freed = await asyncio.to_thread(storage.delete_old_prefix, record["old"], record["prefix"])
        except (OSError, storage.StorageError) as exc:
            raise ValueError(str(exc)) from exc
        await asyncio.to_thread(self._forget_reset, key)
        log_event(logging.INFO, "storage.old_prefix_deleted", "Old prefix deleted", key=key, freed=freed)
        return {"ok": True, "freed": freed}

    def _forget_reset(self, key: str) -> None:
        data = storage.resets(self.paths.runtime_dir)
        record = data.pop(key, None)
        storage.save_resets(self.paths.runtime_dir, data)
        if record and record.get("blob") and os.path.exists(record["blob"]):
            os.unlink(record["blob"])

    async def _finish_prefix_reset(self, key: str) -> dict[str, Any]:
        """After the first launch on a fresh prefix: put the kept saves back (with a pre-restore snapshot)."""
        record = storage.resets(self.paths.runtime_dir).get(key)
        if not record or record.get("stage") != "waiting":
            return {"status": "none"}
        game = await self._game(key)
        gone = await asyncio.to_thread(
            lifecycle.wait_for, lambda: not self._game_running(game), lifecycle.EXIT_WAIT_SECONDS
        )
        if not gone or not os.path.isdir(os.path.join(record["prefix"], "pfx", "drive_c")):
            return {"status": "waiting"}  # still running, or Proton has not built the new prefix yet
        await self.discover_games(refresh=True)
        ctx = await self._snapshot_context(key)
        eng = self._engine()
        async with self.locks.hold(record["gameKey"], "saves"):
            with self.jobs.job("restore"):
                result = await asyncio.to_thread(
                    eng.restore_copy,
                    record["gameKey"],
                    record["blob"],
                    record["meta"],
                    ctx["files"],
                    ctx["roots"],
                    ctx["running"],
                )
        data = storage.resets(self.paths.runtime_dir)
        data[key] = {**record, "stage": "restored", "restored": time.time()}
        await asyncio.to_thread(storage.save_resets, self.paths.runtime_dir, data)
        await self.emit("keepsake_toast", f"{game['name']}: your saves are back in the fresh prefix.")
        log_event(logging.INFO, "storage.prefix_reset_done", "Saves put back after a prefix reset", key=key)
        return {"status": "restored", **{k: v for k, v in result.items() if k in ("status", "prerestore")}}

    # Trust (R3, ADR-0050): cloud integrity and export

    async def scrub_cloud(self, full: bool = False) -> dict[str, Any]:
        """Verify the cloud snapshots of every synced game. Changes nothing.

        The weekly check covers heads, pins and every device's base (what restores rely on);
        ``full`` checks every snapshot whose files are kept.
        """
        eng = self._engine()
        report: dict[str, Any] = {"lastRun": time.time(), "full": bool(full), "games": {}}
        seen: set[str] = set()
        with self.jobs.job("scrub"):
            for game, config, gk in await self._matched():
                if not gk or gk in seen or not config.get("enabled"):
                    continue
                seen.add(gk)
                try:
                    only: set[str] | None = None
                    if not full:
                        metas = await asyncio.to_thread(eng.list_metas, gk)
                        pins = {p["snapId"] for p in await asyncio.to_thread(eng.pins, gk)}
                        bases = set((await asyncio.to_thread(eng.cloud_bases, gk)).values())
                        only = retention.heads(metas) | pins | bases
                    result = await asyncio.to_thread(eng.scrub, gk, only)
                except StoreError as exc:
                    result = {"checked": 0, "bad": [], "missing": [], "error": str(exc)}
                report["games"][gk] = {"name": game["name"], "key": game["key"], **result}
        await asyncio.to_thread(atomic_write_json, os.path.join(self.paths.runtime_dir, SCRUB_FILE), report)
        damaged = sum(len(g["bad"]) + len(g["missing"]) for g in report["games"].values())
        log_event(
            logging.WARNING if damaged else logging.INFO,
            "integrity.scrub",
            "Cloud integrity checked",
            games=len(report["games"]),
            damaged=damaged,
        )
        return report

    async def _weekly_scrub(self) -> None:
        last = float(
            (await asyncio.to_thread(read_json, os.path.join(self.paths.runtime_dir, SCRUB_FILE), {})).get("lastRun")
            or 0
        )
        if time.time() - last >= SCRUB_INTERVAL:
            try:
                await self.scrub_cloud(full=False)
            except (StoreError, SnapshotError, OSError) as exc:
                log_event(logging.INFO, "integrity.scrub_failed", "Integrity check skipped", error=str(exc))

    async def repair_snapshot(self, key: str) -> dict[str, Any]:
        """Repair after a damaged cloud copy: save a fresh snapshot of this device's files under a new id.

        Write-once objects are never fixed in place (P2); the new snapshot becomes this device's base.
        """
        ctx = await self._snapshot_context(key)
        eng = self._engine()
        async with self.locks.hold(ctx["gameKey"], "saves"):
            with self.jobs.job("snapshot"):
                base_id = self._bases().get(ctx["gameKey"])
                base = await asyncio.to_thread(eng.get_meta, ctx["gameKey"], base_id) if base_id else None
                result = await asyncio.to_thread(
                    functools.partial(
                        eng.take,
                        ctx["gameKey"],
                        ctx["files"],
                        ctx["roots"],
                        "manual",
                        base,
                        force=True,
                        flags=["repair"],
                    )
                )
        if result["status"] == "published":
            self._set_base(ctx["gameKey"], result["snapId"])
        log_event(
            logging.INFO, "snapshot.repair", "Fresh snapshot saved", gameKey=ctx["gameKey"], status=result["status"]
        )
        result.pop("meta", None)
        return result

    async def export_snapshots(self, folder: str, scope: str = "latest", key: str | None = None) -> dict[str, Any]:
        """Export snapshots as plain zips to a folder the user chose (a USB drive, an SD card): no lock-in.

        Creates ``Keepsake export <date>`` inside ``folder`` with one folder per game, each zip
        verified against its metadata, an ``index.json`` and a ``README.txt``. Only new files are
        written; nothing is ever overwritten. ``scope`` is ``latest`` or ``all``.
        """
        target_root = export_folder(folder)
        if scope not in ("latest", "all"):
            raise ValueError("choose the latest snapshot of each game, or all of them")
        eng = self._engine()
        chosen: list[tuple[dict[str, Any], str]] = []
        seen: set[str] = set()
        for game, config, gk in await self._matched():
            if not gk or gk in seen or (key is None and not config.get("enabled")) or (key and game["key"] != key):
                continue
            seen.add(gk)
            chosen.append((game, gk))
        if not chosen:
            raise ValueError("there is nothing to export: no synced game was found")
        stamp = time.strftime("%Y-%m-%d %H%M", time.localtime())
        out_dir = await asyncio.to_thread(_new_folder, target_root, f"Keepsake export {stamp}")
        index: list[dict[str, Any]] = []
        with self.jobs.job("export"):
            for game, gk in chosen:
                metas = await asyncio.to_thread(eng.list_metas, gk)
                pruned = await asyncio.to_thread(eng.pruned, gk)
                kept = [m for m in metas if m["snapId"] not in pruned]
                picked = kept[-1:] if scope == "latest" else kept
                game_dir = os.path.join(out_dir, safe_name(game["name"]))
                await asyncio.to_thread(os.makedirs, game_dir, exist_ok=True)
                for meta in picked:
                    name = f"{meta['created'][:10]} {meta['snapId']}.zip"
                    await asyncio.to_thread(eng.download_verified, gk, meta["snapId"], os.path.join(game_dir, name))
                    index.append(
                        {
                            "game": game["name"],
                            "gameKey": gk,
                            "snapId": meta["snapId"],
                            "created": meta["created"],
                            "device": meta.get("deviceName"),
                            "zip": f"{safe_name(game['name'])}/{name}",
                            "files": [f"{f['root']}/{f['rel']}" for f in meta["files"]],
                        }
                    )
        await asyncio.to_thread(_write_new, os.path.join(out_dir, "index.json"), json.dumps(index, indent=2) + "\n")
        await asyncio.to_thread(_write_new, os.path.join(out_dir, "README.txt"), EXPORT_README)
        log_event(logging.INFO, "export.snapshots", "Snapshots exported", games=len(chosen), snapshots=len(index))
        return {"ok": True, "folder": out_dir, "games": len(chosen), "snapshots": len(index)}

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

    # Import every game at once (Peter, 16 November 2026)

    def import_all_status(self) -> dict[str, Any]:
        return dict(self._import_all)

    async def ludusavi_import_all(self, root: str, mode: str) -> dict[str, Any]:
        """Start importing the latest (or every) backup of every readable game, one game at a time, in the background.

        Games not found on this device or not in the manifest are included: an import only adds History
        snapshots under the game's key and never touches saves, so the backups are ready for a later install
        or the other device. A failing game is recorded and the rest carry on; already-imported backups are
        skipped, so running it again is safe. ``ludusavi_import_cancel`` stops between games.
        """
        if mode not in ("latest", "all"):
            raise ValueError("choose the latest backup or all backups")
        if self._import_all.get("running"):
            raise ValueError("an import of every game is already running")
        scanned = await self.ludusavi_scan(root)
        games = [g for g in scanned["games"] if not g.get("error") and g.get("backups")]
        self._import_all = {
            "running": True,
            "cancelled": False,
            "mode": mode,
            "done": 0,
            "total": len(games),
            "current": None,
            "games": {},
            "summary": {"imported": 0, "already-imported": 0, "nothing-to-import": 0, "failed": 0},
        }
        self._import_cancel = False
        self._background.append(asyncio.create_task(self._run_import_all(scanned["root"], games, mode)))
        return self.import_all_status()

    async def _run_import_all(self, root: str, games: list[dict[str, Any]], mode: str) -> None:
        state = self._import_all
        try:
            for game in games:
                if self._import_cancel:
                    state["cancelled"] = True
                    break
                state["current"] = game["name"]
                await self.emit(IMPORT_PROGRESS_EVENT, self.import_all_status())
                ids = (
                    [b["id"] for b in game["backups"]][-1:] if mode == "latest" else [b["id"] for b in game["backups"]]
                )
                try:
                    outcome = await self.ludusavi_import(root, game["folder"], ids, game["gameKey"])
                    results = outcome["results"]
                    error = next((r.get("error") for r in results if r["status"] == "error"), None)
                except Exception as exc:  # noqa: BLE001 - one game failing must not stop the rest
                    results, error = [], str(exc)
                verdict = import_verdict(results, error)
                state["games"][game["folder"]] = {
                    "name": game["name"],
                    "status": verdict,
                    "error": error,
                    "results": results,
                }
                state["summary"][verdict] += 1
                state["done"] += 1
        finally:
            state["running"], state["current"] = False, None
            log_event(logging.INFO, "import.ludusavi_all", "Import of every game finished", **state["summary"])
            await self.emit(IMPORT_PROGRESS_EVENT, self.import_all_status())

    async def ludusavi_import_cancel(self) -> dict[str, Any]:
        self._import_cancel = True
        return self.import_all_status()

    async def ludusavi_import_status(self) -> dict[str, Any]:
        return self.import_all_status()

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

    # Games you can stream from another device: Steam Remote Play's entries (ADR-0064)

    async def remote_copies_report(self, entries: Any) -> dict[str, Any]:
        """The frontend's reading of Steam's library. Warns about local shortcuts hidden from elsewhere."""
        outcome = await asyncio.to_thread(self.remote_copies.save_report, entries)
        for found in outcome["newlyHidden"][:3]:
            await self.emit(
                "keepsake_toast",
                f"{found['name']} was hidden in Steam, perhaps from your other device. "
                "Open Keepsake's Games page to show it again.",
            )
        outcome["tidied"] = 0
        if self.settings.get("tidyAutomatically") and self.settings.get("streamTidyVerified"):
            log = await asyncio.to_thread(self.remote_copies.tidy_log)
            left = {int(k) for k, v in log["hidden"].items() if v.get("state") == "undone"}
            fresh = [c["appid"] for c in await self._copies() if c["presence"] == discovery.REMOTE and not c["hidden"]]
            fresh = [a for a in fresh if a not in left]  # a copy the user brought back stays
            if fresh:
                outcome["tidied"] = (await self.tidy_copies(fresh, automatic=True))["queued"]
        return outcome

    async def _copies(self) -> list[dict[str, Any]]:
        games = (await self.discover_games())["games"]
        return await asyncio.to_thread(self.remote_copies.copies, games)

    async def remote_copies_status(self) -> dict[str, Any]:
        """Every streaming entry, the tidy-up log, and whether Steam has reported yet."""
        report = await asyncio.to_thread(self.remote_copies.report)
        log = await asyncio.to_thread(self.remote_copies.tidy_log)
        return {
            "reportAt": report.get("at"),
            "copies": await self._copies(),
            "log": log["hidden"],
            "automatic": bool(self.settings.get("tidyAutomatically")),
            "tidyAvailable": bool(self.settings.get("streamTidyVerified")),  # off until A201 is verified
            "newlyHidden": [
                {"appid": e["appid"], "name": e["name"]}
                for e in report["entries"]
                if e["steam"] == discovery.LOCAL and e["hidden"]
            ],
        }

    async def tidy_copies(self, appids: list[int], automatic: bool = False) -> dict[str, Any]:
        """Hide the chosen streaming entries in Steam. Only entries Steam itself says are on another device."""
        if not self.settings.get("streamTidyVerified"):
            raise ValueError("hiding streaming entries is not available yet: it may hide the game on your other device")
        if not isinstance(appids, list) or not appids:
            raise ValueError("choose at least one game")
        certain = {c["appid"]: c for c in await self._copies() if c["presence"] == discovery.REMOTE}
        refused = [a for a in appids if a not in certain]
        if refused and not automatic:
            raise ValueError("some of those are not certainly streamed from another device, so nothing was changed")
        queued = 0
        for appid in [a for a in appids if a in certain]:
            op_id = await asyncio.to_thread(
                self._ops().enqueue, "core", "set-hidden", {"appid": int(appid), "hidden": True}
            )
            await asyncio.to_thread(self.remote_copies.record, int(appid), certain[appid]["name"], "pending", op_id)
            queued += 1
        if queued:
            await self.emit("keepsake_steam_ops")
        log_event(logging.INFO, "remotecopies.tidy", "Tidy-up queued", count=queued, automatic=automatic)
        return {"queued": queued}

    async def undo_tidy(self) -> dict[str, Any]:
        """Show again everything a tidy-up hid, and remember not to hide those again by itself."""
        log = await asyncio.to_thread(self.remote_copies.tidy_log)
        queued = 0
        for key, entry in log["hidden"].items():
            if entry.get("state") in ("pending", "hidden", "came-back"):
                op_id = await asyncio.to_thread(
                    self._ops().enqueue, "core", "set-hidden", {"appid": int(key), "hidden": False}
                )
                await asyncio.to_thread(
                    self.remote_copies.record, int(key), str(entry.get("name", "")), "undone", op_id
                )
                queued += 1
        if queued:
            await self.emit("keepsake_steam_ops")
        log_event(logging.INFO, "remotecopies.undo", "Tidy-up undone", count=queued)
        return {"queued": queued}

    async def unhide_local(self, appid: int) -> dict[str, Any]:
        """Show a hidden local shortcut again (the guard's one-press fix). Only shortcuts Steam says are local."""
        verdict = (await asyncio.to_thread(self.remote_copies.steam_verdicts)).get(int(appid))
        if not verdict or verdict["steam"] != discovery.LOCAL:
            raise ValueError("that is not a shortcut on this device")
        op_id = await asyncio.to_thread(
            self._ops().enqueue, "core", "set-hidden", {"appid": int(appid), "hidden": False}
        )
        await self.emit("keepsake_steam_ops")
        return {"id": op_id}

    async def _remote_shortcuts_probe(self) -> dict[str, Any]:
        games = (await self.discover_games())["games"]
        copies = await asyncio.to_thread(self.remote_copies.copies, games)
        log = await asyncio.to_thread(self.remote_copies.tidy_log)
        found = remotecopies.check(copies, games, lambda key: bool(self.game_configs.get(key).get("enabled")), log)
        return {**found, "reportAt": (await asyncio.to_thread(self.remote_copies.report)).get("at")}

    # Uninstall (ADR-0065): Steam games through Steam's own uninstall; non-Steam games here, folder by folder

    def _uninstall_places(self) -> uninstall.Places:
        home = discovery.real_home(self.home)
        roots = discovery.steam_roots(self.home, self.host)
        libraries = [lib for root in roots for lib in discovery.library_folders(root)]
        removable = []
        try:
            with open(os.path.join(self.proc_root, "self", "mounts"), encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].startswith(("/run/media/", "/media/")):
                        removable.append(parts[1].replace("\\040", " "))
        except OSError:
            pass
        extra = [self.paths.settings_dir, self.paths.runtime_dir, self.paths.log_dir, self._library_root()]
        return uninstall.Places(
            home=home, libraries=libraries, steam_roots=roots, extra_protected=extra, removable=removable
        )

    @staticmethod
    def _uninstall_others(game: dict[str, Any], games: list[dict[str, Any]]) -> list[str]:
        """Every folder and file another game uses: the guards never delete around them."""
        others: list[str] = []
        for other in games:
            if other["key"] == game["key"]:
                continue
            others += [str(p) for p in (other.get("base_dir"), other.get("exe"), other.get("prefix")) if p]
            others += [str(p) for p in (other.get("wine_prefix"), other.get("start_dir")) if p]
        return others

    async def _uninstall_target(self, key: str) -> dict[str, Any]:
        game = await self._game(key)
        if game["kind"] not in ("shortcut", "steam"):
            raise ValueError("only Steam games and non-Steam shortcuts can be uninstalled here")
        if game["kind"] == "shortcut":
            verdict = (await asyncio.to_thread(self.remote_copies.steam_verdicts)).get(int(game["appid"]), {})
            if verdict.get("steam") == discovery.REMOTE:
                raise ValueError("Steam says this game is installed on another device, so it is not uninstalled here")
        prefix = game.get("prefix")
        running = await asyncio.to_thread(find_game_processes, int(game["appid"]), prefix, self.proc_root)
        if running:
            raise ValueError("quit the game first")
        return game

    async def uninstall_plan(self, key: str) -> dict[str, Any]:
        """What uninstalling would do, for the confirmation screen. Changes nothing."""
        game = await self._uninstall_target(key)
        config = self.game_configs.get(key)
        game_key = await self._game_key_of(key)
        synced = bool(config.get("enabled") and game_key)
        base = {"key": key, "name": game["name"], "kind": game["kind"], "synced": synced, "gameKey": game_key}
        if game["kind"] == "steam":
            return {**base, "appid": int(game["appid"]), "folders": [], "kept": [], "steam": True}
        games = (await self.discover_games())["games"]
        found = await asyncio.to_thread(
            uninstall.plan, game, self._uninstall_places(), self._uninstall_others(game, games)
        )
        return {**base, **found, "steam": False, "store": self.settings.get("snapshotStore")}

    async def _final_backup(self, key: str) -> dict[str, Any]:
        result = await self.sync_push(key)
        if result.get("status") not in ("published", "published-fork", "no-change", "nothing-to-save"):
            raise ValueError(
                "the final backup could not be saved (the cloud or your other device is not reachable); "
                "try again, or uninstall without a final backup"
            )
        return result

    async def uninstall_steam(self, key: str, backup: bool = True) -> dict[str, Any]:
        """Steam games: an optional final backup, then Steam's own uninstall wizard. Keepsake deletes nothing."""
        plan_ = await self.uninstall_plan(key)
        if not plan_["steam"]:
            raise ValueError("this is not a Steam game")
        backed_up = None
        if backup and plan_["synced"]:
            backed_up = await self._final_backup(key)
        op_id = await asyncio.to_thread(self._ops().enqueue, "uninstall", "open-uninstall", {"appid": plan_["appid"]})
        await self.emit("keepsake_steam_ops")
        log_event(logging.INFO, "uninstall.steam", "Opened Steam's uninstall", appid=plan_["appid"])
        return {"op": op_id, "backup": backed_up}

    async def uninstall_start(self, key: str, skip_backup: bool = False) -> dict[str, Any]:
        """Non-Steam games: start the uninstall in the background. Only after the confirmation screen."""
        if self._uninstall_job and self._uninstall_job["state"] in uninstall.RUNNING:
            raise ValueError("an uninstall is already running")
        plan_ = await self.uninstall_plan(key)
        if plan_["steam"]:
            raise ValueError("Steam uninstalls its own games: use Uninstall in Steam")
        self._uninstall_job = {
            "key": key,
            "name": plan_["name"],
            "appid": plan_["appid"],
            "state": "starting",
            "folders": plan_["folders"],
            "kept": plan_["kept"],
            "done": 0,
            "total": sum(f["size"] for f in plan_["folders"]),
            "removed": [],
            "error": None,
            "backup": None,
            "restoreFrom": None,
        }
        self._uninstall_cancel = False
        task = asyncio.create_task(self._uninstall_run(plan_, bool(skip_backup)))
        self._background.append(task)
        return dict(self._uninstall_job)

    async def uninstall_status(self) -> dict[str, Any] | None:
        return dict(self._uninstall_job) if self._uninstall_job else None

    async def uninstall_cancel(self) -> dict[str, Any] | None:
        """Stop between files. What is already deleted stays deleted; the rest is kept."""
        self._uninstall_cancel = True
        return await self.uninstall_status()

    def _uninstall_set(self, **changes: Any) -> None:
        if self._uninstall_job is not None:
            self._uninstall_job.update(changes)

    async def _wait_op(self, op_id: int, timeout: float = 300.0) -> tuple[bool, dict[str, Any]]:
        future: asyncio.Future[tuple[bool, dict[str, Any]]] = asyncio.get_running_loop().create_future()
        self._op_waiters[op_id] = future
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self._op_waiters.pop(op_id, None)

    async def _uninstall_run(self, plan_: dict[str, Any], skip_backup: bool) -> None:
        key, appid = plan_["key"], int(plan_["appid"])
        try:
            async with self.locks.hold(plan_.get("gameKey") or key, "uninstall"):
                # 1. A final snapshot, so the saves can come back on any device.
                if plan_["synced"] and not skip_backup:
                    self._uninstall_set(state="backing-up")
                    result = await self._final_backup(key)
                    where = "your other devices" if self.settings.get("snapshotStore") == "direct" else "the cloud"
                    self._uninstall_set(
                        backup=result.get("snapId") or result.get("status"),
                        restoreFrom=f"History of {plan_['name']} on any device that syncs with {where}",
                    )
                if self._uninstall_cancel:
                    raise uninstall.Cancelled("cancelled before anything was removed")
                # 2. The shortcut and its artwork, through Steam, read back (ADR-0015, ADR-0065).
                self._uninstall_set(state="removing-shortcut")
                op_id = await asyncio.to_thread(
                    self._ops().enqueue, "uninstall", "remove-shortcut", {"appid": appid, "clearArtwork": True}
                )
                await self.emit("keepsake_steam_ops")
                try:
                    ok, result = await self._wait_op(op_id, self.UNINSTALL_OP_TIMEOUT)
                except TimeoutError as exc:
                    raise ValueError("Steam did not remove the shortcut; open Gaming Mode and try again") from exc
                if not ok or result.get("readBack") is not None:
                    raise ValueError("Steam still lists the shortcut, so nothing was deleted")
                # 3. The prefix and the install folder, each checked again just before.
                self._uninstall_set(state="deleting")
                games = (await self.discover_games(refresh=True))["games"]
                others = self._uninstall_others({"key": key}, games)
                places = self._uninstall_places()
                for item in plan_["folders"]:
                    problem = await asyncio.to_thread(uninstall.recheck, item, appid, places, others)
                    job = self._uninstall_job or {}
                    if problem:
                        self._uninstall_set(kept=[*job.get("kept", []), {"path": item["path"], "reason": problem}])
                        continue
                    start = int(job.get("done", 0))

                    def progress(done: int, start: int = start) -> None:
                        self._uninstall_set(done=start + done)

                    removed = await asyncio.to_thread(
                        uninstall.delete_tree, item["path"], lambda: self._uninstall_cancel, progress
                    )
                    job = self._uninstall_job or {}
                    self._uninstall_set(done=start + removed, removed=[*job.get("removed", []), item["path"]])
                # 4. Keepsake's own records of the game on this device.
                self._uninstall_set(state="cleaning")
                await asyncio.to_thread(self._uninstall_forget, key, appid)
            self._uninstall_set(state="done")
            log_event(logging.INFO, "uninstall.done", "Uninstalled a game", appid=appid)
            await self.emit("keepsake_toast", f"{plan_['name']} is uninstalled.")
        except uninstall.Cancelled as exc:
            self._uninstall_set(state="cancelled", error=str(exc))
            log_event(logging.WARNING, "uninstall.cancelled", "Uninstall stopped", appid=appid)
        except (ValueError, OSError, StoreError, SnapshotError) as exc:
            self._uninstall_set(state="failed", error=str(exc))
            log_event(logging.ERROR, "uninstall.failed", "Uninstall failed", appid=appid, error=str(exc))

    def _uninstall_forget(self, key: str, appid: int) -> None:
        self.game_configs.remove(key)
        self._clear_proposal(key)
        if self.game_links:
            found = self.game_links.for_appid(appid)
            if found:
                self.game_links.remove(found[0])
        if self.installer:
            self.installer.forget_appid(appid)
        self._games = None  # the next scan no longer finds it

    async def steam_ops_claim(self) -> dict[str, Any] | None:
        if self.steam_ops is None:
            return None
        return await asyncio.to_thread(self.steam_ops.claim)

    async def steam_ops_finish(self, op_id: int, ok: bool, result: dict[str, Any]) -> dict[str, Any]:
        await asyncio.to_thread(self._ops().finish, int(op_id), bool(ok), dict(result))
        log_event(logging.INFO, "steamops.finished", "Steam operation finished", id=int(op_id), ok=bool(ok))
        op = await asyncio.to_thread(self._ops().get, int(op_id))
        waiter = self._op_waiters.get(int(op_id))
        if waiter and not waiter.done():
            waiter.set_result((bool(ok), dict(result)))
        if op and op["kind"] == "set-hidden" and op["payload"].get("hidden") is True:
            appid = int(op["payload"]["appid"])
            log = await asyncio.to_thread(self.remote_copies.tidy_log)
            entry = log["hidden"].get(str(appid))
            if entry and entry.get("op") == int(op_id):  # read back: Steam now says it is hidden
                hidden = bool(ok and dict(result).get("readBack") is True)
                state = "hidden" if hidden else "failed"
                await asyncio.to_thread(self.remote_copies.record, appid, str(entry.get("name", "")), state)
        if op and op["module"] == "replication" and self.incoming:
            offer = await asyncio.to_thread(self.incoming.op_finished, int(op_id), bool(ok), dict(result))
            if offer and offer["state"] == "done":
                await self._replication_adopt(offer)
        if op and op["module"] == "installer" and self.installer:
            job = await asyncio.to_thread(self.installer.op_finished, int(op_id), bool(ok), dict(result))
            if job and job["state"] == "done" and op["kind"] in RETARGET_KINDS:
                # Hand-off (slice 22): other modules hear about the new game; the user opts in to each.
                await self.bus.publish(
                    "game_installed", {"gameKey": None, "appid": job["appid"], "title": job["title"]}
                )
                await self.emit("keepsake_toast", f"{job['title']} is installed. Start it from your library.")
        return {"ok": True}

    async def steam_ops_file(self, op_id: int) -> dict[str, Any]:
        """The staged image for a claimed artwork operation, base64-encoded for ``SetCustomArtworkForApp``."""
        op = await asyncio.to_thread(self._ops().get, int(op_id))
        if not op or op["module"] not in ("installer", "replication"):
            raise ValueError("that operation has no staged file")
        try:
            if op["module"] == "replication":
                path = self._incoming().staged_file(op)
            else:
                path = self._installer().staged_file(op)
            data = await asyncio.to_thread(_read_bytes, path)
        except (InstallerError, OfferError, ValueError, OSError) as exc:
            raise ValueError("the staged image is missing") from exc
        return {"base64": base64.b64encode(data).decode("ascii")}

    # Advisor (slice 14, ADR-0028)

    def _the_advisor(self) -> Advisor:
        if self.advisor is None:
            raise ValueError("the Advisor module is off; switch it on in Settings, Modules")
        return self.advisor

    async def advisor_view(self) -> dict[str, Any]:
        if self.advisor is None:
            return {"running": False}
        view = await asyncio.to_thread(self.advisor.view)
        return {"running": True, **view, "pcgwLogin": self.credentials.configured("pcgw")}

    async def advisor_select_game(self, appid: int) -> dict[str, Any]:
        """Advise on any game from the Games list, not only the running one."""
        await asyncio.to_thread(self._the_advisor().set_game, int(appid))
        return await self.advisor_view()

    async def advisor_refresh(self) -> dict[str, Any]:
        await asyncio.to_thread(self._the_advisor().load_reports, True)
        return await self.advisor_view()

    async def advisor_redetect(self) -> dict[str, Any]:
        await asyncio.to_thread(self._the_advisor().detect)
        return await self.advisor_view()

    async def advisor_ai_models(self, provider: str) -> list[dict[str, str]]:
        try:
            return await asyncio.to_thread(self._the_advisor().list_models, str(provider))
        except AdvisorError as exc:
            raise ValueError(str(exc)) from exc

    async def advisor_ai_generate(self) -> dict[str, Any]:
        """Button only (P18): one request to the chosen provider with the minimal payload."""
        result = await asyncio.to_thread(self._the_advisor().generate_ai)
        log_event(
            logging.INFO, "advisor.ai", "AI advice requested", provider=result["provider"], ok=result["error"] is None
        )
        return await self.advisor_view()

    async def advisor_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        advisor = self._the_advisor()
        try:
            await asyncio.to_thread(advisor.save_settings, dict(values))
        except AdvisorError as exc:
            raise ValueError(str(exc)) from exc
        reload = {"steamIdOverrides", "sourceDeckVerified", "sourceAntiCheat", "sourcePcgw", "sourceProtonDb"}
        if advisor.game and set(values) & reload:
            await asyncio.to_thread(advisor.set_game, int(advisor.game["appid"]))
        return await self.advisor_view()

    # Replication: device links and pairing (slice 17, ADR-0054, ADR-0056)

    def _links(self) -> Links:
        if self.links is None:
            raise ValueError("Replication is off; switch it on in Settings, Modules")
        return self.links

    def _replication_changed(self) -> None:
        """Something changed (a pairing request, an offer, a transfer): tell the open pages.

        Offers and transfers report from worker threads too, so this hands over to the event loop.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._replication_changed)
            return
        links = self.links
        if links is None:
            return
        asyncio.get_running_loop().create_task(self.emit(REPLICATION_EVENT))
        for pairing in links.listener.pairings.values() if links.listener else []:
            if pairing.state == "compare" and not pairing.announced:
                pairing.announced = True
                name = pairing.peer_name or "another device"
                text = f"{name} wants to pair. Check the code in Keepsake, Devices."
                asyncio.get_running_loop().create_task(self.emit("keepsake_toast", text))

    async def _replication(self, work: Callable[[Links], Any]) -> Any:
        try:
            result = work(self._links())
            return await result if asyncio.iscoroutine(result) else result
        except (ReplicationError, replication_link.LinkError) as exc:
            raise ValueError(str(exc)) from exc

    async def replication_status(self) -> dict[str, Any]:
        status: dict[str, Any] = await self._replication(lambda links: links.status())
        status["addressChoice"] = str(self.settings.get("replicationAddress"))
        status["addressesAvailable"] = await asyncio.to_thread(netinfo.local_addresses, self.proc_root)
        status["thisDevice"] = {"name": str(self.settings.get("deviceName") or "Unnamed device")}
        return status

    async def replication_set_listener(self, on: bool) -> dict[str, Any]:
        """Switch the listener on or off. Only from a user action (P17); remembered across restarts."""
        await self._replication(lambda links: links.set_listener(bool(on)))
        self.settings.set("replicationListener", bool(on))
        log_event(logging.INFO, "replication.listener", "Listener switched", on=bool(on))
        return await self.replication_status()

    async def replication_set_address(self, address: str) -> dict[str, Any]:
        """Listen on one address, or on every home network and VPN address ("")."""
        address = str(address or "")
        available = [a["address"] for a in await asyncio.to_thread(netinfo.local_addresses, self.proc_root)]
        if address and address not in available:
            raise ValueError("that address is not one of this device's home network or VPN addresses")
        self.settings.set("replicationAddress", address)
        links = self._links()
        if links.listener is not None:  # bind again where the user chose
            await self._replication(lambda lk: lk.set_listener(False))
            await self._replication(lambda lk: lk.set_listener(True))
        return await self.replication_status()

    async def replication_open_pairing(self) -> dict[str, Any]:
        await self._replication(lambda links: links.open_pairing())
        log_event(logging.INFO, "replication.pairing_open", "Pairing window opened")
        return await self.replication_status()

    async def replication_close_pairing(self) -> dict[str, Any]:
        await self._replication(lambda links: links.close_pairing())
        return await self.replication_status()

    async def replication_pair(self, address: str) -> dict[str, Any]:
        """Pair with a device whose pairing window is open, at a found or typed address."""
        pairing: dict[str, Any] = await self._replication(lambda links: links.pair_with(str(address)))
        log_event(logging.INFO, "replication.pair_start", "Pairing started")
        return pairing

    async def replication_answer(self, pairing_id: str, ok: bool) -> dict[str, Any]:
        await self._replication(lambda links: links.answer(str(pairing_id), bool(ok)))
        log_event(logging.INFO, "replication.pair_answer", "Pairing code answered", match=bool(ok))
        return await self.replication_status()

    async def replication_cancel(self, pairing_id: str) -> dict[str, Any]:
        await self._replication(lambda links: links.cancel(str(pairing_id)))
        return await self.replication_status()

    async def replication_find(self) -> list[dict[str, Any]]:
        """Look for Keepsake devices on the LAN for two seconds. Only from a user action."""
        found: list[dict[str, Any]] = await self._replication(lambda links: links.find())
        return found

    async def replication_check(self, peer_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self._replication(lambda links: links.check(str(peer_id)))
        return result

    async def replication_remove(self, peer_id: str) -> dict[str, Any]:
        await self._replication(lambda links: links.remove(str(peer_id)))
        log_event(logging.INFO, "replication.removed", "Paired device removed")
        return await self.replication_status()

    def _replication_hold(self) -> str | None:
        percent, mains = power.battery_state(self.power_root)
        return hold_reason(percent, mains, bool(self._games_running))

    def _replication_connect_for(self, peer_id: str) -> transfer.Connect:
        """A connection maker for a paired device, at the address it was last seen on."""

        async def connect() -> replication_link.Connection:
            links = self._links()
            peer = links.store.get(peer_id)
            if peer is None:
                raise replication_link.LinkError("that device is no longer paired")
            try:
                host, port = parse_address(peer["address"] or "")
            except ReplicationError as exc:
                raise replication_link.LinkError("the device's address is not known; check it in Devices") from exc
            return await replication_link.connect(links.me, links.store, peer_id, host, port)

        return connect

    def _transfers(self) -> Transfers:
        if self.transfers is None:
            raise ValueError("Replication is off; switch it on in Settings, Modules")
        return self.transfers

    async def replication_transfers(self) -> dict[str, Any]:
        return self._transfers().status()

    async def replication_pause(self, job_id: str) -> dict[str, Any]:
        try:
            await self._transfers().pause(str(job_id))
        except transfer.TransferError as exc:
            raise ValueError(str(exc)) from exc
        return self._transfers().status()

    async def replication_resume(self, job_id: str) -> dict[str, Any]:
        try:
            await self._transfers().resume(str(job_id))
        except transfer.TransferError as exc:
            raise ValueError(str(exc)) from exc
        return self._transfers().status()

    async def replication_stop(self, job_id: str) -> dict[str, Any]:
        """ "Stop and remove": only after the user confirmed it on the page."""
        try:
            await self._transfers().stop(str(job_id))
        except transfer.TransferError as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "replication.stopped", "Transfer stopped and removed")
        return self._transfers().status()

    # Sending and receiving games (slice 19, ADR-0059)

    def _replication_places(self) -> dict[str, str]:
        """Where a received game may go on this device: the library, Steam's folders, Keepsake's own."""
        home = discovery.real_home(self.home)
        roots = discovery.steam_roots(self.home, self.host)
        steam = roots[0] if roots else os.path.join(home, ".local", "share", "Steam")
        return {
            "library": self._library_root(),
            "compatdata": os.path.join(steam, "steamapps", "compatdata"),
            "tools": os.path.join(steam, "compatibilitytools.d"),
            "art": os.path.join(self.paths.runtime_dir, "replication-art"),
            "home": home,
        }

    def _incoming(self) -> Incoming:
        if self.incoming is None:
            raise ValueError("Replication is off; switch it on in Settings, Modules")
        return self.incoming

    def _outgoing(self) -> Outgoing:
        if self.outgoing is None:
            raise ValueError("Replication is off; switch it on in Settings, Modules")
        return self.outgoing

    async def replication_send(self, key: str, peer_id: str) -> dict[str, Any]:
        """Offer a non-Steam game to a paired device. Only from a user action.

        Saves first: a game Saves manages is pushed, so the copy carries the newest saves and the
        other device adopts them silently (spec 8.2, Send a game, step 1).
        """
        links = self._links()
        if links.store.get(str(peer_id)) is None:
            raise ValueError("that device is not paired")
        game = await self._game(str(key))
        places = self._replication_places()
        try:
            plan = await asyncio.to_thread(send_plan, dict(game), places["home"], places["library"], places["tools"])
        except SendError as exc:
            raise ValueError(str(exc)) from exc
        config = self.game_configs.get(str(key))
        warning = None
        if config.get("enabled"):
            try:
                pushed = await self.sync_push(str(key))
            except Exception as exc:  # noqa: BLE001 - offline: warn and send what is here (spec step 1)
                pushed, warning = (
                    {},
                    f"Saves could not be pushed first ({type(exc).__name__}); the copy has the saves on this device.",
                )
            if pushed.get("status") == "conflict":
                raise ValueError("this game has a save conflict; resolve it in Keepsake first, then send it")
        extra = {
            "from": {"name": str(self.settings.get("deviceName") or "Unnamed device")},
            "gameKey": config.get("gameKey"),
            "savesEnabled": bool(config.get("enabled")),
        }
        self._sending[str(key)] = {"state": "preparing", "title": plan.title, "peer": str(peer_id), "warning": warning}
        self._background.append(asyncio.create_task(self._send_game(str(key), plan, str(peer_id), extra)))
        return self._sending[str(key)] | {"droppedOptions": plan.dropped_options}

    async def _send_game(self, key: str, plan: Any, peer_id: str, extra: dict[str, Any]) -> None:
        state = self._sending[key]
        try:
            wire = await asyncio.to_thread(self._outgoing().prepare, plan, peer_id, extra)
            connection = await self._replication_connect_for(peer_id)()
            try:
                await send_offer(connection, wire)
            finally:
                await connection.close()
            state.update(state="sent", offer=wire["id"])
            game = await self._game(key)
            scopes = {s: r for s, r in plan.roots.items() if s in ("install", "prefix")}
            self._link_game(wire["id"], plan.title, peer_id, int(game["appid"]), scopes, dict(game))
            await self.emit("keepsake_toast", f"{plan.title} is offered. Accept it on the other device, in Devices.")
        except (OfferError, replication_link.LinkError, OSError, ValueError) as exc:
            state.update(state="failed", reason=str(exc))
            await self.emit("keepsake_toast", f"{plan.title} was not offered: {exc}")
        self._replication_changed()

    async def replication_offers(self) -> dict[str, Any]:
        return {
            "incoming": await asyncio.to_thread(self._incoming().list),
            "outgoing": await asyncio.to_thread(self._outgoing().list),
            "sending": self._sending,
        }

    async def replication_offer_check(self, offer_id: str, copy_tool: bool = False) -> dict[str, Any]:
        """Where an offered game would go, and what is missing, before the user accepts."""
        try:
            return await asyncio.to_thread(self._incoming().preflight, str(offer_id), bool(copy_tool))
        except (OfferError, OSError) as exc:
            return {"problem": str(exc)}

    async def replication_accept(self, offer_id: str, copy_tool: bool = False) -> dict[str, Any]:
        try:
            offer = await asyncio.to_thread(self._incoming().accept, str(offer_id), bool(copy_tool))
        except (OfferError, transfer.TransferError, OSError) as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "replication.accepted", "Offered game accepted", copyTool=bool(copy_tool))
        return offer

    async def replication_decline(self, offer_id: str) -> dict[str, Any]:
        try:
            await asyncio.to_thread(self._incoming().decline, str(offer_id))
        except OfferError as exc:
            raise ValueError(str(exc)) from exc
        return await self.replication_offers()

    async def replication_dismiss(self, offer_id: str) -> dict[str, Any]:
        try:
            await asyncio.to_thread(self._incoming().dismiss, str(offer_id))
        except OfferError as exc:
            raise ValueError(str(exc)) from exc
        return await self.replication_offers()

    async def replication_withdraw(self, offer_id: str) -> dict[str, Any]:
        try:
            await asyncio.to_thread(self._outgoing().withdraw, str(offer_id))
        except OfferError as exc:
            raise ValueError(str(exc)) from exc
        return await self.replication_offers()

    async def replication_remove_game(self, offer_id: str) -> dict[str, Any]:
        """ "Stop and remove" for a game being received: undo everything it made. Confirmed on the page."""
        try:
            await self._incoming().stop(str(offer_id))
        except (OfferError, transfer.TransferError, OSError) as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "replication.removed_game", "Received game stopped and removed")
        return await self.replication_offers()

    async def _replication_adopt(self, offer: dict[str, Any]) -> None:
        """The new shortcut gets the sending device's game key, so Saves adopts the copied saves silently."""
        record = (await asyncio.to_thread(self._incoming()._load)).get(offer["id"], {})
        sent = record.get("offer", {})
        games = (await self.discover_games(refresh=True))["games"]
        game = next((g for g in games if g.get("kind") == "shortcut" and g.get("appid") == offer.get("appid")), None)
        if game is not None and sent.get("gameKey"):
            await self.set_game_key(game["key"], sent["gameKey"])
            if sent.get("savesEnabled"):
                await self.update_game_config(game["key"], {"enabled": True})
        if game is not None:
            scopes = {
                s: p
                for s, p in (
                    ("install", record.get("targets", {}).get("install")),
                    ("prefix", record.get("prefixFinal")),
                )
                if p
            }
            self._link_game(offer["id"], offer["title"], record["peer"], int(game["appid"]), scopes, dict(game))
        text = f"{offer['title']} is ready on this device."
        await self.emit("keepsake_toast", text + (f" {offer['reason']}" if offer.get("reason") else ""))

    # Direct save sync between paired devices, no cloud account (R7, ADR-0061)

    def _direct_root(self) -> str:
        return os.path.join(self.paths.runtime_dir, "direct-store")

    def _direct_store(self) -> LocalFolderStore | None:
        """This device's store, only while it syncs saves directly. Otherwise peers are refused."""
        if self.settings.get("snapshotStore") != "direct":
            return None
        return LocalFolderStore(self._direct_root())

    async def _direct_exchange(self, timeout: float = 60.0, only: str | None = None) -> dict[str, Any]:
        """Fetch from each reachable paired device the save objects this one lacks. Never blocks a game:
        an unreachable device is noted and play carries on with what is here (principle 5)."""
        store = self._direct_store()
        links = self.links
        if store is None or links is None:
            return {"peers": 0, "copied": 0, "unreachable": []}
        summary: dict[str, Any] = {"peers": 0, "copied": 0, "removed": 0, "unreachable": []}
        for peer in links.store.list():
            if only and peer["id"] != only:
                continue
            try:
                connection = await asyncio.wait_for(self._replication_connect_for(peer["id"])(), 10)
                try:
                    result = await asyncio.wait_for(directsync.exchange(store, connection), timeout)
                finally:
                    await connection.close()
                summary["peers"] += 1
                summary["copied"] += result["copied"]
                summary["removed"] += result["removed"]
            except (replication_link.LinkError, StoreError, TimeoutError, OSError) as exc:
                summary["unreachable"].append(peer["name"])
                log_event(
                    logging.INFO, "direct.unreachable", "Direct save sync skipped a device", reason=type(exc).__name__
                )
        self._direct_last = summary | {"at": time.time()}
        if summary["copied"]:
            log_event(
                logging.INFO, "direct.exchanged", "Saves fetched from your other devices", count=summary["copied"]
            )
        return summary

    def _direct_pushed(self) -> None:
        """After a push: tell paired devices there is something new, so they fetch it soon."""
        if self._direct_store() is None or self.links is None:
            return

        async def tell() -> None:
            for peer in self.links.store.list() if self.links else []:
                try:
                    connection = await asyncio.wait_for(self._replication_connect_for(peer["id"])(), 10)
                    try:
                        await directsync.tell_changed(connection)
                    finally:
                        await connection.close()
                except (replication_link.LinkError, TimeoutError, OSError):
                    pass  # it fetches at its next launch or idle pass

        self._background.append(asyncio.create_task(tell()))

    def _direct_peer_changed(self, peer_id: str) -> None:
        self._background.append(asyncio.create_task(self._direct_exchange(only=peer_id or None)))

    async def direct_sync_now(self) -> dict[str, Any]:
        """Fetch saves from paired devices now (Cloud settings, Direct between my devices)."""
        if self._direct_store() is None:
            raise ValueError("choose Direct between my devices in Cloud settings first")
        if self.links is None:
            raise ValueError("switch on Replication in Settings, Modules, and pair your devices")
        return await self._direct_exchange()

    # Keeping games in step (slice 20, ADR-0060)

    def _game_links(self) -> GameLinks:
        if self.game_links is None:
            raise ValueError("Replication is off; switch it on in Settings, Modules")
        return self.game_links

    def _replication_keep(self, game: dict[str, Any], scopes: dict[str, str]) -> dict[str, list[str]]:
        """Every file Saves manages and every config file of the game, per share: never part of an update."""
        config = self.game_configs.get(game["key"])
        index = self.manifest.load()
        match = manifest.match_game(index, game, config)
        title = match.get("title")
        record = index["games"].get(title) if index and title else None
        found = resolve.preview(game, title, record, {**config, "includeConfig": True}, self.home, include_files=True)
        files = [
            os.path.join(found["roots"][root], *rel.split("/"))
            for root, rels in found.get("files", {}).items()
            for rel in rels
            if found["roots"].get(root)
        ]
        return {scope: keep_relative(root, files) for scope, root in scopes.items()}

    def _link_game(
        self, link_id: str, title: str, peer: str, appid: int, scopes: dict[str, str], game: dict[str, Any]
    ) -> None:
        """Link a game sent or received, and take its base in the background (it hashes the whole game)."""
        try:
            self._game_links().add(link_id, title, peer, appid, scopes, {})
        except (LinkStoreError, ValueError) as exc:
            log_event(logging.WARNING, "replication.link_failed", "Game not linked", error=str(exc))
            return
        self._background.append(asyncio.create_task(self._scan_link(link_id, game)))

    async def _scan_link(self, link_id: str, game: dict[str, Any]) -> dict[str, Any] | None:
        links = self._game_links()
        link = links.get(link_id)
        if link is None:
            return None
        keep = await asyncio.to_thread(self._replication_keep, game, link["scopes"])
        manifests = await asyncio.to_thread(scan_game, link["scopes"], keep)
        roots = {s: m["root"] for s, m in manifests.items()}
        changed = links.changed(link_id, roots)
        link = links.get(link_id) or link
        if changed and link["state"] in ("in-sync", "changed-here"):
            link = links.update(link_id, state="changed-here", checked=time.time())
            if link["policy"] == "auto":
                await self._send_update(link_id, game, keep)
        else:
            link = links.update(link_id, checked=time.time())
        self._replication_changed()
        return link

    async def _send_update(self, link_id: str, game: dict[str, Any], keep: dict[str, list[str]]) -> None:
        links = self._game_links()
        link = links.get(link_id)
        if link is None:
            raise ValueError("that game is no longer linked")
        extra = {"from": {"name": str(self.settings.get("deviceName") or "Unnamed device")}}
        try:
            wire, roots = await asyncio.to_thread(
                self._outgoing().prepare_update,
                link_id,
                link["title"],
                link["scopes"],
                keep,
                link["base"],
                link["peer"],
                extra,
            )
            connection = await self._replication_connect_for(link["peer"])()
            try:
                await send_offer(connection, wire)
            finally:
                await connection.close()
        except (OfferError, replication_link.LinkError, OSError) as exc:
            raise ValueError(f"the update was not sent: {exc}") from exc
        links.update(link_id, base=roots, state="in-sync", checked=time.time())
        await self.emit("keepsake_toast", f"An update to {link['title']} is offered to the other device.")

    async def _linked_game(self, link: dict[str, Any]) -> dict[str, Any]:
        games = (await self.discover_games())["games"]
        game = next((g for g in games if g.get("kind") == "shortcut" and g.get("appid") == link.get("appid")), None)
        if game is None:
            raise ValueError(f"{link['title']} was not found in Steam on this device")
        return dict(game)

    async def replication_games(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._game_links().list)

    async def replication_set_policy(self, link_id: str, policy: str) -> list[dict[str, Any]]:
        try:
            self._game_links().update(str(link_id), policy=str(policy))
        except LinkStoreError as exc:
            raise ValueError(str(exc)) from exc
        return await self.replication_games()

    async def replication_check_game(self, link_id: str) -> dict[str, Any]:
        """Look for changes now. Hashes the whole game, so it can take a while for a big one."""
        link = self._game_links().get(str(link_id))
        if link is None:
            raise ValueError("that game is no longer linked")
        result = await self._scan_link(str(link_id), await self._linked_game(link))
        return result or {}

    async def replication_send_update(self, link_id: str) -> list[dict[str, Any]]:
        link = self._game_links().get(str(link_id))
        if link is None:
            raise ValueError("that game is no longer linked")
        game = await self._linked_game(link)
        keep = await asyncio.to_thread(self._replication_keep, game, link["scopes"])
        await self._send_update(str(link_id), game, keep)
        return await self.replication_games()

    async def replication_apply_update(self, offer_id: str, take_theirs: bool = False) -> dict[str, Any]:
        """Apply an update from the other device. If this device changed too, only with ``take_theirs``."""
        offered = {o["id"]: o for o in await asyncio.to_thread(self._incoming().list)}.get(str(offer_id))
        if offered is None or not offered.get("update"):
            raise ValueError("that update has gone")
        links = self._game_links()
        link = links.get(str(offered["link"]))
        if link is None:
            raise ValueError("that game is not linked on this device")
        game = await self._linked_game(link)
        keep = await asyncio.to_thread(self._replication_keep, game, link["scopes"])
        roots = {s: m["root"] for s, m in (await asyncio.to_thread(scan_game, link["scopes"], keep)).items()}
        if links.changed(str(offered["link"]), roots) and not take_theirs:
            links.update(str(offered["link"]), state="both-changed")
            self._replication_changed()
            raise ValueError(f"{link['title']} changed on this device too: choose which copy to keep")
        try:
            result = await asyncio.to_thread(self._incoming().accept_update, str(offer_id), link["scopes"], keep)
        except (OfferError, transfer.TransferError, OSError) as exc:
            raise ValueError(str(exc)) from exc
        links.update(str(offered["link"]), state="updating", pending=str(offer_id))
        return result

    async def replication_keep_mine(self, offer_id: str) -> dict[str, Any]:
        """Both sides changed and the user keeps this device's copy: the update is declined, nothing written."""
        offered = {o["id"]: o for o in await asyncio.to_thread(self._incoming().list)}.get(str(offer_id))
        if offered is None or not offered.get("update"):
            raise ValueError("that update has gone")
        await asyncio.to_thread(self._incoming().decline, str(offer_id))
        if self._game_links().get(str(offered["link"])):
            self._game_links().update(str(offered["link"]), state="changed-here")
        return await self.replication_offers()

    def _replication_offer_arrived(self, offer: dict[str, Any]) -> None:
        """An update for a game set to auto is applied by itself, unless this device changed it too."""
        update = offer.get("update")
        links = self.game_links
        if not update or links is None:
            return
        link = links.get(str(update["link"]))
        if link is None:
            return
        links.update(str(update["link"]), state="update-available")
        if link["policy"] == "auto":
            self._background.append(asyncio.create_task(self._auto_apply(offer["id"])))

    async def _auto_apply(self, offer_id: str) -> None:
        try:
            await self.replication_apply_update(offer_id)
        except ValueError as exc:
            await self.emit("keepsake_toast", str(exc))

    def _replication_update_done(self, record: dict[str, Any]) -> None:
        update = record["offer"].get("update")
        if update and self.game_links and self.game_links.get(update["link"]):
            roots = {s: share["root"] for s, share in record["offer"]["shares"].items()}
            base = {**(self.game_links.get(update["link"]) or {}).get("base", {}), **roots}
            self.game_links.update(update["link"], base=base, state="in-sync", pending=None, checked=time.time())
            self._replication_changed()

    async def replication_wake(self, peer_id: str) -> dict[str, Any]:
        sent: int = await self._replication(lambda links: asyncio.to_thread(links.wake, str(peer_id)))
        return {"sent": sent}

    # Installer (slice 21, ADR-0026)

    def _installer(self) -> Installer:
        if self.installer is None:
            raise ValueError("the Installer module is off; switch it on in Settings, Modules")
        return self.installer

    async def installer_status(self) -> dict[str, Any]:
        return {
            "running": self.installer is not None,
            "udisks": udisks.available(),
            "libraryRoot": self._library_root(),
            "artwork": artwork.available(),
            "artworkKey": self.credentials.configured("steamgriddb"),
            "sources": await asyncio.to_thread(self._install_sources),
            "jobs": await asyncio.to_thread(self.installer.jobs) if self.installer else [],
            "stagingFree": await asyncio.to_thread(self._staging_free),
            "download": dict(self._net),
        }

    def _staging_free(self) -> int | None:
        """Free bytes where network downloads are staged (ADR-0033), or None before the Installer starts."""
        if self.installer is None:
            return None
        try:
            return int(shutil.disk_usage(self.installer.downloads_dir()).free)
        except (OSError, InstallerError):
            return None

    def _install_sources(self) -> dict[str, Any]:
        """Places to start the file picker: home, the library, removable drives and network shares already mounted."""
        home = discovery.real_home(self.home).replace(os.sep, "/")
        user = os.path.basename(home.rstrip("/"))
        try:
            with open(os.path.join(self.proc_root, "self", "mounts"), encoding="utf-8", errors="replace") as handle:
                mounts = handle.read()
        except OSError:
            mounts = ""
        found = installer_files.mounted_sources(mounts, (f"/run/media/{user}/", "/run/media/", "/media/"))
        return {"home": home, **found}

    async def _installer_call(self, method: str, *args: Any) -> dict[str, Any]:
        try:
            result: dict[str, Any] = await asyncio.to_thread(getattr(self._installer(), method), *args)
        except InstallerError as exc:
            raise ValueError(str(exc)) from exc
        return result

    async def installer_add_cd_drive(self, job_id: int) -> dict[str, Any]:
        job = await self._installer_call("add_cd_drive", int(job_id))
        log_event(logging.INFO, "installer.cdrom", "Disc drive added", job=int(job_id))
        return job

    async def installer_remove_shortcut(self, job_id: int) -> dict[str, Any]:
        job = await self._installer_call("remove_shortcut", int(job_id))
        await self.emit("keepsake_steam_ops")
        return job

    async def installer_artwork_search(self, job_id: int) -> list[dict[str, Any]]:
        try:
            return await asyncio.to_thread(self._installer().search_artwork, int(job_id))
        except InstallerError as exc:
            raise ValueError(str(exc)) from exc

    async def installer_artwork_apply(self, job_id: int, game_id: int) -> dict[str, Any]:
        job = await self._installer_call("queue_artwork", int(job_id), int(game_id))
        await self.emit("keepsake_steam_ops")
        return job

    async def installer_handoff(self, job_id: int) -> dict[str, Any]:
        """The Games list key for a finished install, so the user can switch on save sync for it."""
        job = await self._installer_call("get", int(job_id))
        if job["state"] != "done":
            raise ValueError("the install has not finished")
        games = (await self.discover_games(True))["games"]
        game = next((g for g in games if g["appid"] == job["appid"]), None)
        if game is None:
            raise ValueError("Keepsake cannot see the new shortcut yet; try again in a moment")
        return {"key": game["key"], "replication": self.registry.enabled("replication")}

    async def installer_swap_disc(self, job_id: int, disc: str) -> dict[str, Any]:
        """Put the next disc of a set in the emulated drive while the installer waits for it (ADR-0053)."""
        try:
            job = await asyncio.to_thread(self._installer().swap_disc, int(job_id), str(disc))
        except (InstallerError, udisks.UdisksError) as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "installer.disc_swapped", "Disc swapped", job=int(job_id))
        return job

    async def installer_start(self, source: str, title: str, queue: bool = False) -> dict[str, Any]:
        try:
            job = await asyncio.to_thread(self._installer().start, str(source), str(title), False, bool(queue))
        except InPlaceFailed as exc:
            # Option A (ADR-0067): the share would not let udisks open the ISO there, so copy it first.
            return await self._copy_then_install(exc.source, str(title), str(exc))
        except (InstallerError, udisks.UdisksError) as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "installer.start", "Install prepared", job=job["id"], kind=job.get("kind", "queued"))
        return job

    # Installing from a network location that is not mounted (ADR-0033)

    NET_PROGRESS_EVENT = "keepsake_netinstall_progress"

    def _net_session(self, access: dict[str, Any]) -> remote.Session | smbshare.Share:
        """A session for one user action: a remembered location, or an address typed just now.

        ``smb://`` addresses are Windows shares (ADR-0034), ``davs://`` and ``dav://`` are WebDAV
        folders (HTTP rules, ``PROPFIND`` listings); everything else is HTTP or HTTPS.
        """
        access = access if isinstance(access, dict) else {}
        allowed = {str(h) for h in access.get("allowHosts") or [] if isinstance(h, str)}
        if access.get("locationId"):
            loc, password = self.net_locations.get(str(access["locationId"]))
            url, username = loc["url"], loc["username"]
        else:
            url, username, password = (str(access.get(k) or "") for k in ("url", "username", "password"))
        if url.strip().lower().startswith("smb://"):
            return smbshare.Share(url, username, password, connect=self._smb_connect, resolve=self._net_resolve)
        if webdav.is_dav(url):
            return webdav.DavSession(
                webdav.to_http(url),
                username,
                password,
                allowed=allowed,
                connect=self._net_connect,
                resolve=self._net_resolve,
            )
        return remote.Session(
            url, username, password, allowed=allowed, connect=self._net_connect, resolve=self._net_resolve
        )

    @staticmethod
    def _net_target(session: remote.Session | smbshare.Share, url: str, what: str) -> str:
        """``url`` checked to be on the session's own server."""
        if isinstance(session, smbshare.Share):
            address = smbshare.parse(url)
            same = (address.host, address.port) == (session.home, session.address.port)
            target = address.url(folder=what == "browse")
        else:
            target = remote.check_location(webdav.to_http(url) if webdav.is_dav(url) else url)
            same = (urlsplit(target).hostname or "").lower() == session.home
        if not same:
            raise remote.RemoteError(f"{what} within the location you chose")
        return target

    async def installer_net_locations(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.net_locations.public)

    async def installer_net_remember(self, values: dict[str, Any]) -> list[dict[str, Any]]:
        values = values if isinstance(values, dict) else {}
        try:
            return await asyncio.to_thread(
                self.net_locations.save,
                str(values.get("url") or ""),
                str(values.get("username") or ""),
                str(values.get("password") or ""),
                str(values["id"]) if values.get("id") else None,
            )
        except remote.RemoteError as exc:
            raise ValueError(str(exc)) from exc

    async def installer_net_forget(self, location_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.net_locations.forget, str(location_id))

    async def installer_net_browse(self, access: dict[str, Any], url: str = "") -> dict[str, Any]:
        """User action: list folders and ISO files at ``url`` (default: the location's own address)."""
        self._installer()
        try:
            session = self._net_session(access)
            target = self._net_target(session, url or session.url, "browse")
            if isinstance(session, smbshare.Share):
                lister: Callable[..., list[dict[str, Any]]] = smbshare.list_folder
            elif isinstance(session, webdav.DavSession):
                lister = webdav.list_folder
            else:
                lister = remote.list_folder
            entries = await asyncio.to_thread(lister, session, target)
        except remote.RedirectElsewhere as exc:
            return {"url": url, "entries": [], "redirectHost": exc.host, "error": str(exc)}
        except remote.RemoteError as exc:
            raise ValueError(str(exc)) from exc
        folder = target if target.endswith("/") else target + "/"
        return {"url": webdav.to_dav(folder) if isinstance(session, webdav.DavSession) else folder, "entries": entries}

    async def _network_iso_probe(self) -> dict[str, Any]:
        """The Device check's findings (ADR-0067): in-place mounting here, and a loop test on a mounted share."""

        def probe() -> dict[str, Any]:
            found = inplace.find_network_iso(os.path.join(self.proc_root, "self", "mounts"))
            out: dict[str, Any] = {
                "udisks": udisks.available(),
                "fusermount3": bool(shutil.which(netfuse.FUSERMOUNT)),
                "devFuse": os.access("/dev/fuse", os.R_OK | os.W_OK),
                "approved": netfuse.FUSERMOUNT_APPROVED,
                "inPlace": self._netfuse_available(),
                "iso": None,
            }
            if found and out["udisks"]:
                path, fstype = found
                out["iso"] = {"fstype": fstype, "error": inplace.loop_test(path, self._udisks_runner)}
            return out

        return await asyncio.to_thread(probe)

    async def installer_net_find_smb(self) -> dict[str, Any]:
        """User action: SMB servers answering on the local network (ADR-0066). Read only; nothing is mounted."""
        self._installer()
        found = await asyncio.to_thread(lanfind.find_servers, 2.5, self._lan_sockets)
        log_event(logging.INFO, "installer.smb_find", "Looked for Windows shares", servers=len(found["servers"]))
        return found

    async def installer_net_status(self) -> dict[str, Any]:
        return dict(self._net)

    async def installer_net_cancel(self) -> dict[str, Any]:
        if self._net.get("running"):
            self._net_cancel = True
        return dict(self._net)

    async def installer_net_download(
        self, access: dict[str, Any], url: str, title: str, sha256: str = ""
    ) -> dict[str, Any]:
        """User action: download one ISO into staging, then prepare the install from it."""
        installer = self._installer()
        if self._net.get("running"):
            raise ValueError("a download is already running; cancel it first")
        try:
            session = self._net_session(access)
            url = self._net_target(session, url, "download")
            name = remote.file_name(url)
            remote.check_sha256(sha256)
            folder = await asyncio.to_thread(installer.downloads_dir)
        except (remote.RemoteError, InstallerError) as exc:
            raise ValueError(str(exc)) from exc
        self._net_cancel = False
        self._net = {
            "running": True,
            "name": name,
            "title": title,
            "done": 0,
            "total": None,
            "rate": 0,
            "started": time.time(),
        }
        self._background.append(
            asyncio.create_task(self._run_net_download(installer, session, url, folder, str(title), sha256))
        )
        return dict(self._net)

    def _net_progress(self) -> Callable[[int, int | None], None]:
        loop = asyncio.get_running_loop()
        last = [0.0]

        def progress(done: int, total: int | None) -> None:
            now = time.time()
            if now - last[0] < 0.5 and done != total:
                return
            last[0] = now
            elapsed = max(now - float(self._net.get("started") or now), 0.001)
            self._net.update(done=done, total=total, rate=int(done / elapsed))
            asyncio.run_coroutine_threadsafe(self.emit(self.NET_PROGRESS_EVENT, dict(self._net)), loop)

        return progress

    async def _copy_then_install(self, source: str, title: str, reason: str) -> dict[str, Any]:
        """Copy an ISO from a mounted share to staging in the background, then install from the copy."""
        if self._net.get("running"):
            raise ValueError("a download or copy is already running; cancel it first")
        installer = self._installer()
        folder = await asyncio.to_thread(installer.downloads_dir)
        name = os.path.basename(source)
        self._net_cancel = False
        self._net = {"running": True, "name": name, "title": title, "done": 0, "total": None, "rate": 0}
        self._net.update(started=time.time(), copying=True)
        log_event(logging.INFO, "installer.copy_fallback", "Copying an ISO the share would not open in place")
        await self.emit("keepsake_toast", f"{name} is copied to this device first: {reason}. The install starts after.")

        async def run() -> None:
            outcome: dict[str, Any] = {}
            try:
                path = await asyncio.to_thread(
                    inplace.copy_iso, source, folder, self._net_progress(), lambda: self._net_cancel
                )
                job = await asyncio.to_thread(installer.start, path, title, True)
                outcome = {"job": job["id"]}
            except inplace.CopyCancelled:
                outcome = {"cancelled": True}
            except (InstallerError, udisks.UdisksError, ValueError, OSError) as exc:
                outcome = {"error": str(exc)}
            self._net = {**self._net, **outcome, "running": False}
            await self.emit(self.NET_PROGRESS_EVENT, dict(self._net))

        self._background.append(asyncio.create_task(run()))
        return {"copying": True, **self._net}

    def _net_mount_released(self, data: dict[str, Any]) -> None:
        mount = self._net_mounts.pop(str(data.get("netMount") or ""), None)
        if mount is not None:
            mount.close()

    def _try_in_place(
        self, installer: Installer, session: remote.Session | smbshare.Share, url: str, title: str
    ) -> dict[str, Any] | None:
        """Worker thread: install from Keepsake's own read-only mount of the network ISO (ADR-0067).

        Returns the new install, or None when it cannot be done here, so the caller copies instead.
        """
        if self._netfuse_available() is not None:
            return None
        mount: netfuse.Mount | None = None
        try:
            if isinstance(session, smbshare.Share):
                source: netfuse.RangeSource = netfuse.SmbRange(session, url)
                name = smbshare.parse(url).path.rsplit("/", 1)[-1]
            else:
                source = netfuse.HttpRange(session, webdav.to_http(url) if webdav.is_dav(url) else url)
                name = remote.file_name(url)
            mount_id = secrets.token_hex(6)
            point = os.path.join(self.paths.runtime_dir, "installer", "netmount", mount_id)
            mount = self._netfuse_mount(point, netfuse.Handler(name, netfuse.BlockCache(source)))
            path = mount.start()
            self._net_mounts[mount_id] = mount
            job = installer.start(path, title, False, False, mount_id)
            log_event(logging.INFO, "installer.in_place", "Installing from the network ISO in place", job=job["id"])
            return job
        except (netfuse.FuseError, remote.RemoteError, InstallerError, udisks.UdisksError, OSError) as exc:
            if mount is not None:
                mount.close()
                self._net_mounts = {k: v for k, v in self._net_mounts.items() if v is not mount}
            log_event(logging.INFO, "installer.in_place_failed", "Copying the ISO instead", reason=type(exc).__name__)
            return None

    async def _run_net_download(
        self,
        installer: Installer,
        session: remote.Session | smbshare.Share,
        url: str,
        folder: str,
        title: str,
        sha256: str,
    ) -> None:
        loop = asyncio.get_running_loop()
        last = [0.0]

        def progress(done: int, total: int | None) -> None:
            now = time.time()
            if now - last[0] < 0.5 and done != total:
                return
            last[0] = now
            elapsed = max(now - float(self._net.get("started") or now), 0.001)
            self._net.update(done=done, total=total, rate=int(done / elapsed))
            asyncio.run_coroutine_threadsafe(self.emit(self.NET_PROGRESS_EVENT, dict(self._net)), loop)

        outcome: dict[str, Any] = {}
        try:
            in_place = await asyncio.to_thread(self._try_in_place, installer, session, url, title)
            if in_place is not None:
                self._net = {**self._net, "job": in_place["id"], "inPlace": True, "running": False}
                await self.emit(self.NET_PROGRESS_EVENT, dict(self._net))
                return
            fetch = smbshare.download if isinstance(session, smbshare.Share) else remote.download
            path = await asyncio.to_thread(
                fetch,  # type: ignore[arg-type]
                session,
                url,
                folder,
                sha256=sha256 or None,
                progress=progress,
                cancelled=lambda: self._net_cancel,
            )
            job = await asyncio.to_thread(installer.start, path, title, True)
            outcome = {"job": job["id"]}
            log_event(logging.INFO, "installer.net_downloaded", "Network download finished", job=job["id"])
        except remote.Cancelled:
            outcome = {"cancelled": True}
        except remote.RedirectElsewhere as exc:
            outcome = {"error": str(exc), "redirectHost": exc.host}
        except (remote.RemoteError, InstallerError, udisks.UdisksError, OSError) as exc:
            outcome = {"error": str(exc)}
            log_event(logging.WARNING, "installer.net_failed", "Network download failed", reason=type(exc).__name__)
        self._net = {**self._net, **outcome, "running": False}
        await self.emit(self.NET_PROGRESS_EVENT, dict(self._net))

    async def installer_create_shortcut(self, job_id: int, installer_rel: str) -> dict[str, Any]:
        try:
            job = await asyncio.to_thread(self._installer().create_shortcut, int(job_id), str(installer_rel))
        except InstallerError as exc:
            raise ValueError(str(exc)) from exc
        await self.emit("keepsake_steam_ops")
        return job

    async def installer_finished_installing(self, job_id: int) -> dict[str, Any]:
        """Fallback when Steam did not report the installer closing: look for the new programs now."""
        job = await asyncio.to_thread(self._installer().get, int(job_id))
        if job["state"] != "run-installer" or not job.get("appid"):
            raise ValueError("this install is not waiting for the installer")
        found = await asyncio.to_thread(self._installer().installer_exited, int(job["appid"]))
        return found or job

    async def installer_retarget(self, job_id: int, exe: str) -> dict[str, Any]:
        try:
            job = await asyncio.to_thread(self._installer().retarget, int(job_id), str(exe))
        except InstallerError as exc:
            raise ValueError(str(exc)) from exc
        await self.emit("keepsake_steam_ops")
        return job

    async def installer_cancel(self, job_id: int) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(self._installer().cancel, int(job_id))
        except InstallerError as exc:
            raise ValueError(str(exc)) from exc

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

    async def activity(self, limit: int = 100) -> list[dict[str, Any]]:
        """What Keepsake did, newest first, in plain words (ADR-0048)."""
        records = await asyncio.to_thread(tail, self.paths.log_dir, 2000)
        names: dict[str, str] = {}
        try:
            for game, _config, gk in await self._matched():
                names[game["key"]] = game["name"]
                if gk:
                    names.setdefault(gk, game["name"])
        except (OSError, ValueError, StoreError):
            pass  # unnamed games are shown by their key
        return activity.build(records, lambda key: names.get(key, key), max(1, min(int(limit), 500)))

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

    async def signin_probe(self, action: str = "start") -> dict[str, Any]:
        """The Gaming Mode sign-in probe's loopback step (ADR-0044): "start" gives an address
        for Steam's browser, "result" says whether the browser reached it. Only from a user action."""
        if action == "start":
            if self._signin_probe is not None:
                self._signin_probe.close()
            self._signin_probe = await asyncio.to_thread(BrowserProbe)
            return {"url": self._signin_probe.url}
        if self._signin_probe is None:
            return {"arrived": False, "error": "not-started"}
        result = self._signin_probe.result()
        await asyncio.to_thread(diagnostics.record_probe_event, self.paths.runtime_dir, "signin-loopback", result)
        return result

    async def record_probe_event(self, kind: str, payload: Any) -> int:
        return await asyncio.to_thread(diagnostics.record_probe_event, self.paths.runtime_dir, kind, payload)

    # Device checks: the device run inside the plugin (ADR-0062)

    def _device_context(self) -> devicechecks.Context:
        return devicechecks.Context(
            home=discovery.real_home(self.home),
            proc_root=self.proc_root,
            sys_root=self.sys_root,
            library=self._library_root(),
            places=self._replication_places(),
            work_dir=os.path.join(self.paths.runtime_dir, "device-checks"),
            links=self.links,
            connect_for=self._replication_connect_for if self.links else None,
            probes={
                "remote-shortcuts": self._remote_shortcuts_probe,
                "smb-find": lambda: asyncio.to_thread(lanfind.find_servers, 2.5, self._lan_sockets),
                "network-iso": self._network_iso_probe,
            },
        )

    async def device_checks(self) -> dict[str, Any]:
        return {
            "checks": [{"id": c.id, "title": c.title, "needs": c.needs} for c in devicechecks.CHECKS],
            "results": [self._device_results[c.id] for c in devicechecks.CHECKS if c.id in self._device_results],
        }

    async def device_check_run(self, check_id: str) -> dict[str, Any]:
        """Run one check now. Only from a user action: some take a minute and write test files."""
        context = self._device_context()
        os.makedirs(context.work_dir, exist_ok=True)
        outcome = await devicechecks.run(str(check_id), context)
        self._device_results[outcome["id"]] = outcome
        log_event(logging.INFO, "devicecheck.run", "Device check run", check=outcome["id"], status=outcome["status"])
        return outcome

    async def device_checks_run_all(self) -> dict[str, Any]:
        for check in devicechecks.CHECKS:
            await self.device_check_run(check.id)
        return await self.device_checks()

    async def device_checks_export(self) -> dict[str, Any]:
        """Save the results as one redacted file, and give a short summary for the screen and a QR code."""
        import ssl

        results = [self._device_results[c.id] for c in devicechecks.CHECKS if c.id in self._device_results]
        if not results:
            raise ValueError("run the checks first")
        model = devicechecks.model_name(self.sys_root)
        text = devicechecks.summary(self.version, results, model)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = f"device-checks-{stamp}.json"
        payload = {
            "version": self.version,
            "host": self.host,
            "model": model,
            "python": sys.version.split()[0],
            "openssl": ssl.OPENSSL_VERSION,
            "results": results,
        }
        await asyncio.to_thread(atomic_write_json, os.path.join(self.paths.settings_dir, name), payload)
        where = devicechecks.tilde(os.path.join(self.paths.settings_dir, name), discovery.real_home(self.home))
        log_event(logging.INFO, "devicecheck.export", "Device check results exported", file=name)
        return {"file": name, "where": where, "summary": text}

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


def newer_save(state: dict[str, Any]) -> dict[str, Any] | None:
    """A newer save from another device that this device has not taken in yet (ADR-0049)."""
    newer = state.get("newer")
    if not isinstance(newer, dict) or newer.get("snapId") == state.get("base") or state.get("conflict"):
        return None
    return {"snapId": newer.get("snapId"), "device": newer.get("device"), "created": newer.get("created")}


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
