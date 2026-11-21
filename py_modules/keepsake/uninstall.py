"""Uninstall a non-Steam game from this device: its Proton prefix and install folder (ADR-0065).

Only folders that pass every guard here are deleted:
- the prefix only as ``<library>/steamapps/compatdata/<appid>`` of a known library, for the
  game's own app ID;
- the install folder (the shortcut's start folder, else its exe's folder) only when it lies
  strictly inside the home folder, a Steam library or a removable drive, and deleting it
  removes no protected folder (a home folder, a library or its steamapps folders, Keepsake's
  own folders, a well-known user folder) and nothing another game uses;
- never a link, never a mount point, never a missing or unreadable folder.

Each guard is checked when the plan is made and again just before deleting. Deletion walks the
tree bottom up without following links, can be cancelled between files, and reports progress.
Steam games are never deleted here: Steam's own uninstall does that (ADR-0065).
"""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .safepath import is_within

# Folders in the home folder that are never deleted, nor anything that contains them.
HOME_PROTECTED = (
    "Desktop",
    "Documents",
    "Downloads",
    "Music",
    "Pictures",
    "Videos",
    "Games",
    ".local",
    ".local/share",
    ".config",
    ".cache",
    ".steam",
    ".var",
    "homebrew",
    "Applications",
)
STEAMAPPS_PROTECTED = ("steamapps", "steamapps/common", "steamapps/compatdata", "steamapps/shadercache")
REMOVABLE_ROOTS = ("/run/media", "/media")


class UninstallError(ValueError):
    pass


@dataclass
class Places:
    """What the guards need to know about this device."""

    home: str
    libraries: list[str]
    steam_roots: list[str] = field(default_factory=list)
    extra_protected: list[str] = field(default_factory=list)  # Keepsake's folders, the library root setting
    removable: list[str] = field(default_factory=list)  # mount points of SD cards and drives
    is_mount: Callable[[str], bool] = os.path.ismount
    is_link: Callable[[str], bool] = os.path.islink

    def allowed_roots(self) -> list[str]:
        return [self.home, *self.libraries, *self.removable]

    def protected(self) -> list[str]:
        home = [self.home, *(os.path.join(self.home, *p.split("/")) for p in HOME_PROTECTED)]
        libraries = [os.path.join(library, *p.split("/")) for library in self.libraries for p in STEAMAPPS_PROTECTED]
        return [*home, *libraries, *self.steam_roots, *self.extra_protected, *self.removable, *REMOVABLE_ROOTS, "/"]


def prefix_problem(prefix: str | None, appid: int, places: Places) -> str | None:
    """Why the game's prefix must not be deleted, or None when it may."""
    if not prefix:
        return "there is no prefix"
    expected = [os.path.join(lib, "steamapps", "compatdata", str(int(appid))) for lib in places.libraries]
    if not any(os.path.normcase(os.path.abspath(prefix)) == os.path.normcase(e) for e in expected):
        return "it is not this game's compatdata folder in a Steam library"
    if places.is_link(prefix):
        return "it is a link"
    if places.is_mount(prefix):
        return "it is a mount point"
    if not os.path.isdir(prefix):
        return "it is not there"
    return None


def folder_problem(folder: str | None, places: Places, others: Iterable[str]) -> str | None:
    """Why an install folder must not be deleted, or None when it may.

    ``others`` are every folder and file another game on this device uses: other shortcuts'
    start folders, exes and prefixes, and Steam games' install folders.
    """
    if not folder:
        return "the shortcut names no folder"
    if not os.path.isabs(folder):
        return "it is not a full path"
    if places.is_link(folder):
        return "it is a link"
    real = os.path.realpath(folder)
    if not os.path.isdir(real):
        return "it is not there"
    if places.is_mount(real):
        return "it is a mount point"
    if not any(is_within(root, real) for root in places.allowed_roots()):
        return "it is not inside your home folder, a Steam library or a removable drive"
    # A root itself is never deleted: home and drives are protected below, and a library holds steamapps.
    for kept in places.protected():
        if is_within(real, kept):
            return f"deleting it would delete {kept}"
    for other in others:
        if other and (is_within(real, other) or is_within(other, real)):
            return "another game uses it or a folder around it"
    return None


def size_of(path: str, limit: int = 2_000_000) -> int:
    """Bytes in a tree, not following links (links count as their own size)."""
    total = 0
    count = 0
    for top, dirs, files in os.walk(path, followlinks=False):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(top, d))]:
            try:
                total += os.lstat(os.path.join(top, name)).st_size
            except OSError:
                continue
            count += 1
            if count > limit:
                return total
    return total


def free_space(path: str) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def plan(
    game: dict[str, Any],
    places: Places,
    others: Iterable[str],
    sizes: Callable[[str], int] = size_of,
    free: Callable[[str], int] = free_space,
) -> dict[str, Any]:
    """What uninstalling a non-Steam game would delete, with sizes, free space after, and what is kept."""
    if game.get("kind") != "shortcut":
        raise UninstallError("only non-Steam games are uninstalled here; Steam uninstalls its own games")
    others = list(others)
    appid = int(game["appid"])
    folders: list[dict[str, Any]] = []
    kept: list[dict[str, str]] = []
    prefix = game.get("prefix")
    problem = prefix_problem(prefix, appid, places)
    if problem is None and prefix:
        folders.append({"path": os.path.realpath(prefix), "kind": "prefix"})
    elif prefix:
        kept.append({"path": prefix, "reason": problem or ""})
    install = game.get("base_dir")
    if install and not (prefix and folders and is_within(prefix, install)):
        problem = folder_problem(install, places, others)
        if problem is None:
            folders.append({"path": os.path.realpath(install), "kind": "install"})
        elif problem != "it is not there":
            kept.append({"path": install, "reason": problem})
    by_device: dict[int, list[int]] = {}
    for item in folders:
        item["size"] = sizes(item["path"])
        try:
            device = os.stat(item["path"]).st_dev
        except OSError:
            device = -1
        by_device.setdefault(device, [free(item["path"]), 0])[1] += item["size"]
        item["freeAfter"] = by_device[device]
    for item in folders:
        before, freed = item.pop("freeAfter")
        item["freeAfter"] = before + freed
    return {"appid": appid, "name": game.get("name", ""), "folders": folders, "kept": kept}


def recheck(item: dict[str, Any], appid: int, places: Places, others: Iterable[str]) -> str | None:
    """The guards again, just before deleting (the folder may have changed since the plan)."""
    if item["kind"] == "prefix":
        return prefix_problem(item["path"], appid, places)
    return folder_problem(item["path"], places, others)


class Cancelled(Exception):
    pass


def delete_tree(
    path: str,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int], None] = lambda done: None,
) -> int:
    """Delete a folder bottom up without following links. Returns bytes removed; stops on cancel."""
    done = 0
    for top, dirs, files in os.walk(path, topdown=False, followlinks=False):
        for name in files + dirs:
            if cancelled():
                raise Cancelled(f"stopped after {done} bytes")
            full = os.path.join(top, name)
            info = os.lstat(full)
            if stat.S_ISDIR(info.st_mode):
                os.rmdir(full)  # a real folder: already emptied, as the walk is bottom up
            else:
                os.unlink(full)  # a file or a link: the link itself, never what it points at
                done += info.st_size
                progress(done)
    os.rmdir(path)
    return done


RUNNING = ("starting", "backing-up", "removing-shortcut", "deleting", "cleaning")
