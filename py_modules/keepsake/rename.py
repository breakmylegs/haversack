"""Keepsake becomes Haversack: moving the settings and data across (R27, ADR-0089).

Decky gives each plugin ``<homebrew>/settings/<folder>``, ``<homebrew>/data/<folder>`` and
``<homebrew>/logs/<folder>``, named after the plugin's folder. Haversack takes over Keepsake's:

- **Held while Keepsake is installed.** Haversack starts nothing (no sync, no lifecycle, no
  listener) while the old Keepsake plugin is still installed, so the two never sync at once. Its
  quick menu shows one card: remove the old plugin, after the user confirms.
- **Copied only once Keepsake is gone,** so nothing changes under the copy. Nothing in Haversack's
  folders is overwritten (a file already there stays), file modes are kept (sign-in tokens stay
  owner-only), and every copied file is checked by hash against the original. The copy needs room
  for itself: if there is not enough free space, nothing is copied and the user is told.
- **Recorded only after every file checks out** (``moved-from-keepsake.json`` in Haversack's
  settings), with a note left beside Keepsake's settings (``moved-to-haversack.json``), so the move
  is not repeated. A failed copy is not recorded and is tried again at the next start.
- **Moved again after the way back.** If any of Keepsake's files changed after the move was recorded
  (the user went back to Keepsake, then forward again), Haversack's own folders are renamed aside
  (``Haversack.before-<time>``, never deleted) and Keepsake's newer data is moved in whole.

The originals are never changed or removed: reinstalling an old Keepsake finds everything as it was.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from typing import Any

OLD, NEW = "Keepsake", "Haversack"
OLD_HELPER_FOLDER = "keepsake-helper"
OLD_HELPER = "Keepsake Helper"
KINDS = ("settings", "data")
MARKER = "moved-from-keepsake.json"
NOTE = "moved-to-haversack.json"
SPARE = 64 * 1024 * 1024  # left free after the copy, so the device never runs out


class MoveError(Exception):
    pass


def homebrew(settings_dir: str) -> str:
    """``<homebrew>`` from this plugin's settings folder (``<homebrew>/settings/<folder>``)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(settings_dir)))


def old_installed(home: str) -> bool:
    """True while the old Keepsake plugin is still installed."""
    return os.path.isfile(os.path.join(home, "plugins", OLD, "plugin.json"))


def old_helper_installed(home: str) -> bool:
    return os.path.isfile(os.path.join(home, "plugins", OLD_HELPER_FOLDER, "plugin.json"))


def _newest_old_change(home: str) -> float:
    """The newest modification time in Keepsake's folders, leaving out the note the move adds."""
    newest = 0.0
    for kind in KINDS:
        for folder, _dirs, names in os.walk(os.path.join(home, kind, OLD), followlinks=False):
            for name in names:
                path = os.path.join(folder, name)
                if name != NOTE and not os.path.islink(path):
                    newest = max(newest, os.path.getmtime(path))
    return newest


def returned(home: str) -> bool:
    """True when Keepsake was used again after the move (the way back, then forward again)."""
    marker = os.path.join(home, "settings", NEW, MARKER)
    return os.path.exists(marker) and _newest_old_change(home) > os.path.getmtime(marker) + 1


def needed(home: str) -> bool:
    """True when Keepsake's folders exist and the move has not been recorded, or Keepsake was used since."""
    if os.path.exists(os.path.join(home, "settings", NEW, MARKER)):
        return returned(home)
    return any(os.path.isdir(os.path.join(home, kind, OLD)) for kind in KINDS)


def _set_aside(home: str, stamp: str) -> list[str]:
    """Rename Haversack's folders out of the way (never deleted), so Keepsake's newer data moves in whole."""
    moved = []
    for kind in KINDS:
        current = os.path.join(home, kind, NEW)
        if os.path.isdir(current):
            aside = os.path.join(home, kind, f"{NEW}.before-{stamp}")
            os.rename(current, aside)
            moved.append(os.path.relpath(aside, home))
    return moved


def _digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _pending(source: str, target: str | None) -> int:
    """Bytes still to copy from ``source`` into ``target`` (files not already there; all of them for None)."""
    total = 0
    for folder, _dirs, names in os.walk(source, followlinks=False):
        dest_folder = os.path.join(target, os.path.relpath(folder, source)) if target else None
        for name in names:
            src = os.path.join(folder, name)
            if (
                name == NOTE
                or os.path.islink(src)
                or (dest_folder and os.path.lexists(os.path.join(dest_folder, name)))
            ):
                continue
            total += os.path.getsize(src)
    return total


def _copy_tree(source: str, target: str) -> tuple[int, int, list[str]]:
    """Copy files missing in ``target``, keeping modes; returns (files, bytes, kept-as-they-were)."""
    files = size = 0
    kept: list[str] = []
    for folder, dirs, names in os.walk(source, followlinks=False):
        rel_folder = os.path.relpath(folder, source)
        dest_folder = os.path.normpath(os.path.join(target, rel_folder))
        os.makedirs(dest_folder, exist_ok=True)
        shutil.copymode(folder, dest_folder)
        dirs.sort()
        for name in sorted(names):
            src, dest = os.path.join(folder, name), os.path.join(dest_folder, name)
            if os.path.islink(src) or name == NOTE:
                continue  # links are not followed or copied (Keepsake's folders hold none), nor the move's note
            rel = os.path.normpath(os.path.join(rel_folder, name))
            if os.path.lexists(dest):
                kept.append(rel)
                continue
            shutil.copy2(src, dest)
            if _digest(src) != _digest(dest):
                raise MoveError(f"{rel} did not copy correctly")
            files += 1
            size += os.path.getsize(dest)
    return files, size, kept


def move(home: str, clock: Any = time.time, free: Any = None) -> dict[str, Any]:
    """Copy Keepsake's settings and data into Haversack's folders, check them, and record the move."""
    if old_installed(home):
        raise MoveError("the old Keepsake plugin is still installed")
    sources = [(kind, os.path.join(home, kind, OLD)) for kind in KINDS]
    sources = [(kind, path) for kind, path in sources if os.path.isdir(path)]
    again = returned(home)  # Haversack's own folders are set aside, so everything is copied
    need = sum(_pending(path, None if again else os.path.join(home, kind, NEW)) for kind, path in sources)
    room = (free or (lambda p: shutil.disk_usage(p).free))(home)
    if need + SPARE > room:
        raise MoveError(f"needs {need + SPARE} bytes free to copy, {room} are free")
    report: dict[str, Any] = {"files": 0, "bytes": 0, "kept": [], "setAside": []}
    if again:
        report["setAside"] = _set_aside(home, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(clock())))
    for kind, source in sources:
        files, size, kept = _copy_tree(source, os.path.join(home, kind, NEW))
        report["files"] += files
        report["bytes"] += size
        report["kept"] += [f"{kind}/{k}" for k in kept]
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))
    record = {"from": OLD, "at": stamp, "files": report["files"], "bytes": report["bytes"]}
    os.makedirs(os.path.join(home, "settings", NEW), exist_ok=True)
    with open(os.path.join(home, "settings", NEW, MARKER), "w", encoding="utf-8") as handle:
        json.dump({**record, "kept": report["kept"][:200]}, handle, indent=1)
    note = os.path.join(home, "settings", OLD, NOTE)
    if os.path.isdir(os.path.dirname(note)):
        with open(note, "w", encoding="utf-8") as handle:
            json.dump({"to": NEW, "at": stamp}, handle)
    return report


class Gate:
    """Whether Haversack may start: never while Keepsake is installed, and only after the move."""

    def __init__(self, settings_dir: str, mover: Any = move) -> None:
        self.home = homebrew(settings_dir)
        self.error = ""
        self._move = mover

    def ready(self) -> bool:
        if old_installed(self.home):
            return False
        if needed(self.home):
            try:
                self._move(self.home)
            except (MoveError, OSError) as exc:
                self.error = str(exc)  # fail closed: nothing starts, the copy is tried again
                return False
        self.error = ""
        return True

    def status(self, started: bool) -> dict[str, Any]:
        return {**state(self.home), "started": started, "error": self.error}


def state(home: str) -> dict[str, Any]:
    """For the screen: whether the move happened, and whether the old plugins are still installed."""
    marker = os.path.join(home, "settings", NEW, MARKER)
    moved = None
    if os.path.exists(marker):
        try:
            with open(marker, encoding="utf-8") as handle:
                moved = json.load(handle)
        except (OSError, ValueError):
            moved = {"from": OLD}
    held = old_installed(home)
    return {"moved": moved, "oldInstalled": held, "oldHelper": old_helper_installed(home), "hold": held}
