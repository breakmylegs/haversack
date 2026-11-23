"""Replication manifests: what a shared folder holds, exactly (slice 18a, ADR-0057).

A manifest lists every entry under a root with a relative POSIX path, its type, size, mode,
modification time (nanoseconds) and, for links, the link text. Files carry the SHA-256 of
each 4 MiB chunk and of the whole file. Chunks that are all zeros are marked, so they are
neither sent nor written: a sparse file stays sparse. The root hash is the SHA-256 of the
manifest's canonical JSON, so one value pins every byte of a version.

Paths never hold an absolute path, a user name or a device name (P10): only what is under
the shared root.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from typing import Any

CHUNK = 4 * 1024 * 1024
VERSION = 1
MAX_ENTRIES = 200_000
WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
WINDOWS_BAD = set('<>:"\\|?*')


class ManifestError(Exception):
    pass


def zero_hash(size: int) -> str:
    return hashlib.sha256(bytes(size)).hexdigest()


_ZERO_FULL = zero_hash(CHUNK)


def is_zero_chunk(digest: str, size: int) -> bool:
    return digest == (_ZERO_FULL if size == CHUNK else zero_hash(size))


def chunk_sizes(size: int) -> list[int]:
    full, rest = divmod(size, CHUNK)
    return [CHUNK] * full + ([rest] if rest else [])


def hash_file(path: str, read: int | None = None) -> tuple[str, list[str]]:
    """The whole-file SHA-256 and the SHA-256 of each chunk."""
    read = read or CHUNK
    whole = hashlib.sha256()
    chunks = []
    with open(path, "rb") as handle:
        while True:
            block = handle.read(read)
            if not block:
                break
            whole.update(block)
            chunks.append(hashlib.sha256(block).hexdigest())
    return whole.hexdigest(), chunks


def check_path(rel: str, windows: bool = False) -> str:
    """A safe relative POSIX path, or ManifestError. On a Windows target, names Windows forbids too."""
    if not rel or rel.startswith("/") or "\\" in rel or "\x00" in rel or (len(rel) > 1 and rel[1] == ":"):
        raise ManifestError(f"not a relative path: {rel[:80]}")
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ManifestError(f"not a clean path: {rel[:80]}")
    if windows:
        for part in parts:
            stem = part.split(".")[0].lower()
            if stem in WINDOWS_RESERVED or set(part) & WINDOWS_BAD or part.endswith((" ", ".")):
                raise ManifestError(f"Windows cannot store this name: {rel[:80]}")
    return rel


def build(root: str, exclude: Callable[[str], bool] = lambda _rel: False) -> dict[str, Any]:
    """Describe everything under ``root``. Links are recorded, never followed."""
    entries: list[dict[str, Any]] = []
    root = os.path.abspath(root)
    for folder, dirs, files in os.walk(root, followlinks=False):
        rel_folder = os.path.relpath(folder, root).replace(os.sep, "/")
        dirs.sort()
        for name in sorted(dirs) + sorted(files):
            full = os.path.join(folder, name)
            rel = name if rel_folder == "." else f"{rel_folder}/{name}"
            if exclude(rel):
                if name in dirs:
                    dirs.remove(name)
                continue
            info = os.lstat(full)
            entry: dict[str, Any] = {
                "path": check_path(rel),
                "mode": stat.S_IMODE(info.st_mode),
                "mtime": info.st_mtime_ns,
            }
            if stat.S_ISLNK(info.st_mode):
                entry |= {"type": "link", "target": os.readlink(full)}
                if name in dirs:
                    dirs.remove(name)  # never walk into a linked folder
            elif stat.S_ISDIR(info.st_mode):
                entry["type"] = "dir"
            elif stat.S_ISREG(info.st_mode):
                whole, chunks = hash_file(full)
                entry |= {"type": "file", "size": info.st_size, "sha256": whole, "chunks": chunks}
            else:
                continue  # sockets, devices and pipes are not copied
            entries.append(entry)
            if len(entries) > MAX_ENTRIES:
                raise ManifestError(f"more than {MAX_ENTRIES} entries")
    manifest = {"version": VERSION, "chunk": CHUNK, "entries": sorted(entries, key=lambda e: e["path"])}
    manifest["root"] = root_hash(manifest)
    return manifest


def canonical(manifest: dict[str, Any]) -> bytes:
    body = {k: v for k, v in manifest.items() if k != "root"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def root_hash(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(manifest)).hexdigest()


def validate(manifest: Any, expected_root: str, windows: bool = False) -> dict[str, Any]:
    """A received manifest, checked against the root hash the user agreed to receive."""
    if not isinstance(manifest, dict) or manifest.get("version") != VERSION or manifest.get("chunk") != CHUNK:
        raise ManifestError("the manifest is not one this Haversack understands; update both devices")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ManifestError("the manifest is not valid")
    if root_hash(manifest) != expected_root:
        raise ManifestError("the manifest does not match what was offered")
    seen: set[str] = set()
    folded: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") not in ("file", "dir", "link"):
            raise ManifestError("the manifest is not valid")
        path = check_path(str(entry.get("path", "")), windows)
        if path in seen or path.lower() in folded:
            raise ManifestError(f"two entries differ only by case: {path[:80]}")
        seen.add(path)
        folded.add(path.lower())
        if not isinstance(entry.get("mode"), int) or not isinstance(entry.get("mtime"), int):
            raise ManifestError("the manifest is not valid")
        if entry["type"] == "file":
            size, chunks = entry.get("size"), entry.get("chunks")
            if not isinstance(size, int) or size < 0 or not isinstance(chunks, list):
                raise ManifestError("the manifest is not valid")
            if len(chunks) != len(chunk_sizes(size)):
                raise ManifestError(f"chunk list does not match the size of {path[:80]}")
        elif entry["type"] == "link":
            target = entry.get("target")
            if not isinstance(target, str) or not target or "\x00" in target:
                raise ManifestError("the manifest is not valid")
            if target.startswith("/") or ".." in _resolved_parts(path, target):
                raise ManifestError(f"a link points outside the folder: {path[:80]}")
    for entry in entries:  # every parent folder must be a folder in the manifest, not a link
        parent = entry["path"].rpartition("/")[0]
        if parent and parent not in seen:
            raise ManifestError(f"a parent folder is missing: {entry['path'][:80]}")
    links = {e["path"] for e in entries if e["type"] == "link"}
    for entry in entries:
        parts = entry["path"].split("/")
        if any("/".join(parts[:i]) in links for i in range(1, len(parts))):
            raise ManifestError(f"an entry sits under a link: {entry['path'][:80]}")
    return manifest


def _resolved_parts(path: str, target: str) -> list[str]:
    """Where a relative link lands, as parts from the root; '..' left over means outside."""
    out: list[str] = path.split("/")[:-1]
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not out:
                return [".."]
            out.pop()
        else:
            out.append(part)
    return out


def total_bytes(manifest: dict[str, Any]) -> int:
    return sum(int(e["size"]) for e in manifest["entries"] if e["type"] == "file")
