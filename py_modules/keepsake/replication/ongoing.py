"""Keeping a game in step between devices after the first copy (slice 20a, ADR-0060).

Each game sent or received is linked on both devices by its offer ID. A link records where the
game is on this device, a policy (off, manual or auto), and the base: each share's root hash at
the last sync. Saves and settings are never part of it: the scan leaves out every file Saves
manages and every config file (P14, and the screens differ), and an update keeps this device's
own copies of them.

A scan hashes the game again. A root that differs from the base means the game changed here.
An update from the other device names the base it started from; if this device changed too,
both sides changed and the user chooses. Keepsake never picks a side by itself (P1).
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from ..fsutil import atomic_write_json, read_json
from . import manifest as mf
from . import sendgame

POLICIES = ("off", "manual", "auto")
STATES = ("in-sync", "changed-here", "update-available", "both-changed", "updating")
LINK_ID = re.compile(r"^[0-9a-f]{16}$")
GAME_SCOPES = ("install", "prefix")
MAX_LINKS = 64


class LinkError(Exception):
    pass


def keep_relative(root: str, files: Iterable[str]) -> list[str]:
    """The absolute paths under ``root``, as the relative paths a manifest uses."""
    real = os.path.realpath(root)
    out = set()
    for path in files:
        full = os.path.realpath(path)
        if full != real and full.startswith(real.rstrip(os.sep) + os.sep):
            out.add(os.path.relpath(full, real).replace(os.sep, "/"))
    return sorted(out)


def scan(scopes: dict[str, str], keep: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """Manifests of a linked game, without its saves and settings. Slow for a big game: a worker thread."""
    manifests = {}
    for scope, root in scopes.items():
        base_exclude = sendgame.exclude_for(scope)
        kept = set(keep.get(scope, []))
        lowered = {k.lower() for k in kept}

        def exclude(rel: str, base_exclude: Callable[[str], bool] = base_exclude, lowered: set[str] = lowered) -> bool:
            return base_exclude(rel) or rel.lower() in lowered

        if os.path.isdir(root):
            manifests[scope] = mf.build(root, exclude)
    return manifests


def state_after(local_changed: bool, update_from_other: bool) -> str:
    if local_changed and update_from_other:
        return "both-changed"
    if update_from_other:
        return "update-available"
    if local_changed:
        return "changed-here"
    return "in-sync"


class GameLinks:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            data = read_json(self.path, default={})
        links = data.get("links") if isinstance(data, dict) else None
        return links if isinstance(links, dict) else {}

    def _save(self, links: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            atomic_write_json(self.path, {"version": 1, "links": links})

    def add(
        self, link_id: str, title: str, peer: str, appid: int | None, scopes: dict[str, str], base: dict[str, str]
    ) -> None:
        if not LINK_ID.match(link_id):
            raise LinkError("that link is not valid")
        links = self._load()
        if link_id not in links and len(links) >= MAX_LINKS:
            raise LinkError(f"at most {MAX_LINKS} games can be kept in step")
        links[link_id] = {
            "title": title,
            "peer": peer,
            "appid": appid,
            "scopes": {k: v for k, v in scopes.items() if k in GAME_SCOPES},
            "base": {k: v for k, v in base.items() if k in GAME_SCOPES},
            "policy": "manual",
            "state": "in-sync",
            "checked": time.time(),
        }
        self._save(links)

    def get(self, link_id: str) -> dict[str, Any] | None:
        return self._load().get(link_id)

    def for_appid(self, appid: int) -> tuple[str, dict[str, Any]] | None:
        for link_id, link in self._load().items():
            if link.get("appid") == appid:
                return link_id, link
        return None

    def list(self) -> list[dict[str, Any]]:
        return [{"id": k, **v} for k, v in sorted(self._load().items(), key=lambda kv: kv[1].get("title") or "")]

    def update(self, link_id: str, **changes: Any) -> dict[str, Any]:
        links = self._load()
        link: dict[str, Any] | None = links.get(link_id)
        if link is None:
            raise LinkError("that game is no longer linked")
        if "policy" in changes and changes["policy"] not in POLICIES:
            raise LinkError("the policy is off, manual or auto")
        link.update(changes)
        self._save(links)
        return link

    def remove(self, link_id: str) -> None:
        links = self._load()
        if links.pop(link_id, None) is not None:
            self._save(links)

    def changed(self, link_id: str, roots: dict[str, str]) -> bool:
        """Whether a scan's roots differ from the base. A link without a base takes these as its base."""
        link = self.get(link_id)
        if link is None:
            raise LinkError("that game is no longer linked")
        if not link.get("base"):
            self.update(link_id, base=roots, checked=time.time())
            return False
        return any(link["base"].get(scope) != root for scope, root in roots.items())
