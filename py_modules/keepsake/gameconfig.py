"""Per-game settings on this device: match override, aliases, config files, custom paths, exclusions.

Stored in ``games.json`` in the settings folder, keyed by the device-local
game key from discovery. Slice 7 publishes these as write-once config
revisions in the cloud, keyed by ``gameKey``, so they reach other devices
(build prompt section 9).
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any

from .fsutil import atomic_write_json, read_json
from .resolve import ALL_ROOTS
from .safepath import PathEscapeError, is_within

GAMES_FILE = "games.json"
MAX_ALIASES = 10
MAX_CUSTOM_PATHS = 20
MAX_EXCLUSIONS = 50
MAX_TEXT = 200
_GLOB_SEGMENT = re.compile(r"^[^/\\\x00:]+$")
_GAME_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")

DEFAULT: dict[str, Any] = {
    "matchTitle": None,
    "aliases": [],
    "includeConfig": False,
    "customPaths": [],
    "exclusions": [],
    "enabled": False,
    "launchGate": "freeze",
    "gameKey": None,
    "gameKeySource": None,
}


class GameConfigError(ValueError):
    pass


def validate_rel_glob(rel: str) -> str:
    """A relative POSIX path that may contain glob characters, never escaping its root."""
    rel = rel.replace("\\", "/").strip().strip("/")
    if not rel or len(rel) > MAX_TEXT:
        raise GameConfigError("path is empty or too long")
    for segment in rel.split("/"):
        if segment in ("", ".", "..") or not _GLOB_SEGMENT.match(segment):
            raise GameConfigError(f"invalid path segment: {segment!r}")
    return rel


def _text_list(value: Any, limit: int, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise GameConfigError(f"{label} must be a list of at most {limit} items")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > MAX_TEXT or "\x00" in item:
            raise GameConfigError(f"invalid {label} entry")
        if item.strip() not in out:
            out.append(item.strip())
    return out


def validate(config: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULT)
    unknown = set(config) - set(DEFAULT)
    if unknown:
        raise GameConfigError(f"unknown game settings: {sorted(unknown)}")
    title = config.get("matchTitle")
    if title is not None and (not isinstance(title, str) or not title.strip() or len(title) > MAX_TEXT):
        raise GameConfigError("invalid match title")
    out["matchTitle"] = title.strip() if isinstance(title, str) else None
    out["aliases"] = _text_list(config.get("aliases", []), MAX_ALIASES, "aliases")
    if not isinstance(config.get("includeConfig", False), bool):
        raise GameConfigError("includeConfig must be true or false")
    out["includeConfig"] = config.get("includeConfig", False)
    paths = config.get("customPaths", [])
    if not isinstance(paths, list) or len(paths) > MAX_CUSTOM_PATHS:
        raise GameConfigError(f"at most {MAX_CUSTOM_PATHS} custom paths")
    clean_paths: list[dict[str, str]] = []
    for item in paths:
        if not isinstance(item, dict) or item.get("root") not in ALL_ROOTS or not isinstance(item.get("rel"), str):
            raise GameConfigError("custom paths need a known root and a relative path")
        entry = {"root": str(item["root"]), "rel": validate_rel_glob(item["rel"])}
        if entry not in clean_paths:
            clean_paths.append(entry)
    out["customPaths"] = clean_paths
    exclusions = _text_list(config.get("exclusions", []), MAX_EXCLUSIONS, "exclusions")
    for pattern in exclusions:
        if pattern.startswith("/") or ".." in pattern.split("/"):
            raise GameConfigError("exclusions are relative to the save folder")
    out["exclusions"] = exclusions
    if not isinstance(config.get("enabled", False), bool):
        raise GameConfigError("enabled must be true or false")
    out["enabled"] = config.get("enabled", False)
    gate = config.get("launchGate", "freeze")
    if gate not in ("freeze", "strict", "off"):
        raise GameConfigError("launch gate must be freeze, strict or off")
    out["launchGate"] = gate
    key = config.get("gameKey")
    if key is not None and (not isinstance(key, str) or not _GAME_KEY.match(key)):
        raise GameConfigError("a game key is lower-case letters, digits and hyphens")
    out["gameKey"] = key
    source = config.get("gameKeySource")
    if source not in (None, "user", "auto"):
        raise GameConfigError("invalid game key source")
    out["gameKeySource"] = source if key else None
    return out


def custom_path_from_absolute(path: str, roots: dict[str, str | None]) -> dict[str, str]:
    """Express a folder picked in the file picker as ``{root, rel}``.

    The most specific root containing the folder wins. Folders outside every
    root of the game are refused (write allowlist, build prompt section 8).
    """
    real = os.path.realpath(path)
    best: tuple[int, str, str] | None = None
    for name, root in roots.items():
        if not root or not os.path.isdir(root):
            continue
        real_root = os.path.realpath(root)
        if is_within(real_root, real) and real != real_root:
            rel = os.path.relpath(real, real_root).replace(os.sep, "/")
            if best is None or len(real_root) > best[0]:
                best = (len(real_root), name, rel)
    if best is None:
        raise PathEscapeError("that folder is not inside any of this game's save roots")
    return {"root": best[1], "rel": validate_rel_glob(best[2])}


class GameConfigStore:
    def __init__(self, settings_dir: str) -> None:
        self._path = os.path.join(settings_dir, GAMES_FILE)
        self._lock = threading.Lock()

    def _all(self) -> dict[str, Any]:
        try:
            data = read_json(self._path, default={})
        except (OSError, ValueError) as exc:
            raise GameConfigError("games.json is unreadable") from exc
        return data if isinstance(data, dict) else {}

    def get(self, key: str) -> dict[str, Any]:
        with self._lock:
            stored = self._all().get(key)
        if not isinstance(stored, dict):
            return dict(DEFAULT)
        try:
            return validate(stored)
        except GameConfigError:
            return dict(DEFAULT)

    def any_enabled(self) -> bool:
        with self._lock:
            data = self._all()
        return any(isinstance(v, dict) and v.get("enabled") is True for v in data.values())

    def update(self, key: str, changes: dict[str, Any]) -> dict[str, Any]:
        if not key or len(key) > MAX_TEXT:
            raise GameConfigError("invalid game key")
        with self._lock:
            data = self._all()
            stored = data.get(key)
            current: dict[str, Any] = stored if isinstance(stored, dict) else {}
            merged = validate({**DEFAULT, **current, **changes})
            data[key] = merged
            atomic_write_json(self._path, data)
            return merged
