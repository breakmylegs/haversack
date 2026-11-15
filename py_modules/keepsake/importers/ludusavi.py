"""Read Ludusavi backups and turn them into Keepsake ``import`` snapshots (slice 10, ADR-0021).

Ludusavi (MIT) keeps one folder per game with a ``mapping.yaml`` that lists
full backups and their differential children. Each backup stores files under
their absolute path: in a folder (simple format) or a zip, below a drive
folder such as ``drive-0`` (the empty drive on Linux) or ``drive-C``.

Absolute paths are mapped to Keepsake's logical roots by their shape: the
``.../pfx/drive_c/users/steamuser/AppData/...`` pattern inside any Proton
prefix (so the old compatdata ID does not matter), Windows ``C:/Users/<name>``
paths, Linux home folders and Steam ``userdata``. Paths that fit no root are
reported and left out, never guessed.

Only the files named in ``mapping.yaml`` are read; every file is checked
against its recorded size and hash, and the whole backup is refused on any
mismatch (fail closed). Nothing is ever written to the Ludusavi folder.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import shutil
import zipfile
from typing import Any

from ..safepath import is_within, join_within, validate_relative
from ..yamlsubset import YamlSubsetError, iter_entries

MAPPING_FILE = "mapping.yaml"
MAX_GAMES = 2000
MAX_FILES = 20000
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
_DRIVE = re.compile(r"^([A-Za-z]:)/(.*)$")
_WIN_USER_ROOTS = (
    (("appdata", "roaming"), "winAppData"),
    (("appdata", "locallow"), "winLocalAppDataLow"),
    (("appdata", "local"), "winLocalAppData"),
    (("saved games",), "winSavedGames"),
    (("documents",), "winDocuments"),
    (("my documents",), "winDocuments"),
)


class LudusaviError(ValueError):
    pass


# Reading mapping.yaml


def load_mapping(game_folder: str) -> dict[str, Any]:
    path = os.path.join(game_folder, MAPPING_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            entries = dict(iter_entries(handle))
    except (OSError, UnicodeDecodeError) as exc:
        raise LudusaviError(f"cannot read {MAPPING_FILE}: {exc}") from exc
    for value in entries.values():
        if isinstance(value, YamlSubsetError):
            raise LudusaviError(f"{MAPPING_FILE} uses YAML Keepsake cannot read: {value}")
    if not isinstance(entries.get("name"), str) or not isinstance(entries.get("backups"), list):
        raise LudusaviError(f"{MAPPING_FILE} has no game name or backups")
    drives = entries.get("drives") if isinstance(entries.get("drives"), dict) else {}
    return {"name": entries["name"], "drives": drives, "backups": entries["backups"]}


def _backup_name(item: Any) -> str:
    name = item.get("name") if isinstance(item, dict) else None
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or name == "..":
        raise LudusaviError("a backup in mapping.yaml has an invalid name")
    return name


def _when(item: dict[str, Any]) -> float | None:
    text = item.get("when")
    if not isinstance(text, str):
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def list_backups(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Every full backup and differential child, oldest first. IDs are ``full`` or ``full/child``."""
    out = []
    for full in mapping["backups"]:
        if not isinstance(full, dict):
            continue
        full_name = _backup_name(full)
        out.append(
            {
                "id": full_name,
                "kind": "full",
                "when": full.get("when"),
                "created": _when(full),
                "files": len(_file_map(full)),
            }
        )
        for child in full.get("children") or []:
            if isinstance(child, dict):
                out.append(
                    {
                        "id": f"{full_name}/{_backup_name(child)}",
                        "kind": "differential",
                        "when": child.get("when"),
                        "created": _when(child),
                        "files": len(resolve_files(mapping, f"{full_name}/{_backup_name(child)}")),
                    }
                )
    return sorted(out, key=lambda b: (b["created"] or 0, b["id"]))


def scan(root: str) -> list[dict[str, Any]]:
    """Games in a Ludusavi backup folder. Unreadable games are listed with their error."""
    out: list[dict[str, Any]] = []
    try:
        names = sorted(os.listdir(root))
    except OSError as exc:
        raise LudusaviError(f"cannot open the backup folder: {exc}") from exc
    for name in names[:MAX_GAMES]:
        folder = os.path.join(root, name)
        if os.path.islink(folder) or not os.path.isfile(os.path.join(folder, MAPPING_FILE)):
            continue
        try:
            mapping = load_mapping(folder)
            out.append({"folder": name, "name": mapping["name"], "backups": list_backups(mapping), "error": None})
        except LudusaviError as exc:
            out.append({"folder": name, "name": name, "backups": [], "error": str(exc)})
    return out


def _file_map(backup: dict[str, Any]) -> dict[str, Any]:
    files = backup.get("files")
    return files if isinstance(files, dict) else {}


def resolve_files(mapping: dict[str, Any], backup_id: str) -> dict[str, tuple[str, int, str]]:
    """Original path to ``(backup name, size, hash)`` for a full backup or a differential child."""
    full_name, _, child_name = backup_id.partition("/")
    full = next((b for b in mapping["backups"] if isinstance(b, dict) and b.get("name") == full_name), None)
    if full is None:
        raise LudusaviError(f"no backup named {full_name}")
    files: dict[str, tuple[str, int, str]] = {}
    for path, entry in _file_map(full).items():
        if isinstance(entry, dict):
            files[str(path)] = (full_name, int(entry.get("size", -1)), str(entry.get("hash", "")))
    if child_name:
        child = next(
            (c for c in full.get("children") or [] if isinstance(c, dict) and c.get("name") == child_name), None
        )
        if child is None:
            raise LudusaviError(f"no backup named {backup_id}")
        for path, entry in _file_map(child).items():
            if entry is None:
                files.pop(str(path), None)  # removed or ignored in this differential
            elif isinstance(entry, dict):
                files[str(path)] = (child_name, int(entry.get("size", -1)), str(entry.get("hash", "")))
    return files


# Mapping absolute paths to logical roots


def _clean(parts: list[str]) -> str | None:
    if not parts:
        return None
    try:
        return validate_relative("/".join(parts))
    except ValueError:
        return None


def _windows_root(rest: list[str]) -> tuple[str, str] | None:
    lower = [p.lower() for p in rest]
    if len(rest) >= 3 and lower[0] == "users":
        sub, sub_lower = rest[2:], lower[2:]
        if lower[1] == "public":
            rel = _clean(sub)
            return ("winPublic", rel) if rel else None
        for suffix, root in _WIN_USER_ROOTS:
            if tuple(sub_lower[: len(suffix)]) == suffix:
                rel = _clean(sub[len(suffix) :])
                return (root, rel) if rel else None
        return None
    if lower and lower[0] == "programdata":
        rel = _clean(rest[1:])
        return ("winProgramData", rel) if rel else None
    return None


def to_logical(original: str) -> tuple[str, str] | None:
    """``(root, rel)`` for an absolute path from a Ludusavi backup, or None when it fits no root."""
    path = original.replace("\\", "/")
    parts = [p for p in path.split("/") if p]
    lower = [p.lower() for p in parts]
    for i in range(len(lower) - 1):
        if lower[i] == "pfx" and lower[i + 1] == "drive_c":
            return _windows_root(parts[i + 2 :])  # any Proton prefix, whatever its compatdata ID
    for i in range(len(lower) - 2):
        if lower[i] == "userdata" and i > 0 and lower[i - 1] in ("steam", ".steam") and parts[i + 1].isdigit():
            rel = _clean(parts[i + 2 :])
            return ("steamUserdata", rel) if rel else None
    if parts and _DRIVE.match(parts[0] + "/"):
        return _windows_root(parts[1:])
    home: list[str] | None = None
    if len(lower) > 2 and lower[0] == "home":
        home = parts[2:]
    elif len(lower) > 3 and lower[:2] == ["var", "home"]:
        home = parts[3:]
    if home is None:
        return None
    if [h.lower() for h in home[:2]] == [".local", "share"]:
        rel = _clean(home[2:])
        return ("xdgData", rel) if rel else None
    if home and home[0] == ".config":
        rel = _clean(home[1:])
        return ("xdgConfig", rel) if rel else None
    rel = _clean(home)
    return ("home", rel) if rel else None


# Extracting a backup into staging


def stored_location(drives: dict[str, Any], original: str) -> str:
    """Where Ludusavi stored ``original``: ``<drive folder>/<path without drive>``."""
    path = original.replace("\\", "/")
    match = _DRIVE.match(path)
    drive, plain = (match.group(1), match.group(2)) if match else ("", path.lstrip("/"))
    folder = next((str(k) for k, v in drives.items() if v == drive), None)
    if folder is None:
        folder = "drive-0" if drive == "" else "drive-" + drive.rstrip(":")
    return f"{folder}/{plain}"


def _hash_ok(data_path: str, expected_size: int, expected: str) -> bool:
    if os.path.getsize(data_path) != expected_size:
        return False
    algorithm = {40: "sha1", 64: "sha256"}.get(len(expected))
    if algorithm is None:
        return True  # no usable hash recorded: the size check stands
    digest = hashlib.new(algorithm)
    with open(data_path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == expected.lower()


def extract(game_folder: str, backup_id: str, staging: str) -> dict[str, Any]:
    """Copy one backup's files into ``staging/<root>/<rel>``, verified.

    Returns ``files`` (root to relative paths), ``roots`` (root to its staging
    folder), ``skipped`` (paths that fit no logical root, with the reason),
    ``created`` (the backup's own time) and ``name`` (the game's Ludusavi name).
    """
    mapping = load_mapping(game_folder)
    plan = resolve_files(mapping, backup_id)
    if len(plan) > MAX_FILES:
        raise LudusaviError("too many files in this backup")
    when = next((b["created"] for b in list_backups(mapping) if b["id"] == backup_id), None)
    files: dict[str, list[str]] = {}
    roots: dict[str, str | None] = {}
    skipped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    total = 0
    zips: dict[str, zipfile.ZipFile] = {}
    try:
        for original in sorted(plan):
            backup, size, expected = plan[original]
            mapped = to_logical(original)
            if mapped is None:
                skipped.append({"path": original, "reason": "not in a save folder Keepsake knows"})
                continue
            if mapped in seen:
                skipped.append({"path": original, "reason": "another file maps to the same place"})
                continue
            seen.add(mapped)
            total += max(size, 0)
            if total > MAX_TOTAL_BYTES:
                raise LudusaviError("this backup is too large to import")
            root, rel = mapped
            root_dir = os.path.join(staging, root)
            dest = join_within(root_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            location = stored_location(mapping["drives"], original)
            if backup.endswith(".zip"):
                archive = zips.get(backup)
                if archive is None:
                    archive = zips[backup] = zipfile.ZipFile(os.path.join(game_folder, backup))
                try:
                    info = archive.getinfo(location)
                except KeyError as exc:
                    raise LudusaviError(f"{backup} is missing {original}") from exc
                if info.file_size != size:
                    raise LudusaviError(f"{original} has the wrong size in {backup}")
                with archive.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
            else:
                backup_dir = os.path.join(game_folder, backup)
                src_path = os.path.join(backup_dir, *location.split("/"))
                if os.path.islink(src_path) or not is_within(game_folder, src_path):
                    raise LudusaviError(f"{original} is not a plain file inside the backup")
                if not os.path.isfile(src_path):
                    raise LudusaviError(f"{backup} is missing {original}")
                shutil.copyfile(src_path, dest)
            if not _hash_ok(dest, size, expected):
                raise LudusaviError(f"{original} does not match the size or hash Ludusavi recorded")
            files.setdefault(root, []).append(rel)
            roots[root] = root_dir
    finally:
        for archive in zips.values():
            archive.close()
    return {"files": files, "roots": roots, "skipped": skipped, "created": when, "name": mapping["name"]}
