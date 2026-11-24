"""Backend application core.

``main.py`` creates one :class:`KeepsakeApp` and forwards each frontend call to
it. Keeping the logic here means it can be tested without Decky.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import re
import secrets
import shutil
import sys
import threading
import time
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, ClassVar
from urllib.parse import urlsplit

from . import (
    devicechecks,
    diagnostics,
    discovery,
    leftovers,
    manifest,
    net,
    power,
    remotecopies,
    resolve,
    shortcuts,
)
from .backends import BackendConfigError, CredentialStore
from .bus import EventBus
from .fsutil import atomic_write_json, read_json
from .gameconfig import GameConfigStore
from .installer import artwork, inplace, lanfind, netfuse, remote, smbshare, udisks, webdav
from .installer import files as installer_files
from .installer.artwork import SteamGridDB
from .installer.service import InPlaceFailed, Installer, InstallerError
from .installer.service import health_checks as installer_health_checks
from .jobs import JobTracker
from .locks import GameLocks
from .log import log_event, setup_logging, tail
from .modules import Module, ModuleRegistry
from .paths import PluginPaths
from .procs import find_game_processes
from .replication import activity as replication_activity
from .replication import link as replication_link
from .replication import netinfo, transfer
from .replication.jobs import Transfers, hold_reason
from .replication.news import PeerNews
from .replication.offers import Incoming, OfferError, Outgoing, send_offer, wire_reason
from .replication.ongoing import GameLinks, keep_relative
from .replication.ongoing import LinkError as LinkStoreError
from .replication.ongoing import scan as scan_game
from .replication.peers import PeerStore
from .replication.sendgame import SendError
from .replication.sendgame import plan as send_plan
from .replication.sendgame import sizes as send_sizes
from .replication.service import Links, ReplicationError, parse_address
from .replication.service import health_checks as replication_health_checks
from .replication.source import Shares
from .settings import MODULE_NAMES as SETTINGS_MODULE_NAMES
from .settings import SettingsStore
from .statedb import StateDB, StateError, open_db
from .steamops import SteamOps
from .update import Updater, startup_notice

EmitFn = Callable[..., Coroutine[Any, Any, None]]
NAV_KINDS = {
    "start",
    "stop",
    "route-mount",
    "route-unmount",
    "page-mount",
    "page-unmount",
    "navigate",
    "redirect",
    "focus-call",
    "focus",
    "focus-left-sidebar-unprompted",
    "input",
    "section-open",  # the menu redesign (ADR-0095): a section's own page with its tabs
    "tab",  # L1, R1 or the D-pad on the tab bar switched sub-page
}
NAV_DETAIL = re.compile(r"^[A-Za-z0-9/_:@.-]{0,80}$")


def navigation_record(record: Any) -> dict[str, Any]:
    """Keep only known event kinds, numbers, booleans and short id-like strings: never free text."""
    events = []
    for item in list((record or {}).get("events") or [])[:5000]:
        if (
            not isinstance(item, dict)
            or item.get("kind") not in NAV_KINDS
            or not isinstance(item.get("t"), (int, float))
        ):
            continue
        detail: dict[str, Any] = {}
        for key, value in dict(item.get("detail") or {}).items():
            if not NAV_DETAIL.match(str(key)):
                continue
            if isinstance(value, bool) or isinstance(value, (int, float)):
                detail[str(key)] = value
            elif isinstance(value, str) and NAV_DETAIL.match(value):
                detail[str(key)] = value
        events.append({"t": int(item["t"]), "kind": item["kind"], **({"detail": detail} if detail else {})})
    summary = {
        k: int(v)
        for k, v in dict((record or {}).get("summary") or {}).items()
        if NAV_DETAIL.match(str(k)) and isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    return {"summary": summary, "events": events}


MANIFEST_PROGRESS_EVENT = "keepsake_manifest_progress"
REPLICATION_EVENT = "keepsake_replication"
SHORTCUTS_EVENT = "keepsake_shortcuts"
PAIR_REQUEST_EVENT = "keepsake_pair_request"  # a device asks to pair (ADR-0070)
MANIFEST_PROGRESS_SECONDS = 0.5
RETARGET_KINDS = ("set-shortcut-name", "set-shortcut-exe", "set-shortcut-start-dir", "set-launch-options")


async def _no_emit(event: str, *args: Any) -> None:
    return None


# Games whose launch Keepsake cannot see: newer saves come in from the idle pass (ADR-0051).
SCAN_WAIT = 20.0  # seconds a game scan may take before the last list is used
PROGRESS_SECONDS = 1.0  # how often a receiving device reports progress to the sender
PULL_TOKEN_SECONDS = 900.0  # a listed game can be asked for for 15 minutes
PULL_LIST_MAX = 200


def normalise_appid(value: Any) -> int:
    """Accept a signed or unsigned 32-bit app ID, or a 64-bit shortcut game ID; return the unsigned app ID."""
    number = int(value)
    if number >= 2**32:
        number >>= 32  # 64-bit game ID: (appid << 32) | 0x02000000
    return number & 0xFFFFFFFF


def capital(text: str) -> str:
    """A device name at the start of a sentence: "the other device" becomes "The other device"."""
    return text[:1].upper() + text[1:]


def space_text(device: str, needed: int, free: int) -> str:
    """\"Legion Go 2 doesn't have enough space: needs 41.2 GiB, has 12.0 GiB free\" (ADR-0072)."""
    return (
        f"{capital(device)} doesn't have enough space: needs {needed / 2**30:.1f} GiB, has {free / 2**30:.1f} GiB free"
    )


def low_priority() -> None:
    """A disk thread runs at a lower CPU priority (Linux: per thread). I/O priority would need ioprio_set,
    which the standard library does not offer; the kernel's scheduler still favours interactive work."""
    with contextlib.suppress(AttributeError, OSError):
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)  # type: ignore[attr-defined, unused-ignore]


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
        # Haversack installs games and moves them between handhelds (the strip, ADR-0098): Decky only.
        self.host = "decky"
        self.credentials = CredentialStore(paths.settings_dir)  # the SteamGridDB key and network passwords
        self.paths = paths
        self.home = home
        self._games: dict[str, Any] | None = None
        # Disk work on its own low-priority threads, so a slow or offline disk never ties up the shared pool
        # or the event loop (v0.30.1); one game scan at a time.
        self._disk = ThreadPoolExecutor(max_workers=3, thread_name_prefix="keepsake-disk", initializer=low_priority)
        self._scan_future: asyncio.Future[dict[str, Any]] | None = None
        self._scan_slow = False
        self.remote_copies = remotecopies.RemoteCopies(paths.runtime_dir)
        # The Ludusavi manifest tells Replication where a game keeps its saves, so updates never replace
        # the other device's saves (ADR-0072).
        self.manifest = manifest.ManifestStore(paths.runtime_dir, download=download)
        self.game_configs = GameConfigStore(paths.settings_dir)
        self._auto_refresh_manifest = auto_refresh_manifest
        self._manifest_lock = asyncio.Lock()
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
        self._manifest_progress: dict[str, Any] = {"stage": "idle", "running": False}
        self._background: list[asyncio.Task[Any]] = []
        self.emit = emit or _no_emit
        self.proc_root = proc_root
        self.version = version or os.environ.get("DECKY_PLUGIN_VERSION") or "0.0.0"
        paths.ensure()
        setup_logging(paths.log_dir)
        self.settings = SettingsStore(paths.settings_dir)
        self.jobs = JobTracker()
        self.updater = Updater(paths.runtime_dir, self.version, fetch)
        self._fetch = fetch
        self._update_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._notice: dict[str, Any] | None = None
        # v2 Core (slice 13, ADR-0012, ADR-0024): lifecycle bus, per-game locks, module registry, state database.
        self.bus = EventBus()
        self.locks = GameLocks()
        self._op_waiters: dict[int, asyncio.Future[tuple[bool, dict[str, Any]]]] = {}
        self.registry = ModuleRegistry(self.bus, lambda: dict(self.settings.get("moduleFlags")))
        self.db: StateDB | None = None
        self.steam_ops: SteamOps | None = None
        self._register_modules()

    def _register_modules(self) -> None:
        # The two parts left after the strip (ADR-0098): moving games between devices, and installing them.
        self.links: Links | None = None
        self.transfers: Transfers | None = None
        self.incoming: Incoming | None = None
        self.outgoing: Outgoing | None = None
        self.game_links: GameLinks | None = None
        self._sending: dict[str, dict[str, Any]] = {}  # games being prepared to send, by game key
        self._send_tasks: dict[str, asyncio.Task[None]] = {}
        self._pulling: dict[str, dict[str, Any]] = {}  # games asked for from another device, by pull token
        self._pull_tokens: dict[str, dict[str, Any]] = {}  # this device's games listed to a peer, by token
        self._pulls_stopped: set[str] = set()
        self._news: PeerNews | None = None
        self._progress_task: asyncio.Task[None] | None = None
        self._progress_told: dict[str, tuple[Any, ...]] = {}
        self.sys_root = "/sys"
        self.dev_root = "/dev"
        self.power_root = "/"  # where /sys/class/power_supply is read (tests point it elsewhere)
        self._games_running: set[int] = set()
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
                on_state=self._replication_offer_state,
            )
            self.game_links = GameLinks(os.path.join(self.paths.runtime_dir, "replication-games.json"))
            restored = await asyncio.to_thread(self.outgoing.restore)
            self.links.handlers.update(
                {
                    **shares.handlers(),
                    "offer": self.incoming.handle_offer,
                    "offer-state": self._replication_offer_news,
                    # v0.31.0 (ADR-0072): space before sending, Stop from either side, and pulling a game
                    "space-check": self.incoming.handle_space,
                    "offer-stop": self.incoming.handle_stop,
                    "games-list": self._serve_games_list,
                    "pull-check": self._serve_pull_check,
                    "pull": self._serve_pull,
                    "pull-state": self._replication_pull_news,
                    "speed": devicechecks.serve_speed,  # the other side of the link speed check (ADR-0062)
                    # R26 stage 2 (ADR-0087 addendum): emulator games between paired devices
                    "emu-summary": self._serve_emu_summary,
                    "emu-offer": self.incoming.handle_emu_offer,
                }
            )
            if restored:
                log_event(logging.INFO, "replication.offers_restored", "Offered games available again", count=restored)
            self._news = PeerNews(self._replication_connect_for)
            resumed = await self.transfers.start_up()
            if resumed:
                log_event(logging.INFO, "replication.resumed", "Transfers resumed after a restart", count=len(resumed))
                self._progress_pump()

        async def replication_stop() -> None:
            news, self._news = self._news, None
            if news is not None:
                await news.close()
            if self._progress_task is not None:
                self._progress_task.cancel()
                self._progress_task = None
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
                        "keepsake_toast", f"{job['title']}: choose the game's program in Haversack, Installer."
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
            )
        )
        self._navigation_record: dict[str, Any] | None = None

    # Looks (R29 stage 1, ADR-0091)

    # Pause the running game (R29 stage 3, ADR-0094)

    # Controller reconnect help (R22, ADR-0082): every action is gated on the user's rule for that device.

    # Emulator games (R26 stage 1, ADR-0087): read-only

    async def emulator_setup(self) -> dict[str, Any]:
        """This device's emulator setup and games. Game names are shown on this device only."""
        if not self.registry.enabled("replication"):
            return {"off": True, "problem": "Replication is off; switch it on in Settings, Modules"}
        from .replication import emulators

        return await asyncio.to_thread(emulators.scan, discovery.real_home(self.home))

    async def _serve_emu_summary(self, _session: Any, _message: dict[str, Any]) -> dict[str, Any]:
        """The ``emu-summary`` request from a paired device: systems, emulators and settings present, and
        this device's emulator games by system and name. No paths and nothing about key files."""
        from .replication import emuplan

        found = await asyncio.to_thread(emuplan.summary, discovery.real_home(self.home))
        return {"type": "emu-summary", **found}

    async def emulator_peer(self, peer_id: str) -> dict[str, Any]:
        """The paired device's emulator summary, for the copy plan."""
        name = self._peer_name(peer_id)
        try:
            connection = await self._replication_connect_for(str(peer_id))()
            try:
                reply = await connection.request({"type": "emu-summary"})
            finally:
                await connection.close()
        except (replication_link.LinkError, OSError) as exc:
            raise ValueError(f"{capital(name)} could not be reached: {exc}") from exc
        if reply.get("type") != "emu-summary":
            raise ValueError(f"{capital(name)} needs Haversack 0.49 or later to take emulator games")
        return {k: reply.get(k) or [] for k in ("systems", "emulators", "configs", "games")}

    async def emulator_send(self, peer_id: str, system: str, unit: str, with_keys: bool = False) -> dict[str, Any]:
        """Send one emulator game to a paired device (R26 stage 2). Keys only with ``with_keys``, which the
        page asks for separately."""
        from .replication import emulators, emuplan

        home = discovery.real_home(self.home)
        setup = emulators.emudeck(home) or emulators.retrodeck(home)
        if setup is None:
            raise ValueError("this device has no EmuDeck or RetroDECK setup")
        roms = setup["romsPath"]
        game = next(
            (g for g in await asyncio.to_thread(emulators.games, roms) if g.system == system and g.name == unit), None
        )
        if game is None:
            raise ValueError("that game was not found on this device")
        emulator = next((e for e in emulators.emulators(home) if e["system"] == system), None)
        target = await self.emulator_peer(peer_id)
        if [system, unit] in target["games"]:
            raise ValueError(f"{capital(self._peer_name(peer_id))} already has {unit}")
        try:
            plan = await asyncio.to_thread(emuplan.plan, home, roms, game, emulator, target, bool(with_keys))
        except emuplan.EmuPlanError as exc:
            raise ValueError(str(exc)) from exc
        extra = {"from": {"name": self.settings.get("deviceName") or ""}}

        async def send() -> None:
            try:
                wire = await asyncio.to_thread(self._outgoing().prepare_emulator, plan, str(peer_id), extra)
                connection = await self._replication_connect_for(str(peer_id))()
                try:
                    reply = await connection.request({"type": "emu-offer", "offer": wire})
                finally:
                    await connection.close()
                if reply.get("type") == "error":
                    raise ValueError(str(reply.get("reason") or reply.get("message") or "the other device refused it"))
                await self.emit("keepsake_toast", f"{unit} is on its way to {self._peer_name(peer_id)}.")
            except Exception as exc:  # noqa: BLE001 - reported to the user, never left hanging
                log_event(
                    logging.WARNING,
                    "replication.emu_offer_failed",
                    "Emulator game not offered",
                    error=type(exc).__name__,
                )
                await self.emit("keepsake_toast", f"{unit} was not offered: {exc}")

        self._background.append(asyncio.create_task(send()))
        log_event(
            logging.INFO,
            "replication.emu_offer",
            "Emulator game offered",
            parts=sorted(plan.roots),
            keys=bool(with_keys),
        )
        return {"ok": True, "parts": sorted(plan.roots)}

    # The controllers' own settings and stick lights (R24, ADR-0086)

    # Fan control (R24, ADR-0085)

    def _library_root(self) -> str:
        configured = str(self.settings.get("libraryRoot") or "").strip()
        return configured or os.path.join(discovery.real_home(self.home), "Games").replace(os.sep, "/")

    def _prefix_for(self, appid: int) -> str | None:
        for root in discovery.steam_roots(self.home, self.host):
            found = discovery.find_compatdata(int(appid), discovery.library_folders(root))
            if found:
                return found
        return None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._notice = await asyncio.to_thread(startup_notice, self.paths.runtime_dir, self.version)
        if self._notice:
            log_event(logging.INFO, "update.applied", "Running a new version", **self._notice)
        if self.settings.read_only:
            log_event(logging.WARNING, "settings.safe_mode", "Settings were written by a newer version; read-only")
        # Earlier, larger versions wrote Desktop Mode entries for a tray that is gone (ADR-0098).
        removed = await asyncio.to_thread(leftovers.remove_desktop_entries, discovery.real_home(self.home))
        if removed:
            log_event(logging.INFO, "leftovers.desktop_entries", "Old Desktop Mode entries removed", count=len(removed))
        log_event(logging.INFO, "app.start", "Haversack backend started", version=self.version)
        try:
            self.db = await asyncio.to_thread(open_db, self.paths.runtime_dir)
            self.steam_ops = SteamOps(self.db) if self.db else None
        except (StateError, OSError) as exc:  # modules needing state stay off (P13)
            log_event(logging.ERROR, "state.unavailable", "State database unavailable", error=str(exc))
            self.db, self.steam_ops = None, None
        await self.registry.start_all()
        if self._auto_refresh_manifest:
            # Weekly refresh in the background; never blocks start-up. Replication needs it to protect saves.
            self._background.append(asyncio.create_task(self.refresh_manifest(False)))

    # Status and updates

    def status_now(self) -> dict[str, Any]:
        """The status from memory only: no disk and no event loop, so it answers at once from any thread (v0.30.1)."""
        return {
            "version": self.version,
            "safeMode": self.settings.read_only,
            "busy": self.jobs.busy_reason(),
            "scanSlow": self._scan_slow,
        }

    async def get_status(self) -> dict[str, Any]:
        return self.status_now()

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

    def _scan_all(self) -> dict[str, Any]:
        """Disk thread: Steam's libraries and shortcuts (a slow or absent disk only slows this)."""
        return discovery.discover(self.home, self.host)

    async def _scan(self) -> dict[str, Any]:
        """One scan at a time, on the low-priority disk threads, bounded in time (v0.30.1).

        A disk that is slow, spinning up or gone can hold a scan in the kernel; then the last list is
        used and the status says so, and nothing else waits on it.
        """
        loop = asyncio.get_running_loop()
        if self._scan_future is None or self._scan_future.done():
            self._scan_future = loop.run_in_executor(self._disk, self._scan_all)
        try:
            found = await asyncio.wait_for(asyncio.shield(self._scan_future), SCAN_WAIT)
        except TimeoutError:
            if self._games is None:
                raise ValueError(
                    "the game scan is taking a long time (a disk may be slow or offline); try again"
                ) from None
            self._scan_slow = True
            log_event(logging.WARNING, "discovery.slow", "Game scan is slow; using the last list")
            return self._games
        self._scan_slow = False
        return found

    async def discover_games(self, refresh: bool = False) -> dict[str, Any]:
        """Scan Steam on this device. Cached until ``refresh``."""
        if self._games is None or refresh:
            self._games = await self._scan()
            counts: dict[str, int] = {}
            for game in self._games["games"]:
                counts[game["kind"]] = counts.get(game["kind"], 0) + 1
            log_event(logging.INFO, "discovery.scan", "Scanned games", roots=len(self._games["roots"]), **counts)
        mismatches = await asyncio.to_thread(discovery.load_mismatches, self.paths.runtime_dir)
        # Each shortcut's presence from the file and Steam's install state (ADR-0064). Steam Remote Play's
        # streaming entries are not in shortcuts.vdf, so they never reach this list.
        games = await asyncio.to_thread(self.remote_copies.apply, self._games["games"])
        return {**self._games, "games": games, "mismatches": mismatches}

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

    # Suspend snapshots (slice 11, ADR-0022)

    # Play sessions (ADR-0069): measured while a game runs, read only, summaries kept for the Advisor

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

    async def set_game_key(self, key: str, game_key_value: str | None, title: str | None = None) -> dict[str, Any]:
        """Use a suggested or new game key (or clear it). Chosen by the user, so any proposal is settled."""
        changes: dict[str, Any] = {"gameKey": game_key_value, "gameKeySource": "user" if game_key_value else None}
        if title is not None:
            changes["matchTitle"] = title
        config = await self.update_game_config(key, changes)
        if game_key_value:
            self._clear_proposal(key)
        return config

    async def search_titles(self, query: str) -> list[str]:
        index = await asyncio.to_thread(self.manifest.load)
        return manifest.search_titles(index, str(query)[:200]) if index else []

    async def update_game_config(self, key: str, changes: dict[str, Any]) -> dict[str, Any]:
        await self._game(key)
        if "matchTitle" in changes and changes["matchTitle"] is not None:
            index = await asyncio.to_thread(self.manifest.load)
            if not index or changes["matchTitle"] not in index.get("games", {}):
                raise ValueError("that title is not in the manifest")
        config = await asyncio.to_thread(self.game_configs.update, key, dict(changes))
        log_event(logging.INFO, "game.config", "Game settings changed", key=key, fields=sorted(changes))
        return config

    # Credentials: the SteamGridDB key (Install's artwork) and network-location passwords

    async def backend_config(self, backend: str) -> dict[str, Any]:
        return self.credentials.public(str(backend))

    async def set_backend_config(self, backend: str, values: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(self.credentials.save, str(backend), dict(values))
        except BackendConfigError as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "backend.config", "Backend settings saved", backend=backend)
        return result

    async def on_game_event(self, kind: str, raw_id: Any) -> dict[str, Any]:
        """A game started or exited (from the frontend). Replication and Install listen (ADR-0098)."""
        event = {"start": "game_started", "exit": "game_exited"}.get(kind)
        try:
            appid = normalise_appid(raw_id)
        except (ValueError, TypeError):
            return {"handled": 0}
        # An update waits while any game runs (build prompt section 12).
        if kind == "start":
            self.jobs.open_session(str(appid))
        elif kind == "exit":
            self.jobs.close_session(str(appid))
        if event:
            await self.bus.publish(event, {"gameKey": None, "appid": appid})
        return {"handled": 1 if event else 0}

    async def _game_key_of(self, key: str) -> str | None:
        game = await self._game(key)
        index = await asyncio.to_thread(self.manifest.load)
        found = manifest.match_game(index, game, self.game_configs.get(key)).get("gameKey")
        return str(found) if found else None

    # Desktop (ADR-0068): the plugin serves the desktop interface on loopback and writes the tray's entries

    # Storage (R5, ADR-0052): disk use, shader cache, reset prefix and keep saves

    # Trust (R3, ADR-0050): cloud integrity and export

    # Shared game settings (config revisions in the cloud)

    # Ludusavi import (slice 10, ADR-0021)

    # Modules and the Steam Operations Executor (slice 13)

    # Import every game at once (Peter, 16 November 2026)

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
        # Flags of modules removed in the strip (ADR-0098) are dropped, or the whole setting would be refused.
        flags = {k: v for k, v in dict(self.settings.get("moduleFlags")).items() if k in SETTINGS_MODULE_NAMES}
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
        """The frontend's reading of Steam's library, for Install's artwork for streaming tiles (ADR-0081)."""
        return await asyncio.to_thread(self.remote_copies.save_report, entries)

    # Steam operations (ADR-0015): queued here, run by the frontend through the Steam client

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
            if pairing.state == "request" and not pairing.announced:
                # The page shows Accept and Decline, or, while a game runs, only a notification (ADR-0070).
                pairing.announced = True
                request = {"id": pairing.id, "name": pairing.peer_name or "Another device", "address": pairing.address}
                asyncio.get_running_loop().create_task(self.emit(PAIR_REQUEST_EVENT, request))
        self._replication_two_way(links)

    def _replication_two_way(self, links: Links) -> None:
        """Pairing is trust both ways (ADR-0072): a device that started a pairing becomes reachable too.

        Sending needs both directions (the offer goes one way, the files come back the other), so
        a finished pairing switches this device's listener on for paired devices, and says so.
        """
        for pairing in list(links.initiated.values()):
            if pairing.state != "paired" or pairing.two_way:
                continue
            pairing.two_way = True
            if links.listener is None and replication_link.available():
                name = pairing.peer_name or "The other device"
                asyncio.get_running_loop().create_task(self._open_for_peer(name))

    async def _open_for_peer(self, name: str) -> None:
        try:
            await self._replication(lambda links: links.set_listener(True))
        except ValueError as exc:
            await self.emit("keepsake_toast", f"Paired with {name}, but it cannot reach this device yet: {exc}")
            return
        self.settings.set("replicationListener", True)
        log_event(logging.INFO, "replication.listener", "Listener switched on by a pairing", on=True)
        await self.emit("keepsake_toast", f"Paired with {name}. Games can now go both ways between you.")
        self._replication_changed()

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

    async def replication_pair(self, address: str) -> dict[str, Any]:
        """Send a pairing request to a found or typed address (ADR-0070)."""
        pairing: dict[str, Any] = await self._replication(lambda links: links.pair_with(str(address)))
        log_event(logging.INFO, "replication.pair_start", "Pairing started")
        return pairing

    async def replication_answer(self, pairing_id: str, ok: bool) -> dict[str, Any]:
        """Accept or Decline a pairing request on this device."""
        await self._replication(lambda links: links.answer(str(pairing_id), bool(ok)))
        log_event(logging.INFO, "replication.pair_answer", "Pairing request answered", accepted=bool(ok))
        return await self.replication_status()

    async def replication_enter_code(self, pairing_id: str, code: str) -> dict[str, Any]:
        """The code the other device shows, typed here (never logged)."""
        await self._replication(lambda links: links.enter_code(str(pairing_id), str(code)))
        log_event(logging.INFO, "replication.pair_code", "Pairing code entered")
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
        peer = links.store.get(str(peer_id))
        if peer is None:
            raise ValueError("that device is not paired")
        key, peer_id = str(key), str(peer_id)
        state: dict[str, Any] = {"state": "preparing", "stage": "checking-space", "title": "", "peer": peer_id}
        try:
            plan, _warning, extra = await self._prepare_send(key, peer_id, state, check_space=True)
        except ValueError as exc:
            if state["title"]:
                state.update(state="failed", stage="failed", reason=str(exc))
                self._replication_changed()
            raise
        self._background.append(asyncio.create_task(self._send_game(key, plan, peer_id, extra)))
        return state | {"droppedOptions": plan.dropped_options}

    async def _prepare_send(
        self, key: str, peer_id: str, state: dict[str, Any], check_space: bool, pull: str | None = None
    ) -> tuple[Any, str | None, dict[str, Any]]:
        """The quick steps before a send, shared by Send and by another device's Get this game.

        The plan, the space check on the other device (skipped when that device asked: it checked
        its own space), then the source checkpoint. Raises ValueError with a plain reason.
        """
        game = await self._game(key)
        places = self._replication_places()
        try:
            plan = await asyncio.to_thread(send_plan, dict(game), places["home"], places["library"], places["tools"])
        except SendError as exc:
            raise ValueError(str(exc)) from exc
        state["title"] = plan.title
        self._sending[key] = state
        self._replication_changed()
        if check_space:
            await self._peer_space_check(peer_id, plan)
        state["stage"] = "preparing"
        self._replication_changed()
        config = self.game_configs.get(key)
        warning = None
        extra = {
            "from": {"name": str(self.settings.get("deviceName") or "Unnamed device")},
            # The receiver uses the game key to find the game's saves and protect them on updates.
            "gameKey": config.get("gameKey"),
            "savesEnabled": False,  # save sync is gone (ADR-0098); older devices read this
            **({"pull": pull} if pull else {}),
        }
        state["warning"] = warning
        return plan, warning, extra

    async def _peer_space_check(self, peer_id: str, plan: Any) -> None:
        """Ask the other device whether the game fits, before reading every file (ADR-0072)."""
        sizes = await asyncio.to_thread(send_sizes, plan)
        name = self._peer_name(peer_id)
        try:
            connection = await self._replication_connect_for(peer_id)()
            try:
                reply = await connection.request(
                    {"type": "space-check", "bytes": sizes, "compatTool": plan.compat_tool}
                )
            finally:
                await connection.close()
        except (replication_link.LinkError, OSError) as exc:
            raise ValueError(f"{capital(name)} could not be reached: {exc}") from exc
        if reply.get("type") == "error":
            log_event(logging.INFO, "replication.space_unknown", "The other device has no space check")
            return  # an older Keepsake: its own check runs when the copy starts
        if not reply.get("ok"):
            if reply.get("reason"):
                raise ValueError(f"{capital(name)} cannot take it: {reply['reason']}")
            raise ValueError(space_text(name, int(reply.get("needed") or 0), int(reply.get("free") or 0)))

    def _peer_name(self, peer_id: str) -> str:
        links = self.links
        peer = links.store.get(peer_id) if links is not None else None
        return str((peer or {}).get("name") or "the other device")

    async def _send_game(self, key: str, plan: Any, peer_id: str, extra: dict[str, Any]) -> None:
        state = self._sending[key]
        task = asyncio.current_task()
        if task is not None:
            self._send_tasks[key] = task
        try:
            wire = await asyncio.to_thread(self._outgoing().prepare, plan, peer_id, extra)
            connection = await self._replication_connect_for(peer_id)()
            try:
                await send_offer(connection, wire)
            finally:
                await connection.close()
            state.update(state="sent", stage="copying", offer=wire["id"])
            self._sending.pop(key, None)  # the offer's own entry takes over
            game = await self._game(key)
            scopes = {s: r for s, r in plan.roots.items() if s in ("install", "prefix")}
            self._link_game(wire["id"], plan.title, peer_id, int(game["appid"]), scopes, dict(game))
            await self.emit("keepsake_toast", f"{plan.title} is on its way to {self._peer_name(peer_id)}.")
        except asyncio.CancelledError:
            self._sending.pop(key, None)  # Stop and remove before the offer went
            raise
        except Exception as exc:  # noqa: BLE001 - whatever goes wrong, the page must not say "preparing" for ever
            reason = str(exc) or type(exc).__name__
            state.update(state="failed", stage="failed", reason=reason)
            log_event(logging.WARNING, "replication.offer_failed", "Offer not sent", error=type(exc).__name__)
            await self.emit("keepsake_toast", f"{plan.title} was not offered: {reason}")
            if extra.get("pull") and self._news is not None:
                message = {
                    "type": "pull-state",
                    "game": extra["pull"],
                    "state": "failed",
                    "reason": wire_reason(reason),
                }
                self._news.tell(peer_id, f"pull:{extra['pull']}", message, final=True)
        finally:
            self._send_tasks.pop(key, None)
        self._replication_changed()

    async def replication_offers(self) -> dict[str, Any]:
        return {
            "incoming": await asyncio.to_thread(self._incoming().list),
            "outgoing": await asyncio.to_thread(self._outgoing().list),
            "sending": self._sending,
            "activity": await self.replication_activity(),
        }

    async def replication_activity(self) -> list[dict[str, Any]]:
        """Every game moving between devices, as bars for the pages and the quick access menu (ADR-0072).

        Empty when Replication is off. Read from memory and two small files, so a page can ask
        every second while something moves.
        """
        incoming, outgoing, links = self.incoming, self.outgoing, self.links
        if incoming is None or outgoing is None or links is None:
            return []
        names = {str(p["id"]): str(p.get("name") or "the other device") for p in links.store.list()}
        out = [
            replication_activity.preparing(
                f"pull:{token}", "receiving", p["title"], names.get(p["peer"], "the other device"), p
            )
            for token, p in self._pulling.items()
        ]
        out += await asyncio.to_thread(incoming.activity, names)
        out += [
            replication_activity.preparing(
                f"send:{key}", "sending", s["title"], names.get(s["peer"], "the other device"), s
            )
            for key, s in self._sending.items()
            if s.get("state") != "sent" and s.get("title")
        ]
        out += await asyncio.to_thread(outgoing.activity, names)
        return out

    async def replication_stop_game(self, entry_id: str) -> list[dict[str, Any]]:
        """Stop and remove, from either device (ADR-0072). Confirmed on the page.

        On the receiving device it removes everything the copy made. On the sending device it asks
        the receiving one to do that, then withdraws the offer; if that device cannot be reached,
        its copy fails once the files are no longer offered, and it can be removed there.
        """
        entry_id = str(entry_id)
        if entry_id.startswith("send:"):
            key = entry_id[5:]
            task = self._send_tasks.get(key)
            if task is not None:
                task.cancel()
            self._sending.pop(key, None)
        elif entry_id.startswith("pull:"):
            token = entry_id[5:]
            self._pulling.pop(token, None)
            self._pulls_stopped.add(token)  # an offer that still comes for it is declined
        elif await asyncio.to_thread(lambda: entry_id in self._incoming()._load()):
            await self.replication_remove_game(entry_id)
        else:
            outgoing = self._outgoing()
            peer_id = await asyncio.to_thread(outgoing.peer_of, entry_id)
            if peer_id is None:
                raise ValueError("that game is no longer moving")
            try:
                connection = await self._replication_connect_for(peer_id)()
                try:
                    await asyncio.wait_for(connection.request({"type": "offer-stop", "id": entry_id}), 30)
                finally:
                    await connection.close()
            except (replication_link.LinkError, OSError, TimeoutError) as exc:
                log_event(
                    logging.INFO, "replication.stop_unreached", "Could not ask the other device to stop", error=str(exc)
                )
            try:
                await asyncio.to_thread(outgoing.withdraw, entry_id)
            except OfferError:
                pass  # the other device's "removed" withdrew it first
        log_event(logging.INFO, "replication.stopped_game", "Game transfer stopped and removed")
        self._replication_changed()
        return await self.replication_activity()

    async def replication_clear_game(self, entry_id: str) -> list[dict[str, Any]]:
        """Clear a finished or failed bar. A failed copy on this device is removed, as Stop and remove does."""
        entry_id = str(entry_id)
        if entry_id.startswith("send:"):
            self._sending.pop(entry_id[5:], None)
        elif entry_id.startswith("pull:"):
            self._pulling.pop(entry_id[5:], None)
        else:
            record = (await asyncio.to_thread(self._incoming()._load)).get(entry_id)
            if record is not None and record.get("state") == "done":
                await asyncio.to_thread(self._incoming().dismiss, entry_id)
            elif record is not None:
                await self._incoming().stop(entry_id)
            else:
                try:
                    await asyncio.to_thread(self._outgoing().withdraw, entry_id)
                except OfferError:
                    pass
        self._replication_changed()
        return await self.replication_activity()

    async def replication_offer_check(self, offer_id: str, copy_tool: bool = False) -> dict[str, Any]:
        """Where an offered game would go, and what is missing, before the user accepts."""
        try:
            return await asyncio.to_thread(self._incoming().preflight, str(offer_id), bool(copy_tool))
        except (OfferError, OSError) as exc:
            return {"problem": str(exc)}

    async def replication_accept(self, offer_id: str, copy_tool: bool = False) -> dict[str, Any]:
        incoming = self._incoming()
        try:
            jobs = await asyncio.to_thread(incoming.begin, str(offer_id), bool(copy_tool))
        except (OfferError, transfer.TransferError, OSError) as exc:
            raise ValueError(str(exc)) from exc
        # The copies are asyncio tasks, so they start here on the event loop, never in the worker
        # thread that checked and planned them (the v0.30.1 stall: they never started).
        incoming.start_jobs(str(offer_id), jobs)
        self._progress_pump()
        log_event(logging.INFO, "replication.accepted", "Offered game accepted", copyTool=bool(copy_tool))
        return await asyncio.to_thread(incoming._public, str(offer_id))

    async def _auto_accept(self, offer: dict[str, Any]) -> None:
        """A new game from a paired device starts copying by itself (ADR-0072, replacing ADR-0059's Accept).

        The same checks run as when Accept was pressed: nothing replaced, space with margin, the
        compatibility tool copied when this device lacks it. A refusal fails the offer with the
        reason, shown on both devices.
        """
        incoming = self._incoming()
        try:
            jobs = await asyncio.to_thread(incoming.begin, offer["id"], True)
        except (OfferError, transfer.TransferError, OSError) as exc:
            await asyncio.to_thread(incoming.fail, offer["id"], str(exc))
            return
        incoming.start_jobs(offer["id"], jobs)
        self._progress_pump()
        log_event(logging.INFO, "replication.auto_accepted", "Game from a paired device started copying")

    def _progress_pump(self) -> None:
        """While games come in, tell their senders the progress about once a second."""
        if self._progress_task is None or self._progress_task.done():
            self._progress_task = asyncio.get_running_loop().create_task(self._pump_progress())

    async def _pump_progress(self) -> None:
        while self.incoming is not None and self._news is not None:
            entries = await asyncio.to_thread(self.incoming.activity, {})
            moving = [e for e in entries if e["stage"] not in ("done", "failed")]
            records = await asyncio.to_thread(self.incoming._load)
            for entry in moving:
                record = records.get(entry["id"])
                if record is None:
                    continue
                told = (entry["stage"], entry["done"] // (1 << 20), entry["secondsLeft"])
                if self._progress_told.get(entry["id"]) == told:
                    continue
                self._progress_told[entry["id"]] = told
                message = {
                    "type": "offer-state",
                    "id": entry["id"],
                    "state": record.get("state"),
                    "reason": wire_reason(entry.get("reason")),
                    **replication_activity.wire(entry),
                }
                self._news.tell(str(record["peer"]), entry["id"], message)
            if not moving:
                return
            self._replication_changed()
            await asyncio.sleep(PROGRESS_SECONDS)

    def _replication_offer_state(self, offer_id: str, record: dict[str, Any]) -> None:
        """An offer this device received changed state: tell the device that sent it (v0.30.2).

        Called from worker threads too. Best effort, with two retries: the other device's list
        catches up whenever it is told. Only the state and a path-free reason go over the link.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._replication_offer_state, offer_id, record)
            return
        state = record.get("state")
        message: dict[str, Any] = {
            "type": "offer-state",
            "id": offer_id,
            "state": state,
            "reason": wire_reason(record.get("reason")),
        }
        if record.get("offer", {}).get("shares") and state not in ("declined", "removed"):
            jobs = {}
            if self.transfers is not None:
                jobs = {j: self.transfers.jobs[j] for j in record.get("jobs", {}).values() if j in self.transfers.jobs}
            message.update(replication_activity.wire(replication_activity.receiving(offer_id, record, jobs, "")))
        title = record.get("offer", {}).get("title") or "The game"
        if state == "failed":
            self._background.append(
                loop.create_task(self.emit("keepsake_toast", f"{title} did not arrive: {record.get('reason')}"))
            )
        elif state == "transferring" and not record.get("offer", {}).get("update"):
            sender = record.get("offer", {}).get("from") or "the other device"
            self._background.append(loop.create_task(self.emit("keepsake_toast", f"{title} is coming from {sender}.")))
        if self._news is not None:
            final = state in ("done", "failed", "declined", "removed")
            self._news.tell(str(record.get("peer")), offer_id, message, final=final)

    async def _replication_offer_news(self, session: Any, message: dict[str, Any]) -> dict[str, Any]:
        """The ``offer-state`` request: news from the device an offer went to (v0.30.2)."""
        outgoing = self.outgoing
        if outgoing is None:
            raise replication_link.ServeError("Replication is off on this device")
        changed = await asyncio.to_thread(
            outgoing.record_state,
            session.peer_id,
            message.get("id"),
            message.get("state"),
            message.get("reason"),
            message,
        )
        if changed:
            self._replication_changed()
        if changed and changed["stateChanged"]:
            title, name = changed["title"] or "The game", self._peer_name(session.peer_id)
            state = changed["state"]
            if state == "failed":
                await self.emit("keepsake_toast", f"{title} did not arrive on {name}: {changed['reason']}")
            elif state == "done":
                await self.emit("keepsake_toast", f"{title} arrived on {name}.")
            elif state == "transferring":
                await self.emit("keepsake_toast", f"{title} is copying to {name}.")
            elif state in ("removed", "declined"):
                with contextlib.suppress(OfferError):
                    await asyncio.to_thread(outgoing.withdraw, str(changed["id"]))  # its files are no longer needed
                word = "stopped and removed" if state == "removed" else "declined"
                await self.emit("keepsake_toast", f"{capital(name)} {word} {title}.")
                self._replication_changed()
        return {"type": "offer-state-received", "id": message.get("id")}

    # Getting a game from another device (ADR-0072)

    def _pull_key(self, session: Any, message: dict[str, Any]) -> str:
        token = message.get("game")
        held = self._pull_tokens.get(token) if isinstance(token, str) else None
        if held is None or held["peer"] != session.peer_id or held["expires"] < time.time():
            raise replication_link.ServeError("that game list is out of date; open it again")
        return str(held["key"])

    async def _serve_games_list(self, session: Any, message: dict[str, Any]) -> dict[str, Any]:
        """The ``games-list`` request: the non-Steam games a paired device may take from here.

        Each gets a fresh random token, valid for that device for 15 minutes: no app ID, key or
        path goes over the link (principle 10).
        """
        games = (await self.discover_games())["games"]

        def sendable() -> list[dict[str, Any]]:
            return [
                g for g in games if g.get("kind") == "shortcut" and os.path.isfile(str(g.get("exe") or "").strip('"'))
            ]

        now = time.time()
        self._pull_tokens = {k: v for k, v in self._pull_tokens.items() if v["expires"] > now}
        listed = []
        for game in (await asyncio.to_thread(sendable))[:PULL_LIST_MAX]:
            token = secrets.token_hex(8)
            self._pull_tokens[token] = {
                "key": game["key"],
                "peer": session.peer_id,
                "expires": now + PULL_TOKEN_SECONDS,
            }
            listed.append({"id": token, "title": str(game.get("name") or "A game")[:200]})
        return {"type": "games", "games": sorted(listed, key=lambda g: g["title"].casefold())}

    async def _serve_pull_check(self, session: Any, message: dict[str, Any]) -> dict[str, Any]:
        """The ``pull-check`` request: what a game would need, so the asking device checks its own space."""
        key = self._pull_key(session, message)
        game = await self._game(key)
        places = self._replication_places()
        try:
            plan = await asyncio.to_thread(send_plan, dict(game), places["home"], places["library"], places["tools"])
        except SendError as exc:
            raise replication_link.ServeError(str(exc)) from exc
        sizes = await asyncio.to_thread(send_sizes, plan)
        return {"type": "pull-size", "title": plan.title, "bytes": sizes, "compatTool": plan.compat_tool}

    async def _serve_pull(self, session: Any, message: dict[str, Any]) -> dict[str, Any]:
        """The ``pull`` request: a paired device pressed Get this game. Allowed by the pairing itself."""
        key = self._pull_key(session, message)
        token = str(message["game"])
        self._pull_tokens.pop(token, None)  # one pull per listing
        self._background.append(asyncio.create_task(self._serve_pull_task(key, session.peer_id, token)))
        return {"type": "pull-started", "game": token}

    async def _serve_pull_task(self, key: str, peer_id: str, token: str) -> None:
        state: dict[str, Any] = {"state": "preparing", "stage": "preparing", "title": "", "peer": peer_id}
        try:
            plan, _warning, extra = await self._prepare_send(key, peer_id, state, check_space=False, pull=token)
        except ValueError as exc:
            state.update(state="failed", stage="failed", reason=str(exc))
            if self._news is not None:
                failed = {"type": "pull-state", "game": token, "state": "failed", "reason": wire_reason(str(exc))}
                self._news.tell(peer_id, f"pull:{token}", failed, final=True)
            self._replication_changed()
            return
        await self.emit("keepsake_toast", f"{plan.title} is being copied to {self._peer_name(peer_id)}.")
        await self._send_game(key, plan, peer_id, extra)

    async def _replication_pull_news(self, session: Any, message: dict[str, Any]) -> dict[str, Any]:
        """The ``pull-state`` request: the device a game was asked from could not send it."""
        token = message.get("game")
        pending = self._pulling.get(token) if isinstance(token, str) else None
        if pending is None or pending["peer"] != session.peer_id:
            raise replication_link.ServeError("no such game was asked for")
        if message.get("state") == "failed":
            reason = wire_reason(str(message.get("reason") or "")) or "it could not be sent"
            pending.update(state="failed", stage="failed", reason=reason)
            await self.emit("keepsake_toast", f"{pending['title']} could not be copied: {reason}")
            self._replication_changed()
        return {"type": "pull-state-received", "game": token}

    async def replication_peer_games(self, peer_id: str) -> list[dict[str, Any]]:
        """Games on a paired device that this device can get (a user action: Games on <device>)."""
        peer_id = str(peer_id)
        if self._links().store.get(peer_id) is None:
            raise ValueError("that device is not paired")
        try:
            connection = await self._replication_connect_for(peer_id)()
            try:
                reply = await connection.request({"type": "games-list"})
            finally:
                await connection.close()
        except (replication_link.LinkError, OSError) as exc:
            raise ValueError(f"{self._peer_name(peer_id)} could not be reached: {exc}") from exc
        if reply.get("type") == "error":
            raise ValueError(f"update Haversack on {self._peer_name(peer_id)} to get games from it")
        listed = reply.get("games")
        games: list[Any] = listed if isinstance(listed, list) else []
        return [
            {"id": str(g["id"]), "title": " ".join(str(g.get("title") or "").split())[:200]}
            for g in games[:PULL_LIST_MAX]
            if isinstance(g, dict) and isinstance(g.get("id"), str) and re.fullmatch(r"[0-9a-f]{16}", g["id"])
        ]

    async def replication_get_game(self, peer_id: str, game_id: str, title: str = "") -> list[dict[str, Any]]:
        """Get this game: the same as a send, started from this side (ADR-0072).

        This device checks its own space first, then asks the other device to send it. The offer
        that comes back starts copying by itself.
        """
        peer_id, token = str(peer_id), str(game_id)
        if not re.fullmatch(r"[0-9a-f]{16}", token):
            raise ValueError("that game is not valid")
        name = self._peer_name(peer_id)
        pending = {
            "state": "preparing",
            "stage": "checking-space",
            "title": " ".join(title.split())[:200] or "A game",
            "peer": peer_id,
        }
        self._pulling[token] = pending
        self._replication_changed()
        try:
            connection = await self._replication_connect_for(peer_id)()
            try:
                sized = await connection.request({"type": "pull-check", "game": token})
                if sized.get("type") != "pull-size":
                    raise ValueError(str(sized.get("reason") or f"{capital(name)} would not send it"))
                pending["title"] = " ".join(str(sized.get("title") or pending["title"]).split())[:200]
                given = sized.get("bytes")
                raw: dict[Any, Any] = given if isinstance(given, dict) else {}
                sizes = {
                    str(k): int(v)
                    for k, v in raw.items()
                    if k in ("install", "prefix", "tool", "art") and isinstance(v, int) and v >= 0
                }
                tool = sized.get("compatTool") if isinstance(sized.get("compatTool"), str) else None
                fits = await asyncio.to_thread(self._incoming().space_check, sizes, tool)
                if not fits["ok"]:
                    me = str(self.settings.get("deviceName") or "This device")
                    raise ValueError(fits["reason"] or space_text(me, int(fits["needed"]), int(fits["free"])))
                started = await connection.request({"type": "pull", "game": token})
                if started.get("type") != "pull-started":
                    raise ValueError(str(started.get("reason") or f"{capital(name)} would not send it"))
            finally:
                await connection.close()
        except (replication_link.LinkError, OSError) as exc:
            pending.update(state="failed", stage="failed", reason=f"{capital(name)} could not be reached: {exc}")
            self._replication_changed()
            raise ValueError(pending["reason"]) from exc
        except ValueError as exc:
            pending.update(state="failed", stage="failed", reason=str(exc))
            self._replication_changed()
            raise
        pending.update(stage="preparing", reason=f"{capital(name)} is reading the game's files")
        log_event(logging.INFO, "replication.pull", "Asked a paired device for a game")
        self._replication_changed()
        return await self.replication_activity()

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

    # Keeping games in step (slice 20, ADR-0060)

    def _game_links(self) -> GameLinks:
        if self.game_links is None:
            raise ValueError("Replication is off; switch it on in Settings, Modules")
        return self.game_links

    def _replication_keep(self, game: dict[str, Any], scopes: dict[str, str]) -> dict[str, list[str]]:
        """Every save and config file the manifest lists for the game, per share: never part of an update (ADR-0098)."""
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
        incoming = self._incoming()
        try:
            jobs = await asyncio.to_thread(incoming.begin_update, str(offer_id), link["scopes"], keep)
        except (OfferError, transfer.TransferError, OSError) as exc:
            raise ValueError(str(exc)) from exc
        incoming.start_jobs(str(offer_id), jobs)  # on the event loop, as in replication_accept
        links.update(str(offered["link"]), state="updating", pending=str(offer_id))
        return await asyncio.to_thread(incoming._public, str(offer_id))

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
        """A new game starts copying by itself (ADR-0072). An update for a game set to auto is applied
        by itself, unless this device changed it too; other updates wait for the user."""
        update = offer.get("update")
        if not update:
            pull = offer.get("pull")
            if pull and pull in self._pulls_stopped:
                self._pulls_stopped.discard(pull)
                with contextlib.suppress(OfferError):
                    self._incoming().decline(offer["id"])  # stopped here while the other device prepared it
                return
            if pull:
                self._pulling.pop(pull, None)  # the offer's own bar takes over
            self._background.append(asyncio.create_task(self._auto_accept(offer)))
            return
        links = self.game_links
        if links is None:
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

    async def installer_stream_tiles(self) -> list[dict[str, Any]]:
        """Streaming tiles for non-Steam games on another device (R18, ADR-0081), from Steam's own report."""
        report = await asyncio.to_thread(self.remote_copies.report)
        return [
            {"appid": e["appid"], "name": e["name"], "devices": e.get("clients", [])}
            for e in report.get("entries", [])
            if e.get("steam") == discovery.REMOTE and int(e["appid"]) >= 2**31
        ]

    async def installer_stream_art_search(self, title: str) -> list[dict[str, Any]]:
        try:
            return await asyncio.to_thread(self._installer().search_titles, str(title)[:80])
        except InstallerError as exc:
            raise ValueError(str(exc)) from exc

    async def installer_stream_art_apply(self, appid: int, game_id: int) -> dict[str, Any]:
        """User action: add SteamGridDB's artwork to one streaming tile, through Steam (P15)."""
        tiles = {t["appid"] for t in await self.installer_stream_tiles()}
        if int(appid) not in tiles:
            raise ValueError("that is not a streaming tile for a non-Steam game")
        try:
            queued = await asyncio.to_thread(self._installer().queue_stream_art, int(appid), int(game_id))
        except InstallerError as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "installer.stream_art", "Artwork queued for a streaming tile", images=queued)
        await self.emit("keepsake_steam_ops")
        return {"queued": queued}

    # Library extras (R29 stage 2, ADR-0093)
    # A grid file's suffix to Steam's library asset type.
    ART_SUFFIX: ClassVar[dict[str, int]] = {"p": 0, "": 3, "_hero": 1, "_logo": 2}
    ART_LABELS: ClassVar[dict[int, str]] = {0: "cover", 3: "wide cover", 1: "background", 2: "logo"}

    @classmethod
    def _missing_art(cls, game: dict[str, Any]) -> list[int]:
        """The kinds of library artwork a game has no custom image for, in Steam's grid folder."""
        appid = str(game.get("appid") or "")
        has = set()
        for name in game.get("artwork") or []:
            stem = os.path.splitext(str(name))[0]
            if stem.startswith(appid) and stem[len(appid) :] in cls.ART_SUFFIX:
                has.add(cls.ART_SUFFIX[stem[len(appid) :]])
        return [t for t in (0, 3, 1, 2) if t not in has]

    async def game_art_status(self, key: str) -> dict[str, Any]:
        """For a non-Steam game: which kinds of artwork it lacks, so Find artwork fills only those."""
        game = await self._game(str(key))
        non_steam = int(game.get("appid") or 0) >= 2**31
        missing = self._missing_art(game) if non_steam else []
        return {
            "nonSteam": non_steam,
            "missing": [self.ART_LABELS[t] for t in missing],
            "available": self.installer is not None and non_steam,
        }

    async def game_art_apply(self, key: str, game_id: int) -> dict[str, Any]:
        """User action: SteamGridDB's images for the kinds of artwork the game lacks, set through Steam (P15)."""
        game = await self._game(str(key))
        try:
            queued = await asyncio.to_thread(
                self._installer().queue_game_art, int(game["appid"]), int(game_id), set(self._missing_art(game))
            )
        except InstallerError as exc:
            raise ValueError(str(exc)) from exc
        log_event(logging.INFO, "installer.game_art", "Artwork queued for a non-Steam game", images=queued)
        await self.emit("keepsake_steam_ops")
        return {"queued": queued}

    async def installer_handoff(self, job_id: int) -> dict[str, Any]:
        """The Games list key for a finished install, so Install can open it in Games (ADR-0098)."""
        job = await self._installer_call("get", int(job_id))
        if job["state"] != "done":
            raise ValueError("the install has not finished")
        games = (await self.discover_games(True))["games"]
        game = next((g for g in games if g["appid"] == job["appid"]), None)
        if game is None:
            raise ValueError("Haversack cannot see the new shortcut yet; try again in a moment")
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
        if smbshare.is_smb(url):  # also \\server\share, as File Explorer writes it (Share parses it)
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
            address = smbshare.parse(url)  # also takes \\\\server\\share, as File Explorer writes it
            same = (address.host, address.port) == (session.home, session.address.port)
            target = address.url(folder=what == "browse")
        else:
            target = remote.check_location(webdav.to_http(url) if webdav.is_dav(url) else url)
            same = (urlsplit(target).hostname or "").lower() == session.home
        if not same:
            raise remote.RemoteError(f"{what} within the location you chose")
        return target

    @staticmethod
    def _net_unexpected(what: str, exc: BaseException) -> str:
        log_event(
            logging.WARNING,
            "installer.net_unexpected",
            "Network install step failed",
            step=what,
            error=type(exc).__name__,
        )
        return (
            f"Haversack could not {what} ({type(exc).__name__}). Check the address, user name and "
            "password; if it keeps happening, export diagnostics from Settings."
        )

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
        except Exception as exc:  # a plain message, never a raw exception (v0.30.2)
            raise ValueError(self._net_unexpected("remember that location", exc)) from exc

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
        except Exception as exc:  # a plain message on the page, never a raw exception (v0.30.2)
            raise ValueError(self._net_unexpected("browse that location", exc)) from exc
        folder = target if target.endswith("/") else target + "/"
        return {"url": webdav.to_dav(folder) if isinstance(session, webdav.DavSession) else folder, "entries": entries}

    async def installer_net_find_smb(self) -> dict[str, Any]:
        """User action: SMB servers answering on the local network (ADR-0066). Read only; nothing is mounted."""
        self._installer()
        try:
            found = await asyncio.to_thread(lanfind.find_servers, 2.5, self._lan_sockets)
        except Exception as exc:  # a plain message, never a raw exception (v0.30.2)
            raise ValueError(self._net_unexpected("search your network", exc)) from exc
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

    async def stop(self) -> None:
        for task in self._background:
            task.cancel()
        self._disk.shutdown(wait=False, cancel_futures=True)  # a scan held by a slow disk is left behind
        await self.registry.stop_all()
        if self.db is not None:
            self.db.close()
            self.db, self.steam_ops = None, None
        log_event(logging.INFO, "app.stop", "Haversack backend stopped")

    # Settings

    async def get_settings(self) -> dict[str, Any]:
        return self.settings.all()

    async def set_setting(self, key: str, value: Any) -> dict[str, Any]:
        result = self.settings.set(key, value)
        log_event(logging.INFO, "settings.changed", "Setting changed", key=key)
        if key == "deviceName" and self.links is not None:
            # Replication starts with the app now (ADR-0098), often before the device is named: the running
            # link, listener and discovery share this identity, so a rename reaches the next hello at once.
            self.links.me.name = str(self.settings.get("deviceName") or "Unnamed device")
        if key == "qamShortcuts":
            await self.emit(SHORTCUTS_EVENT)  # the quick access menu shows the change at once
        return result

    # Quick menu shortcuts (layout v3 addendum, ADR-0073)

    async def qam_shortcuts(self) -> dict[str, Any]:
        """Every shortcut this device can show, the ones chosen (in order), and the defaults."""
        modules = {name: self.registry.enabled(name) for name in SETTINGS_MODULE_NAMES}
        offered = shortcuts.available(modules, ["updates"])
        chosen = self.settings.get("qamShortcuts")
        return {
            "available": offered,
            "shown": shortcuts.shown(chosen, offered),
            "chosen": list(shortcuts.DEFAULT) if chosen is None else list(chosen),
            "defaults": list(shortcuts.DEFAULT),
        }

    async def run_shortcut(self, shortcut_id: str) -> dict[str, Any]:
        """Run an action shortcut from the quick access menu. ``open`` asks the page to open a tab instead."""
        offered = {e["id"]: e for e in (await self.qam_shortcuts())["available"]}
        entry = offered.get(str(shortcut_id))
        if entry is None or entry["kind"] != "action":
            raise ValueError("that shortcut is not available here")
        sid = entry["id"]
        if sid == "get-game":
            return {"message": "Choose Games on a device, then Get this game.", "open": ["games-devices", "devices"]}
        if sid == "run-device-checks":
            r = await self.device_checks_run_all()
            counts: dict[str, int] = {}
            for result in r.get("results", []):
                counts[result["status"]] = counts.get(result["status"], 0) + 1
            parts = [f"{counts[k]} {k}" for k in ("pass", "warn", "fail", "skip") if counts.get(k)]
            return {"message": f"Device checks: {', '.join(parts) or 'none ran'}."}
        if sid == "check-updates":
            r = await self.check_for_updates(True)
            latest = r.get("latest") or {}
            return {
                "message": f"Update available: v{latest.get('version')}."
                if r.get("updateAvailable")
                else "Haversack is up to date."
            }
        if sid == "send-current":
            running = sorted(self._games_running - {0})
            games = (await self.discover_games())["games"]
            current = next((g for g in games if running and g.get("appid") == running[-1]), None)
            if current is None:
                return {"message": "No game is running."}
            peers = self._links().store.list()
            if len(peers) != 1:
                return {"message": "Choose the device on Other devices.", "open": ["games-devices", "devices"]}
            await self.replication_send(current["key"], str(peers[0]["id"]))
            return {"message": f"Sending {current['name']} to {peers[0].get('name') or 'your other device'}."}
        raise ValueError("that shortcut is not available here")

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
                "emulator-setup": self._emulator_probe,
            },
        )

    async def _emulator_probe(self) -> dict[str, Any]:
        found = await self.emulator_setup()
        if found.get("off"):
            return {"off": True}
        return {
            "setups": found["setups"],
            "emulators": [{"name": e["name"], "type": e["type"]} for e in found["emulators"]],
            "perSystem": found["perSystem"],
            "secrets": found["secrets"],
        }

    async def _remote_shortcuts_probe(self) -> dict[str, Any]:
        games = (await self.discover_games())["games"]
        copies = await asyncio.to_thread(self.remote_copies.copies, games)
        log = await asyncio.to_thread(self.remote_copies.tidy_log)
        found = remotecopies.check(copies, games, lambda key: bool(self.game_configs.get(key).get("enabled")), log)
        return {**found, "reportAt": (await asyncio.to_thread(self.remote_copies.report)).get("at")}

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
            "replication": await self._replication_redacted(),
            "navigation": self._navigation_record,
        }
        await asyncio.to_thread(atomic_write_json, os.path.join(self.paths.settings_dir, name), payload)
        where = devicechecks.tilde(os.path.join(self.paths.settings_dir, name), discovery.real_home(self.home))
        log_event(logging.INFO, "devicecheck.export", "Device check results exported", file=name)
        return {"file": name, "where": where, "summary": text}

    async def save_navigation_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """The navigation recorder's result (v0.41.1): kept to page ids, routes and counts, saved as one file."""
        clean = navigation_record(record)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = f"navigation-{stamp}.json"
        path = os.path.join(self.paths.settings_dir, name)
        await asyncio.to_thread(atomic_write_json, path, {"version": self.version, **clean})
        self._navigation_record = {"file": name, **clean}
        log_event(logging.INFO, "navigation.recorded", "Navigation recorded", **clean["summary"])
        return {"file": name, "where": devicechecks.tilde(path, discovery.real_home(self.home))}

    async def _replication_redacted(self) -> dict[str, Any] | None:
        """Offer and transfer states for the Device checks' export (v0.30.2): no titles, names or paths."""
        incoming, outgoing = self.incoming, self.outgoing
        if incoming is None or outgoing is None:
            return None
        return {
            "incoming": await asyncio.to_thread(incoming.redacted),
            "outgoing": await asyncio.to_thread(outgoing.redacted),
            "sending": [
                {"state": s.get("state"), "reason": wire_reason(s.get("reason"))} for s in self._sending.values()
            ],
            "activity": [
                {k: (wire_reason(e[k]) if k == "reason" else e[k]) for k in ("direction", "stage", "percent", "reason")}
                for e in await self.replication_activity()
            ],
            "news": [m.get("type") for _peer, m in (self._news.sent if self._news else [])],
        }

    async def export_diagnostics(self, frontend: dict[str, Any] | None = None) -> str:
        path = await asyncio.to_thread(
            diagnostics.export,
            self.paths.settings_dir,
            self.paths.runtime_dir,
            self.paths.log_dir,
            frontend,
            {"manifest": self.manifest.status()},
        )
        log_event(logging.INFO, "diagnostics.export", "Diagnostics exported", file=os.path.basename(path))
        return path
