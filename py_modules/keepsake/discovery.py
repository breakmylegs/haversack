"""Steam discovery: roots, libraries, users, Steam apps and non-Steam shortcuts.

Read only. Nothing here writes to Steam's files (editing ``shortcuts.vdf`` is
an escalation item). Results describe this device only and never go to the
cloud as they contain absolute paths and per-device IDs (principle 10).
"""

from __future__ import annotations

import glob
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from .fsutil import atomic_write_json, read_json
from .vdf import VdfError, loads_binary, loads_text

STEAMID64_BASE = 76561197960265728

# Steam "apps" that are runtimes and tools, not games.
TOOL_APPIDS = frozenset(
    {
        228980,  # Steamworks Common Redistributables
        1070560,  # Steam Linux Runtime 1.0 (scout)
        1391110,  # Steam Linux Runtime 2.0 (soldier)
        1628350,  # Steam Linux Runtime 3.0 (sniper)
        1493710,  # Proton Experimental
        2180100,  # Proton Hotfix
        2805730,  # Proton 9.0
        3658110,  # Proton 10.0
    }
)
TOOL_NAME_PREFIXES = ("Proton", "Steam Linux Runtime", "Steamworks Common Redistributables", "SteamVR")

STEAM_ROOT_CANDIDATES = (
    (".local", "share", "Steam"),
    (".steam", "steam"),
    (".steam", "root"),
    (".var", "app", "com.valvesoftware.Steam", "data", "Steam"),
)


def real_home(home: str | None = None) -> str:
    """Resolve the home folder so ``/var/home/x`` and ``/home/x`` compare equal."""
    return os.path.realpath(home or os.environ.get("DECKY_USER_HOME") or os.path.expanduser("~"))


def unsigned_appid(appid: int) -> int:
    """Convert the signed 32-bit ``appid`` stored in ``shortcuts.vdf`` to unsigned."""
    return int(appid) & 0xFFFFFFFF


WINDOWS_HOST = "windows"  # keepsake.hosts: Steam for Windows layout (ADR-0038)
_WINDOWS_STEAM_KEYS = (
    ("HKEY_CURRENT_USER", r"Software\Valve\Steam", "SteamPath"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Valve\Steam", "InstallPath"),
)
_WINDOWS_STEAM_FALLBACKS = (("ProgramFiles(x86)", "Steam"), ("ProgramFiles", "Steam"))


def windows_steam_paths(env: Mapping[str, str] | None = None) -> list[str]:
    """Where Steam for Windows says it is (the registry), then its default folders. Read only."""
    found: list[str] = []
    try:
        import winreg  # Windows only, so imported here (ADR-0030 keeps optional modules lazy)
    except ImportError:
        winreg = None  # type: ignore[assignment]
    for hive_name, key, value in _WINDOWS_STEAM_KEYS if winreg is not None else ():
        try:
            with winreg.OpenKey(getattr(winreg, hive_name), key) as handle:
                path, _kind = winreg.QueryValueEx(handle, value)
        except OSError:
            continue
        if isinstance(path, str) and path.strip():
            found.append(path.strip())
    env = os.environ if env is None else env
    for variable, folder in _WINDOWS_STEAM_FALLBACKS:
        base = env.get(variable)
        if base:
            found.append(os.path.join(base, folder))
    return found


def steam_roots(home: str | None = None, host: str = "decky", windows_paths: list[str] | None = None) -> list[str]:
    """Return distinct Steam installation folders, most conventional first.

    On a Windows host (ADR-0038) they come from Steam for Windows' registry entry
    and its default folders; elsewhere from the home folder's usual places.
    """
    if host == WINDOWS_HOST:
        candidates = [os.path.realpath(p) for p in (windows_steam_paths() if windows_paths is None else windows_paths)]
    else:
        base = real_home(home)
        candidates = [os.path.realpath(os.path.join(base, *parts)) for parts in STEAM_ROOT_CANDIDATES]
    seen: set[str] = set()
    roots: list[str] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        if os.path.isdir(os.path.join(candidate, "steamapps")) or os.path.isdir(os.path.join(candidate, "userdata")):
            seen.add(candidate)
            roots.append(candidate)
    return roots


def library_folders(steam_root: str) -> list[str]:
    """Return library folders for a Steam root, with the root itself first."""
    libraries = [os.path.realpath(steam_root)]
    path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            data = loads_text(handle.read())
    except (OSError, VdfError):
        return libraries
    folders = data.get("libraryfolders") or data.get("LibraryFolders") or {}
    if isinstance(folders, dict):
        for key in sorted(folders, key=lambda k: (not k.isdigit(), int(k) if k.isdigit() else 0, k)):
            entry = folders[key]
            folder = entry.get("path") if isinstance(entry, dict) else entry if isinstance(entry, str) else None
            if folder:
                real = os.path.realpath(folder)
                if real not in libraries:
                    libraries.append(real)
    return libraries


def steam_user_ids(steam_root: str) -> list[str]:
    """Return Steam account IDs (id3) that have a userdata folder, newest activity first."""
    userdata = os.path.join(steam_root, "userdata")
    try:
        names = [n for n in os.listdir(userdata) if n.isdigit() and n != "0"]
    except OSError:
        return []

    def mtime(name: str) -> float:
        try:
            return os.path.getmtime(os.path.join(userdata, name, "config"))
        except OSError:
            return 0.0

    return sorted(names, key=mtime, reverse=True)


@dataclass(frozen=True)
class Shortcut:
    appid_signed: int
    appid_unsigned: int
    name: str
    exe: str
    start_dir: str
    last_play_time: int
    launch_options: str = ""
    icon: str = ""


ARTWORK_SUFFIXES = ("", "p", "_hero", "_logo", "_icon")
ARTWORK_EXTENSIONS = (".png", ".jpg", ".jpeg")


def compat_tool_mapping(steam_root: str) -> dict[int, str]:
    """App ID to compatibility tool name from Steam's ``config/config.vdf`` (read-only, v2 slice 3 amendment).

    The mapping lives under ``InstallConfigStore/Software/Valve/Steam/CompatToolMapping``
    (assumption A126). Returns an empty mapping when the file or the key is missing.
    """
    path = os.path.join(steam_root, "config", "config.vdf")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            data = loads_text(handle.read())
    except (OSError, VdfError):
        return {}
    node: Any = _lower_keys(data)
    for key in ("installconfigstore", "software", "valve", "steam", "compattoolmapping"):
        node = _lower_keys(node).get(key) if isinstance(node, dict) else None
    out: dict[int, str] = {}
    if isinstance(node, dict):
        for appid, entry in node.items():
            if (
                str(appid).isdigit()
                and isinstance(entry, dict)
                and isinstance(entry.get("name"), str)
                and entry["name"]
            ):
                out[int(appid)] = entry["name"]
    return out


def artwork_files(steam_root: str, user_id3: str | None, appid: int) -> list[str]:
    """Custom artwork file names for an app in ``userdata/<id3>/config/grid`` (read-only)."""
    if not user_id3:
        return []
    grid = os.path.join(steam_root, "userdata", user_id3, "config", "grid")
    found = []
    for suffix in ARTWORK_SUFFIXES:
        for extension in ARTWORK_EXTENSIONS:
            name = f"{appid}{suffix}{extension}"
            if os.path.isfile(os.path.join(grid, name)):
                found.append(name)
    return found


def _lower_keys(entry: dict[str, Any]) -> dict[str, Any]:
    return {k.lower(): v for k, v in entry.items()}


def read_shortcuts(path: str) -> list[Shortcut]:
    """Read ``shortcuts.vdf``. Raises ``OSError`` or :class:`VdfError` on failure."""
    with open(path, "rb") as handle:
        data = loads_binary(handle.read())
    root = _lower_keys(data).get("shortcuts", {})
    out: list[Shortcut] = []
    if not isinstance(root, dict):
        return out
    for entry in root.values():
        if not isinstance(entry, dict):
            continue
        e = _lower_keys(entry)
        appid = e.get("appid")
        if not isinstance(appid, int):
            continue
        out.append(
            Shortcut(
                appid_signed=appid if appid < 2**31 else appid - 2**32,
                appid_unsigned=unsigned_appid(appid),
                name=str(e.get("appname", "")),
                exe=str(e.get("exe", "")),
                start_dir=str(e.get("startdir", "")),
                last_play_time=int(e.get("lastplaytime", 0) or 0),
                launch_options=str(e.get("launchoptions", "")),
                icon=str(e.get("icon", "")),
            )
        )
    return out


def find_compatdata(appid_unsigned: int, libraries: list[str]) -> str | None:
    """Return the first ``compatdata/<id>`` folder that has a ``pfx``, base library first."""
    for library in libraries:
        candidate = os.path.join(library, "steamapps", "compatdata", str(appid_unsigned))
        if os.path.isdir(os.path.join(candidate, "pfx")):
            return candidate
    return None


# Users


def default_user_id(steam_root: str, user_ids: list[str] | None = None) -> str | None:
    """Return the id3 of the most recent Steam user.

    Uses ``config/loginusers.vdf`` (``MostRecent``, then ``Timestamp``) and
    falls back to the most recently changed ``userdata`` folder. Account and
    persona names in that file are never read into results.
    """
    candidates = user_ids if user_ids is not None else steam_user_ids(steam_root)
    try:
        with open(os.path.join(steam_root, "config", "loginusers.vdf"), encoding="utf-8", errors="replace") as handle:
            users = loads_text(handle.read()).get("users", {})
    except (OSError, VdfError):
        users = {}
    ranked: list[tuple[int, int, str]] = []
    if isinstance(users, dict):
        for steamid64, info in users.items():
            if not steamid64.isdigit() or not isinstance(info, dict):
                continue
            id3 = str(int(steamid64) - STEAMID64_BASE)
            if id3 not in candidates:
                continue
            most_recent = 1 if str(info.get("MostRecent", info.get("mostrecent", "0"))) == "1" else 0
            try:
                timestamp = int(info.get("Timestamp", info.get("timestamp", 0)) or 0)
            except ValueError:
                timestamp = 0
            ranked.append((most_recent, timestamp, id3))
    if ranked:
        return max(ranked)[2]
    return candidates[0] if candidates else None


# Steam apps


@dataclass(frozen=True)
class SteamApp:
    appid: int
    name: str
    installdir: str
    library: str
    last_played: int


def is_tool(appid: int, name: str) -> bool:
    return appid in TOOL_APPIDS or name.startswith(TOOL_NAME_PREFIXES)


def read_app_manifests(library: str) -> list[SteamApp]:
    """Read ``appmanifest_*.acf`` in one library. Bad files are skipped."""
    out: list[SteamApp] = []
    for path in sorted(glob.glob(os.path.join(library, "steamapps", "appmanifest_*.acf"))):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                state = loads_text(handle.read())
        except (OSError, VdfError):
            continue
        app = state.get("AppState") or state.get("appstate")
        if not isinstance(app, dict):
            continue
        a = _lower_keys(app)
        try:
            appid = int(a.get("appid", ""))
        except ValueError:
            continue
        try:
            last_played = int(a.get("lastplayed", 0) or 0)
        except ValueError:
            last_played = 0
        out.append(
            SteamApp(
                appid=appid,
                name=str(a.get("name", "")),
                installdir=str(a.get("installdir", "")),
                library=library,
                last_played=last_played,
            )
        )
    return out


# Games


@dataclass
class GameEntry:
    """One game on this device. ``key`` is stable on this device only."""

    key: str
    kind: str  # "steam" or "shortcut"
    appid: int
    name: str
    user_id: str | None
    is_default_user: bool
    prefix: str | None
    prefix_library_index: int | None
    base_dir: str | None
    exe_inside_prefix: bool
    last_played: int
    notes: list[str] = field(default_factory=list)
    steam_root: str | None = None
    default_user: str | None = None
    exe_name: str | None = None  # lower-case file name only, for cross-device matching
    # v2 slice 3 amendment, exposed through Core for Replication and Installer. Device-local only (principle 10).
    exe: str | None = None
    start_dir: str | None = None
    launch_options: str = ""
    compat_tool: str | None = None
    artwork: list[str] = field(default_factory=list)
    icon: str = ""
    # "windows" for a native Windows game on a Windows host (resolve.platform_of uses it, ADR-0038).
    os: str = "linux"

    def public(self) -> dict[str, Any]:
        return asdict(self)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def _library_index(prefix: str | None, libraries: list[str]) -> int | None:
    if prefix is None:
        return None
    library = os.path.dirname(os.path.dirname(os.path.dirname(prefix)))
    return libraries.index(library) if library in libraries else None


def shortcut_base_dir(shortcut: Shortcut) -> str | None:
    """The shortcut's ``base`` root: its ``StartDir``, else the exe's folder."""
    start = _unquote(shortcut.start_dir)
    if start:
        return os.path.realpath(start)
    exe = _unquote(shortcut.exe)
    return os.path.realpath(os.path.dirname(exe)) if exe else None


def discover(home: str | None = None, host: str = "decky", windows_paths: list[str] | None = None) -> dict[str, Any]:
    """Scan every Steam root on this device and return games and facts.

    Shortcuts of every Steam user are included; the most recent user is
    marked as default and listed first. On a Windows host games run natively:
    there are no Proton prefixes, and every game is marked ``os: windows``.
    """
    games: list[GameEntry] = []
    roots_info: list[dict[str, Any]] = []
    seen_steam: set[int] = set()
    windows = host == WINDOWS_HOST
    for root in steam_roots(home, host, windows_paths):
        libraries = library_folders(root)
        compat = compat_tool_mapping(root)
        users = steam_user_ids(root)
        default = default_user_id(root, users)
        ordered_users = ([default] if default else []) + [u for u in users if u != default]
        roots_info.append({"path": root, "libraries": libraries, "users": len(users), "defaultUser": default})

        for user in ordered_users:
            path = os.path.join(root, "userdata", user, "config", "shortcuts.vdf")
            if not os.path.exists(path):
                continue
            try:
                shortcuts = read_shortcuts(path)
            except (OSError, VdfError):
                games.append(_broken_shortcuts_entry(user, user == default))
                continue
            for sc in shortcuts:
                prefix = None if windows else find_compatdata(sc.appid_unsigned, libraries)
                exe = _unquote(sc.exe)
                notes = [] if prefix or windows else ["no-prefix"]
                games.append(
                    GameEntry(
                        key=f"shortcut:{user}:{sc.appid_unsigned}",
                        kind="shortcut",
                        appid=sc.appid_unsigned,
                        name=sc.name,
                        user_id=user,
                        is_default_user=user == default,
                        prefix=prefix,
                        prefix_library_index=_library_index(prefix, libraries),
                        base_dir=shortcut_base_dir(sc),
                        exe_inside_prefix=bool(prefix and exe and os.path.realpath(exe).startswith(prefix + os.sep)),
                        last_played=sc.last_play_time,
                        notes=notes,
                        steam_root=root,
                        default_user=default,
                        exe_name=exe.replace("\\", "/").rsplit("/", 1)[-1].lower() or None if exe else None,
                        exe=exe or None,
                        start_dir=_unquote(sc.start_dir) or None,
                        launch_options=sc.launch_options,
                        compat_tool=compat.get(sc.appid_unsigned),
                        artwork=artwork_files(root, user, sc.appid_unsigned),
                        icon=_unquote(sc.icon),
                        os="windows" if windows else "linux",
                    )
                )

        for library in libraries:
            for app in read_app_manifests(library):
                if app.appid in seen_steam or is_tool(app.appid, app.name):
                    continue
                seen_steam.add(app.appid)
                prefix = None if windows else find_compatdata(app.appid, libraries)
                install = os.path.join(library, "steamapps", "common", app.installdir) if app.installdir else None
                games.append(
                    GameEntry(
                        key=f"steam:{app.appid}",
                        kind="steam",
                        appid=app.appid,
                        name=app.name,
                        user_id=None,
                        is_default_user=True,
                        prefix=prefix,
                        prefix_library_index=_library_index(prefix, libraries),
                        base_dir=install,
                        exe_inside_prefix=False,
                        last_played=app.last_played,
                        notes=[] if install and os.path.isdir(install) else ["install-folder-missing"],
                        steam_root=root,
                        default_user=default,
                        compat_tool=compat.get(app.appid),
                        os="windows" if windows else "linux",
                    )
                )
    return {"roots": roots_info, "games": [g.public() for g in games]}


def _broken_shortcuts_entry(user: str, is_default: bool) -> GameEntry:
    return GameEntry(
        key=f"shortcut-error:{user}",
        kind="shortcut",
        appid=0,
        name="shortcuts.vdf could not be read",
        user_id=user,
        is_default_user=is_default,
        prefix=None,
        prefix_library_index=None,
        base_dir=None,
        exe_inside_prefix=False,
        last_played=0,
        notes=["shortcuts-unreadable"],
    )


# Runtime cross-check (build prompt section 8)


def cross_check(expected_prefix: str | None, observed_paths: list[str]) -> dict[str, Any]:
    """Compare the discovered prefix with ``STEAM_COMPAT_DATA_PATH`` of running processes.

    ``match`` only when every observed path resolves to the expected prefix.
    Any disagreement is a ``mismatch``, which blocks sync for the game.
    """
    observed = sorted({os.path.realpath(p.rstrip("/")) for p in observed_paths if p})
    if not observed:
        return {"status": "unknown", "observed": []}
    if expected_prefix is None:
        return {"status": "mismatch", "observed": observed, "reason": "no-discovered-prefix"}
    expected = os.path.realpath(expected_prefix)
    if observed == [expected]:
        return {"status": "match", "observed": observed}
    return {"status": "mismatch", "observed": observed, "reason": "different-prefix"}


MISMATCH_FILE = "prefix-mismatches.json"


UNREADABLE = "_unreadable"


def load_mismatches(runtime_dir: str) -> dict[str, Any]:
    """Return recorded mismatches. An unreadable file returns ``{UNREADABLE: True}``."""
    try:
        data = read_json(os.path.join(runtime_dir, MISMATCH_FILE), default={})
    except (OSError, ValueError):
        return {UNREADABLE: True}
    return data if isinstance(data, dict) else {UNREADABLE: True}


def sync_blocked(runtime_dir: str, key: str) -> bool:
    """Fail closed (principle 5): a recorded mismatch or unreadable state blocks sync."""
    mismatches = load_mismatches(runtime_dir)
    return UNREADABLE in mismatches or key in mismatches


def record_cross_check(runtime_dir: str, key: str, result: dict[str, Any], expected: str | None) -> dict[str, Any]:
    """Remember mismatches until a later check matches. ``unknown`` changes nothing.

    An unreadable file is left untouched, so it keeps blocking every game
    rather than being replaced by a file that forgets earlier mismatches.
    """
    mismatches = load_mismatches(runtime_dir)
    if UNREADABLE in mismatches:
        return mismatches
    if result["status"] == "mismatch":
        mismatches[key] = {"expected": expected, "observed": result["observed"], "reason": result.get("reason")}
    elif result["status"] == "match":
        mismatches.pop(key, None)
    atomic_write_json(os.path.join(runtime_dir, MISMATCH_FILE), mismatches)
    return mismatches
