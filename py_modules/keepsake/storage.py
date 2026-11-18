"""Storage: per-game disk use, clearing the shader cache, and "reset prefix, keep saves" (ADR-0052, R5).

Every action here follows an explicit user choice with a confirmation, and refuses while the
game runs (P6).

- **Disk use** walks the install folder, the Proton prefix, the shader cache and the saves,
  never following symlinks, and stops at a time limit rather than hang on a huge library.
- **Clear shader cache** removes ``steamapps/shadercache/<appid>`` and nothing else. Steam
  rebuilds it the next time the game runs.
- **Reset prefix, keep saves**, for a game in a Steam ``compatdata`` prefix:
  1. a copy of the game's save files is packed and verified (P3);
  2. ``compatdata/<appid>`` is renamed to ``compatdata/<appid>.keepsake-reset-<token>`` (one
     rename, on the same disk; nothing is deleted);
  3. the user starts the game once (Proton builds a fresh prefix) and quits;
  4. on that exit the saves go back into the fresh prefix, with the usual pre-restore snapshot;
  5. the old prefix stays until the user deletes it, so the reset can be undone.
  A game installed inside its prefix is refused: resetting would move the game itself away.
"""

from __future__ import annotations

import os
import re
import shutil
import time
import uuid
from collections.abc import Mapping
from typing import Any

from .fsutil import atomic_write_json, read_json
from .resolve import safe_base

RESETS_FILE = "prefix-resets.json"
RESET_SUFFIX = ".keepsake-reset-"
SIZE_SECONDS = 20.0  # per game, so one enormous install never freezes the page
_APPID = re.compile(r"^\d{1,10}$")


class StorageError(Exception):
    pass


def folder_size(path: str | None, deadline: float | None = None) -> dict[str, Any]:
    """Bytes and files under ``path``; ``partial`` when the time ran out. Symlinks are never followed."""
    total, files, partial = 0, 0, False
    if not path or not os.path.isdir(path):
        return {"bytes": 0, "files": 0, "partial": False, "present": False}
    stack = [path]
    while stack:
        if deadline is not None and time.monotonic() > deadline:
            partial = True
            break
        folder = stack.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return {"bytes": total, "files": files, "partial": partial, "present": True}


def shader_cache_dir(game: Mapping[str, Any]) -> str | None:
    """``<steam root>/steamapps/shadercache/<appid>`` for a Steam game or shortcut, when it exists."""
    root, appid = game.get("steam_root"), str(game.get("appid") or "")
    if not root or not _APPID.match(appid) or appid == "0":
        return None
    path = os.path.join(str(root), "steamapps", "shadercache", appid)
    return path if os.path.isdir(path) else None


def compat_prefix(game: Mapping[str, Any]) -> str | None:
    """A Steam ``compatdata/<appid>`` prefix that a reset may move, or None."""
    prefix = game.get("prefix")
    if not prefix or game.get("kind") not in ("steam", "shortcut"):
        return None
    prefix = str(prefix)
    parent = os.path.basename(os.path.dirname(os.path.normpath(prefix)))
    if parent != "compatdata" or not _APPID.match(os.path.basename(os.path.normpath(prefix))):
        return None
    return prefix if os.path.isdir(prefix) else None


def usage(game: Mapping[str, Any], saves_bytes: int, seconds: float = SIZE_SECONDS, home: str = "") -> dict[str, Any]:
    """Each part gets its own share of the time, so one huge folder never hides the others.

    The install folder is measured only when it is narrow enough to be the game's own
    (``resolve.safe_base``): a shortcut started from ``/`` or the home folder is not counted.
    """
    share = seconds / 3
    install = game.get("base_dir")
    if install and not safe_base(str(install), game, os.path.realpath(home or os.path.expanduser("~"))):
        install = None
    prefix = compat_prefix(game) or game.get("wine_prefix")
    parts = {
        "install": folder_size(str(install) if install else None, time.monotonic() + share),
        "prefix": folder_size(str(prefix) if prefix else None, time.monotonic() + share),
        "shaderCache": folder_size(shader_cache_dir(game), time.monotonic() + share),
    }
    if game.get("exe_inside_prefix"):
        parts["install"] = {"bytes": 0, "files": 0, "partial": False, "present": False, "insidePrefix": True}
    total = sum(p["bytes"] for p in parts.values())
    return {
        "key": game["key"],
        "name": game["name"],
        **parts,
        "saves": {"bytes": int(saves_bytes)},
        "totalBytes": total,
        "partial": any(p.get("partial") for p in parts.values()),
        "canClearShaderCache": parts["shaderCache"]["present"],
        "canResetPrefix": compat_prefix(game) is not None and not game.get("exe_inside_prefix"),
    }


def clear_shader_cache(game: Mapping[str, Any]) -> int:
    """Remove the game's own shader cache folder. Returns the bytes freed."""
    path = shader_cache_dir(game)
    if path is None:
        raise StorageError("this game has no shader cache to clear")
    freed = folder_size(path)["bytes"]
    shutil.rmtree(path)
    return int(freed)


# Prefix resets


def resets(runtime_dir: str) -> dict[str, Any]:
    try:
        data = read_json(os.path.join(runtime_dir, RESETS_FILE), default={})
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def save_resets(runtime_dir: str, data: Mapping[str, Any]) -> None:
    atomic_write_json(os.path.join(runtime_dir, RESETS_FILE), dict(data))


def move_prefix_aside(prefix: str) -> str:
    """Rename the prefix out of Steam's way (atomic, same folder). Returns where it went."""
    token = uuid.uuid4().hex[:12]
    target = os.path.normpath(prefix) + RESET_SUFFIX + token
    if os.path.lexists(target):
        raise StorageError("the reset folder already exists")
    os.rename(prefix, target)
    return target


def put_prefix_back(prefix: str, old: str) -> None:
    """Undo a reset before the saves went back: the fresh prefix (if any) is moved aside, the old one returns."""
    if not os.path.isdir(old):
        raise StorageError("the old prefix is no longer there")
    if os.path.lexists(prefix):
        os.rename(prefix, os.path.normpath(prefix) + RESET_SUFFIX + "fresh-" + uuid.uuid4().hex[:8])
    os.rename(old, prefix)


def delete_old_prefix(old: str, prefix: str) -> int:
    """Delete a prefix a reset moved aside. Only ever a folder named after the game's own prefix."""
    expected = os.path.normpath(prefix) + RESET_SUFFIX
    if not os.path.normpath(old).startswith(expected) or not os.path.isdir(old):
        raise StorageError("that is not a prefix Keepsake moved aside")
    freed = folder_size(old)["bytes"]
    shutil.rmtree(old)
    return int(freed)
