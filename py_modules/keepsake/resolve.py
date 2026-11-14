"""Logical roots, manifest path resolution and file scanning (build prompt section 8).

A manifest path such as ``<winLocalAppData>/Goat2/Saved`` becomes a logical
root plus a relative glob (``winLocalAppData``, ``Goat2/Saved``). Cloud data
only ever holds that pair, never the device path (principle 10).

Rules:

* Unknown or unsupported placeholders skip the path; nothing is guessed.
* ``..``, ``.``, absolute paths and drive letters are rejected (threat model T3).
* Every match must stay inside its root after ``realpath``; symlinks that
  escape are skipped and reported.
* Inside a Proton prefix, names match case-insensitively, as Windows does.
"""

from __future__ import annotations

import fnmatch
import os
import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .safepath import is_within

WIN_ROOTS = (
    "winAppData",
    "winLocalAppData",
    "winLocalAppDataLow",
    "winDocuments",
    "winSavedGames",
    "winPublic",
    "winProgramData",
)
NATIVE_ROOTS = ("home", "xdgData", "xdgConfig")
ALL_ROOTS = (*WIN_ROOTS, "base", *NATIVE_ROOTS, "steamUserdata")

_STEAMUSER = ("drive_c", "users", "steamuser")
_WIN_PATHS = {
    "winAppData": (*_STEAMUSER, "AppData", "Roaming"),
    "winLocalAppData": (*_STEAMUSER, "AppData", "Local"),
    "winLocalAppDataLow": (*_STEAMUSER, "AppData", "LocalLow"),
    "winDocuments": (*_STEAMUSER, "Documents"),
    "winSavedGames": (*_STEAMUSER, "Saved Games"),
    "winPublic": ("drive_c", "users", "Public"),
    "winProgramData": ("drive_c", "ProgramData"),
}

# Leading placeholder forms, longest first. Values are the logical root.
_WIN_PREFIXES = [
    ("<home>/saved games", "winSavedGames"),
    ("<home>/appdata/locallow", "winLocalAppDataLow"),
    ("<home>/appdata/local", "winLocalAppData"),
    ("<home>/appdata/roaming", "winAppData"),
    ("<home>/my documents", "winDocuments"),
    ("<home>/documents", "winDocuments"),
    ("<winlocalappdatalow>", "winLocalAppDataLow"),
    # Manifest quirk: "<winLocalAppData>Low" means LocalLow.
    ("<winlocalappdata>low", "winLocalAppDataLow"),
    ("<winlocalappdata>", "winLocalAppData"),
    ("<winappdata>", "winAppData"),
    ("<windocuments>", "winDocuments"),
    ("<winpublic>", "winPublic"),
    ("<winprogramdata>", "winProgramData"),
]
_COMMON_PREFIXES = [
    ("<root>/userdata/<storeuserid>", "steamUserdata"),
    ("<root>/<game>", "base"),
    ("<base>", "base"),
]
_NATIVE_PREFIXES = [
    ("<xdgdata>", "xdgData"),
    ("<xdgconfig>", "xdgConfig"),
    ("<home>", "home"),
]

DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        "crashdumps",
        "crashes",
        "crashreports",
        "crash reports",
        "logs",
        "log",
        "shadercache",
        "shader_cache",
        "shadercaches",
        "dxcache",
        "glcache",
        "gpucache",
        "code cache",
        "webcache",
        "cefcache",
        "service worker",
        "temp",
        "tmp",
    }
)
DEFAULT_EXCLUDED_FILES = ("*.log", "*.dmp", "*.mdmp", "*.tmp", "*.temp", "*.etl", "*.crash")

MAX_FILES = 20000
MAX_DEPTH = 32
SIZE_WARNING_BYTES = 200 * 1024 * 1024
_GLOB_CHARS = re.compile(r"[*?\[]")


class SkipPath(Exception):
    """The manifest path cannot be resolved safely; the reason is the message."""


def platform_of(game: Mapping[str, Any]) -> str:
    return "proton" if game.get("prefix") else "native"


def logical_roots(
    game: Mapping[str, Any], home: str | None = None, env: Mapping[str, str] | None = None
) -> dict[str, str | None]:
    """Absolute folder for each logical root on this device, or None when not applicable."""
    env = os.environ if env is None else env
    roots: dict[str, str | None] = dict.fromkeys(ALL_ROOTS)
    prefix = game.get("prefix")
    if prefix:
        pfx = os.path.join(str(prefix), "pfx")
        for name, parts in _WIN_PATHS.items():
            roots[name] = os.path.join(pfx, *parts)
    else:
        real_home = os.path.realpath(home or env.get("DECKY_USER_HOME") or os.path.expanduser("~"))
        roots["home"] = real_home
        roots["xdgData"] = os.path.realpath(env.get("XDG_DATA_HOME") or os.path.join(real_home, ".local", "share"))
        roots["xdgConfig"] = os.path.realpath(env.get("XDG_CONFIG_HOME") or os.path.join(real_home, ".config"))
    base = game.get("base_dir")
    real_home_dir = os.path.realpath(home or env.get("DECKY_USER_HOME") or os.path.expanduser("~"))
    roots["base"] = str(base) if base and safe_base(str(base), game, real_home_dir) else None
    steam_root, user = game.get("steam_root"), game.get("user_id") or game.get("default_user")
    roots["steamUserdata"] = os.path.join(str(steam_root), "userdata", str(user)) if steam_root and user else None
    return roots


def safe_base(base: str, game: Mapping[str, Any], home: str) -> bool:
    """Refuse a ``base`` root that is too broad to confine writes.

    A shortcut whose ``StartDir`` or exe folder is ``/``, the home folder, a
    Steam root or the prefix's ``drive_c`` would otherwise make most of the
    disk "inside" the root (write allowlist, build prompt section 8).
    """
    real = os.path.realpath(base)
    parts = [p for p in real.replace("\\", "/").split("/") if p]
    if len(parts) < 2 or os.path.dirname(real) == real:
        return False
    protected = [home]
    if game.get("steam_root"):
        protected.append(str(game["steam_root"]))
    if game.get("prefix"):
        protected.append(os.path.join(str(game["prefix"]), "pfx", "drive_c"))
    for folder in protected:
        # Base must not be the protected folder itself or one of its ancestors.
        if is_within(real, folder):
            return False
    return True


def applies(whens: list[list[str | None]], platform: str) -> bool:
    """A path applies with no constraints, or when any constraint's OS fits.

    Store constraints are ignored: shortcuts installed from ISO have no store,
    but the same game keeps its saves in the same place (Ludusavi's README
    allows checking paths whose constraints do not fit).
    """
    if not whens:
        return True
    wanted = "windows" if platform == "proton" else "linux"
    return any(os_name in (None, wanted) for os_name, _store in whens)


def to_logical(path: str, platform: str, game_names: Iterable[str], steam_id: int | None) -> list[tuple[str, str]]:
    """Turn a manifest path into ``(root, relative glob)`` pairs. Raises :class:`SkipPath`."""
    text = path.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    lowered = text.lower()
    table = _COMMON_PREFIXES + (_WIN_PREFIXES if platform == "proton" else _NATIVE_PREFIXES)
    matched = next(
        (
            (prefix, name)
            for prefix, name in sorted(table, key=lambda item: len(item[0]), reverse=True)
            if lowered == prefix or lowered.startswith(prefix + "/")
        ),
        None,
    )
    if matched is None:
        first = text.split("/", 1)[0]
        raise SkipPath(f"unsupported root {first}" if first.startswith("<") else "absolute or unknown path")
    prefix, root = matched
    rest = text[len(prefix) + 1 :]

    if "<storeGameId>" in rest:
        if steam_id is None:
            raise SkipPath("needs a store game id")
        rest = rest.replace("<storeGameId>", str(steam_id))
    if "<storeUserId>" in rest:
        # A folder named after the store account (usually the SteamID64). Like
        # Ludusavi, match it as a wildcard, but only as a whole path segment.
        if any(seg != "<storeUserId>" and "<storeUserId>" in seg for seg in rest.split("/")):
            raise SkipPath("store user id inside a name")
        rest = "/".join("*" if seg == "<storeUserId>" else seg for seg in rest.split("/"))
    if "<osUserName>" in rest:
        if platform != "proton":
            raise SkipPath("needs the OS user name")
        rest = rest.replace("<osUserName>", "steamuser")
    names = [n for n in game_names if n] or []
    variants = [rest]
    if "<game>" in rest:
        if not names:
            raise SkipPath("needs the game folder name")
        variants = [rest.replace("<game>", name) for name in names]
    out: list[tuple[str, str]] = []
    for variant in variants:
        if re.search(r"<[^>]+>", variant):
            raise SkipPath(f"unknown placeholder {re.search(r'<[^>]+>', variant).group(0)}")  # type: ignore[union-attr]
        variant = variant.strip("/")
        for segment in variant.split("/") if variant else []:
            if segment in ("", ".", ".."):
                raise SkipPath("relative path segment")
            if ":" in segment:
                raise SkipPath("drive letter or stream")
        if (root, variant) not in out:
            out.append((root, variant))
    return out


# Scanning


@dataclass
class ScanResult:
    files: dict[str, int] = field(default_factory=dict)  # relative POSIX path to size
    escaped: list[str] = field(default_factory=list)
    truncated: bool = False


def _match_segment(names: list[str], pattern: str, insensitive: bool) -> list[str]:
    if insensitive:
        lowered = pattern.lower()
        if not _GLOB_CHARS.search(pattern):
            return [n for n in names if n.lower() == lowered]
        return [n for n in names if fnmatch.fnmatchcase(n.lower(), lowered)]
    if not _GLOB_CHARS.search(pattern):
        return [n for n in names if n == pattern]
    return [n for n in names if fnmatch.fnmatchcase(n, pattern)]


def _listdir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def expand(root: str, rel_glob: str, insensitive: bool) -> list[str]:
    """Return relative paths (files or folders) under ``root`` matching ``rel_glob``."""
    current = [""]
    segments = [s for s in rel_glob.split("/") if s] if rel_glob else []
    for segment in segments:
        nxt: list[str] = []
        if segment == "**":
            for rel in current:
                nxt.append(rel)
                base = os.path.join(root, rel)
                for folder, dirs, _files in os.walk(base):
                    depth = os.path.relpath(folder, base).count(os.sep)
                    if depth >= MAX_DEPTH:
                        dirs[:] = []
                    for d in sorted(dirs):
                        nxt.append(os.path.relpath(os.path.join(folder, d), root).replace(os.sep, "/"))
        else:
            for rel in current:
                for name in _match_segment(_listdir(os.path.join(root, rel)), segment, insensitive):
                    nxt.append(f"{rel}/{name}" if rel else name)
        current = sorted(set(nxt))
        if not current:
            break
    return current


def _excluded(rel: str, user_patterns: list[str]) -> bool:
    parts = rel.lower().split("/")
    if any(p in DEFAULT_EXCLUDED_DIRS for p in parts[:-1]):
        return True
    if any(fnmatch.fnmatchcase(parts[-1], pattern) for pattern in DEFAULT_EXCLUDED_FILES):
        return True
    lowered = rel.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern.lower()) for pattern in user_patterns)


def scan(root: str, rel_glob: str, insensitive: bool, user_exclusions: list[str], result: ScanResult) -> int:
    """Add files under the matches of ``rel_glob`` to ``result``; return how many were excluded."""
    excluded = 0
    if not os.path.isdir(root):
        return 0
    real_root = os.path.realpath(root)
    for match in expand(root, rel_glob, insensitive):
        full = os.path.join(root, match) if match else root
        if not is_within(real_root, full):
            result.escaped.append(match)
            continue
        try:
            st = os.lstat(full)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode) or (stat.S_ISLNK(st.st_mode) and os.path.isfile(full)):
            excluded += _add_file(real_root, root, match, user_exclusions, result)
            continue
        if not os.path.isdir(full):
            continue
        for folder, dirs, files in os.walk(full, followlinks=False):
            if os.path.relpath(folder, full).count(os.sep) >= MAX_DEPTH:
                dirs[:] = []
            kept_dirs = []
            for d in dirs:
                if os.path.islink(os.path.join(folder, d)):
                    rel_dir = os.path.relpath(os.path.join(folder, d), root).replace(os.sep, "/")
                    if not is_within(real_root, os.path.join(folder, d)):
                        result.escaped.append(rel_dir)
                    continue  # symlinked folders are never followed
                kept_dirs.append(d)
            dirs[:] = sorted(kept_dirs)
            for name in sorted(files):
                rel = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
                excluded += _add_file(real_root, root, rel, user_exclusions, result)
                if result.truncated:
                    return excluded
    return excluded


def _add_file(real_root: str, root: str, rel: str, user_exclusions: list[str], result: ScanResult) -> int:
    full = os.path.join(root, rel)
    if not is_within(real_root, full):
        result.escaped.append(rel)
        return 0
    if _excluded(rel, user_exclusions):
        return 1
    if rel in result.files:
        return 0
    if len(result.files) >= MAX_FILES:
        result.truncated = True
        return 0
    try:
        result.files[rel] = os.path.getsize(full)
    except OSError:
        pass
    return 0


# Preview


def preview(
    game: Mapping[str, Any],
    title: str | None,
    record: Mapping[str, Any] | None,
    config: Mapping[str, Any],
    home: str | None = None,
    sample_limit: int = 20,
) -> dict[str, Any]:
    """Resolve and scan a game's save locations without writing anything."""
    platform = platform_of(game)
    roots = logical_roots(game, home=home)
    include_config = bool(config.get("includeConfig"))
    exclusions = [str(p) for p in config.get("exclusions", [])]
    names = list((record or {}).get("i", [])) + ([title] if title else [])
    steam_id = (record or {}).get("s")

    candidates: list[tuple[str, str, str, list[list[str | None]]]] = []
    for path, tags, whens in (record or {}).get("f", []):
        candidates.append(("manifest", path, tags, whens))
    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    per_root: dict[str, ScanResult] = {}
    excluded_total = 0

    def run(source: str, label: str, tags: str, pairs: list[tuple[str, str]]) -> None:
        nonlocal excluded_total
        for root_name, rel in pairs:
            root_path = roots.get(root_name)
            if root_path is None:
                skipped.append({"path": label, "reason": f"root {root_name} not available here"})
                continue
            result = per_root.setdefault(root_name, ScanResult())
            before = set(result.files)
            insensitive = platform == "proton" and (root_name in WIN_ROOTS or _inside(root_path, game.get("prefix")))
            excluded_total += scan(root_path, rel, insensitive, exclusions, result)
            added = sorted(set(result.files) - before)
            entries.append(
                {
                    "source": source,
                    "path": label,
                    "root": root_name,
                    "pattern": rel,
                    "tags": tags,
                    "files": len(added),
                    "bytes": sum(result.files[r] for r in added),
                    "samples": added[:sample_limit],
                }
            )

    for source, path, tags, whens in candidates:
        if "s" not in tags and not (include_config and "c" in tags):
            skipped.append(
                {"path": path, "reason": "config files are off for this game" if "c" in tags else "not a save"}
            )
            continue
        if not applies(whens, platform):
            skipped.append({"path": path, "reason": "for another operating system"})
            continue
        try:
            pairs = to_logical(path, platform, names, steam_id if isinstance(steam_id, int) else None)
        except SkipPath as exc:
            skipped.append({"path": path, "reason": str(exc)})
            continue
        run(source, path, tags, pairs)

    for custom in config.get("customPaths", []):
        run("custom", f"<{custom['root']}>/{custom['rel']}", "s", [(custom["root"], custom["rel"])])

    total_files = sum(len(r.files) for r in per_root.values())
    total_bytes = sum(sum(r.files.values()) for r in per_root.values())
    warnings: list[str] = []
    if total_bytes > SIZE_WARNING_BYTES:
        warnings.append("larger than 200 MB")
    if any(r.truncated for r in per_root.values()):
        warnings.append(f"more than {MAX_FILES} files; list truncated")
    escaped = sorted({f"{name}/{e}" for name, r in per_root.items() for e in r.escaped})
    if escaped:
        warnings.append("some paths point outside their folder and were ignored")
    if record is None:
        warnings.append("no manifest match")
    return {
        "title": title,
        "platform": platform,
        "roots": roots,
        "entries": entries,
        "skipped": skipped,
        "escaped": escaped,
        "excluded": excluded_total,
        "totalFiles": total_files,
        "totalBytes": total_bytes,
        "warnings": warnings,
    }


def _inside(path: str, prefix: Any) -> bool:
    return bool(prefix) and is_within(str(prefix), path)
