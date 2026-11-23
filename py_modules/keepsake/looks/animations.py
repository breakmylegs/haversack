"""Boot and suspend animations (R29 stage 1, ADR-0091).

Steam plays its boot and suspend videos from ``<steam>/config/uioverrides/movies`` when a file of the
right name is there: ``deck_startup.webm`` at boot, ``steam_os_suspend.webm`` when the device sleeps and
``steam_os_suspend_from_throbber.webm`` when it sleeps from the loading screen. Haversack copies a WebM
the user picks into that place, and nothing else:

- **Only those three names** in that one folder (the write allowlist addendum in ADR-0091).
- **Never someone else's file lost.** If a video is already there that Haversack did not put there, it
  is kept once in Haversack's own folder before anything replaces it, and **Use Steam's own** puts it
  back.
- **Never another tool's file replaced or removed.** Haversack records the SHA-256 of what it wrote.
  Reset only removes a file that still matches, so a video another tool changed afterwards stays.
  While Animation Changer is installed, Haversack shows the videos and changes nothing.
- **Only real WebM files** (the EBML header), at most 100 MB, copied to a temporary name beside the
  target, checked by hash and then renamed into place, so Steam never sees half a file.

The videos are Steam's interface, not a game's files, so they can change while a game runs; Steam
uses them the next time the device boots or sleeps.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from typing import Any

VIDEOS = {
    "boot": "deck_startup.webm",
    "suspend": "steam_os_suspend.webm",
    "throbber": "steam_os_suspend_from_throbber.webm",
}
EBML = b"\x1a\x45\xdf\xa3"  # every WebM (Matroska) file starts with this
MAX_BYTES = 100 * 1024 * 1024
STATE = "animations.json"


class AnimationError(Exception):
    pass


def overrides(steam_root: str) -> str:
    return os.path.join(steam_root, "config", "uioverrides", "movies")


def _digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def is_webm(path: str) -> bool:
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_BYTES:
            return False
        with open(path, "rb") as handle:
            return handle.read(4) == EBML
    except OSError:
        return False


class Animations:
    """The three videos, the user's WebM files to choose from, and what Haversack put in place."""

    def __init__(self, steam_root: str, data_dir: str, sources: list[tuple[str, str]], clock: Any = time.time) -> None:
        self.folder = overrides(steam_root)
        self.data = os.path.join(data_dir, "looks")
        self.sources = sources  # (label, folder): where the user's WebM files are looked for
        self.clock = clock

    # what Haversack wrote, so it only ever removes its own files
    def _state(self) -> dict[str, Any]:
        try:
            with open(os.path.join(self.data, STATE), encoding="utf-8") as handle:
                found = json.load(handle)
            return found if isinstance(found, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, state: dict[str, Any]) -> None:
        os.makedirs(self.data, exist_ok=True)
        tmp = os.path.join(self.data, STATE + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=1)
        os.replace(tmp, os.path.join(self.data, STATE))

    def choices(self) -> list[dict[str, Any]]:
        """WebM files in the source folders (and one level of sub-folders, as Animation Changer keeps sets)."""
        found: list[dict[str, Any]] = []
        for index, (label, folder) in enumerate(self.sources):
            if not os.path.isdir(folder):
                continue
            for root, dirs, names in os.walk(folder):
                depth = os.path.relpath(root, folder).count(os.sep) + (os.path.relpath(root, folder) != ".")
                if depth >= 1:
                    dirs[:] = []
                dirs.sort()
                for name in sorted(names):
                    path = os.path.join(root, name)
                    if name.lower().endswith(".webm") and is_webm(path):
                        rel = os.path.relpath(path, folder).replace(os.sep, "/")
                        found.append(
                            {"id": f"{index}:{rel}", "name": rel[:-5], "from": label, "bytes": os.path.getsize(path)}
                        )
        return found[:500]

    def _source(self, choice_id: str) -> str:
        """The file behind a choice id, refusing anything outside the source folders."""
        index_text, _, rel = choice_id.partition(":")
        if not index_text.isdigit() or int(index_text) >= len(self.sources) or not rel:
            raise AnimationError("that video is not one of the choices")
        folder = os.path.realpath(self.sources[int(index_text)][1])
        path = os.path.realpath(os.path.join(folder, *rel.split("/")))
        if os.path.commonpath([folder, path]) != folder or not is_webm(path):
            raise AnimationError("that video is not one of the choices")
        return path

    def status(self, blocked_by: str | None = None) -> dict[str, Any]:
        state = self._state()
        videos = {}
        for kind, name in VIDEOS.items():
            path = os.path.join(self.folder, name)
            mine = state.get(kind)
            if not os.path.lexists(path):
                who = "steam"  # Steam's own video
            elif mine and os.path.isfile(path) and _digest(path) == mine.get("sha256"):
                who = "haversack"
            else:
                who = "other"  # put there by hand or by another tool
            videos[kind] = {
                "who": who,
                "name": mine.get("name") if who == "haversack" and mine else None,
                "keptOriginal": os.path.isfile(os.path.join(self.data, "originals", name)),
            }
        return {"videos": videos, "blockedBy": blocked_by, "steamFound": os.path.isdir(os.path.dirname(self.folder))}

    def apply(self, kind: str, choice_id: str) -> dict[str, Any]:
        if kind not in VIDEOS:
            raise AnimationError("unknown video")
        source = self._source(choice_id)
        if not os.path.isdir(os.path.dirname(os.path.dirname(self.folder))):
            raise AnimationError("Steam's config folder was not found")
        os.makedirs(self.folder, exist_ok=True)
        target = os.path.join(self.folder, VIDEOS[kind])
        state = self._state()
        mine = state.get(kind)
        if os.path.lexists(target) and not (mine and os.path.isfile(target) and _digest(target) == mine.get("sha256")):
            kept = os.path.join(self.data, "originals", VIDEOS[kind])
            if not os.path.exists(kept):  # the first one found is the one Use Steam's own brings back
                if os.path.islink(target) or not os.path.isfile(target):
                    raise AnimationError("the video there is not a plain file, so Haversack leaves it alone")
                os.makedirs(os.path.dirname(kept), exist_ok=True)
                shutil.copy2(target, kept + ".tmp")
                os.replace(kept + ".tmp", kept)
        digest = _digest(source)
        tmp = target + ".haversack-tmp"
        shutil.copyfile(source, tmp)
        if _digest(tmp) != digest:
            os.remove(tmp)
            raise AnimationError("the copy did not match the original; nothing was changed")
        os.replace(tmp, target)
        name = choice_id.partition(":")[2].rsplit("/", 1)[-1][:-5]
        state[kind] = {"sha256": digest, "name": name, "at": int(self.clock())}
        self._save(state)
        return self.status()

    def reset(self, kind: str) -> dict[str, Any]:
        """Put Steam's own video (or the one that was there first) back, if the file is still Haversack's."""
        if kind not in VIDEOS:
            raise AnimationError("unknown video")
        target = os.path.join(self.folder, VIDEOS[kind])
        state = self._state()
        mine = state.get(kind)
        if os.path.lexists(target):
            if not (mine and os.path.isfile(target) and _digest(target) == mine.get("sha256")):
                raise AnimationError("this video was changed outside Haversack, so it is left as it is")
            os.remove(target)
        kept = os.path.join(self.data, "originals", VIDEOS[kind])
        if os.path.isfile(kept):
            shutil.copy2(kept, target + ".haversack-tmp")
            os.replace(target + ".haversack-tmp", target)
            os.remove(kept)
        state.pop(kind, None)
        self._save(state)
        return self.status()
