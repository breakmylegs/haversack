"""Steam discovery: roots, libraries, users and non-Steam shortcuts.

Slice 1 holds only what the Diagnostics page needs. Slice 3 extends this into
full discovery (app manifests, classification, prefix mapping).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .vdf import VdfError, loads_binary, loads_text

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


def steam_roots(home: str | None = None) -> list[str]:
    """Return distinct Steam installation folders, most conventional first."""
    base = real_home(home)
    seen: set[str] = set()
    roots: list[str] = []
    for parts in STEAM_ROOT_CANDIDATES:
        candidate = os.path.realpath(os.path.join(base, *parts))
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
