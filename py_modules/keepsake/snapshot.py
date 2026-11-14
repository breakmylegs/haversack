"""Snapshots: scanning, hashing, metadata, zip packing and safe extraction.

A snapshot is a complete file list (so deletions are implicit) plus a zip
blob whose entries are ``<root>/<rel>``. Hashes decide (principle 4): the
``contentHash`` covers every file's root, path, size and SHA-256.

Metadata follows build prompt section 9, ``schemaVersion`` 1.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .resolve import ALL_ROOTS
from .safepath import PathEscapeError, ensure_within, join_within, validate_relative

SCHEMA_VERSION = 1
KINDS = ("auto-exit", "auto-recovered", "manual", "merge", "import", "provisional")
AUTOMATIC_KINDS = ("auto-exit", "auto-recovered")
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
CHUNK = 1024 * 1024
MAX_ENTRY_BYTES = 4 * 1024 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
_SNAP_ID = re.compile(r"^[0-9]{6,}-[0-9a-f]{6}-[0-9a-f]{8}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class SnapshotError(Exception):
    pass


class NewerSchemaError(SnapshotError):
    """The snapshot was written by a newer Keepsake; never write to this game (section 12)."""


@dataclass(frozen=True, order=True)
class FileEntry:
    root: str
    rel: str
    size: int
    sha256: str

    @property
    def arcname(self) -> str:
        return f"{self.root}/{self.rel}"

    def public(self) -> dict[str, Any]:
        return {"root": self.root, "rel": self.rel, "size": self.size, "sha256": self.sha256}


# Hashing


def hash_file(path: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def scan_entries(files_by_root: Mapping[str, Iterable[str]], roots: Mapping[str, str | None]) -> list[FileEntry]:
    """Hash every listed file. Every path is re-validated against its root."""
    entries: list[FileEntry] = []
    for root_name, rels in files_by_root.items():
        root_path = roots.get(root_name)
        if root_name not in ALL_ROOTS or not root_path:
            raise SnapshotError(f"unknown or unavailable root {root_name}")
        for rel in rels:
            path = join_within(root_path, rel)
            size, digest = hash_file(path)
            entries.append(FileEntry(root_name, rel, size, digest))
    return sorted(entries)


def content_hash(entries: Iterable[FileEntry]) -> str:
    """SHA-256 over the sorted file list: one ``root NUL rel NUL size NUL sha256 LF`` line per file."""
    digest = hashlib.sha256()
    for entry in sorted(entries):
        digest.update(f"{entry.root}\0{entry.rel}\0{entry.size}\0{entry.sha256}\n".encode())
    return digest.hexdigest()


def make_snap_id(device_seq: int, device_id: str, chash: str) -> str:
    short = re.sub(r"[^0-9a-f]", "", device_id.lower())[:6].ljust(6, "0")
    return f"{device_seq:06d}-{short}-{chash[:8]}"


# Metadata


def build_meta(
    *,
    game_key: str,
    entries: list[FileEntry],
    parents: list[str],
    device_id: str,
    device_name: str,
    device_seq: int,
    kind: str,
    blob_sha256: str,
    plugin_version: str,
    flags: list[str] | None = None,
    created: float | None = None,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise SnapshotError(f"unknown kind {kind}")
    chash = content_hash(entries)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "snapId": make_snap_id(device_seq, device_id, chash),
        "gameKey": game_key,
        "parents": list(parents),
        "deviceId": device_id,
        "deviceName": device_name,
        "deviceSeq": device_seq,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created if created is not None else time.time())),
        "kind": kind,
        "flags": list(flags or []),
        "contentHash": chash,
        "files": [e.public() for e in sorted(entries)],
        "blobSha256": blob_sha256,
        "pluginVersion": plugin_version,
    }


def meta_bytes(meta: Mapping[str, Any]) -> bytes:
    return json.dumps(meta, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def entries_of(meta: Mapping[str, Any]) -> list[FileEntry]:
    return sorted(FileEntry(f["root"], f["rel"], int(f["size"]), f["sha256"]) for f in meta["files"])


def validate_meta(meta: Any) -> dict[str, Any]:
    """Check structure, paths and that ``contentHash`` and ``snapId`` match the file list."""
    if not isinstance(meta, dict):
        raise SnapshotError("metadata is not an object")
    version = meta.get("schemaVersion")
    if isinstance(version, int) and version > SCHEMA_VERSION:
        raise NewerSchemaError(f"snapshot schema {version} is newer than {SCHEMA_VERSION}")
    if version != SCHEMA_VERSION:
        raise SnapshotError("missing or invalid schemaVersion")
    for key, kind in (
        ("snapId", str),
        ("gameKey", str),
        ("deviceId", str),
        ("contentHash", str),
        ("blobSha256", str),
        ("kind", str),
        ("created", str),
        ("deviceSeq", int),
    ):
        if not isinstance(meta.get(key), kind):
            raise SnapshotError(f"missing or invalid {key}")
    if not _SNAP_ID.match(meta["snapId"]) or meta["kind"] not in KINDS or not _HEX64.match(meta["blobSha256"]):
        raise SnapshotError("invalid snapId, kind or blob hash")
    if not isinstance(meta.get("parents"), list) or not all(
        isinstance(p, str) and _SNAP_ID.match(p) for p in meta["parents"]
    ):
        raise SnapshotError("invalid parents")
    files = meta.get("files")
    if not isinstance(files, list):
        raise SnapshotError("invalid files")
    seen: set[tuple[str, str]] = set()
    for item in files:
        if not isinstance(item, dict) or item.get("root") not in ALL_ROOTS:
            raise SnapshotError("file entry with unknown root")
        try:
            validate_relative(str(item.get("rel", "")))
        except PathEscapeError as exc:
            raise SnapshotError(str(exc)) from exc
        if not isinstance(item.get("size"), int) or item["size"] < 0 or not _HEX64.match(str(item.get("sha256", ""))):
            raise SnapshotError("file entry with invalid size or hash")
        # Case-insensitive: two names differing only in case collide inside a Proton prefix.
        ident = (str(item["root"]), str(item["rel"]).lower())
        if ident in seen:
            raise SnapshotError("duplicate file entry")
        seen.add(ident)
    chash = content_hash(entries_of(meta))
    if chash != meta["contentHash"] or not meta["snapId"].endswith(chash[:8]):
        raise SnapshotError("contentHash does not match the file list")
    return meta


# Packing


def pack(entries: list[FileEntry], roots: Mapping[str, str | None], dest: str) -> str:
    """Write a deterministic zip of ``entries`` to ``dest``; return its SHA-256.

    Every file is re-hashed while it is copied. A file that changed since it
    was scanned aborts the pack (fail closed).
    """
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for entry in sorted(entries):
            root_path = roots.get(entry.root)
            if not root_path:
                raise SnapshotError(f"root {entry.root} unavailable")
            source = join_within(root_path, entry.rel)
            info = zipfile.ZipInfo(entry.arcname, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            digest = hashlib.sha256()
            size = 0
            with open(source, "rb") as handle, archive.open(info, "w", force_zip64=entry.size > 2**31) as out:
                while chunk := handle.read(CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            if size != entry.size or digest.hexdigest() != entry.sha256:
                raise SnapshotError(f"{entry.arcname} changed while packing")
    return hash_file(dest)[1]


# Verification and extraction


def _check_zip(archive: zipfile.ZipFile, meta: Mapping[str, Any]) -> dict[str, FileEntry]:
    """Validate every zip entry against the metadata before anything is extracted (T4)."""
    expected = {e.arcname: e for e in entries_of(meta)}
    names: set[str] = set()
    total = 0
    for info in archive.infolist():
        name = info.filename
        if name in names:
            raise SnapshotError(f"duplicate zip entry {name}")
        names.add(name)
        if name not in expected:
            raise SnapshotError(f"unexpected zip entry {name!r}")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode) or info.is_dir():
            raise SnapshotError(f"zip entry {name} is not a regular file")
        if info.flag_bits & 0x1:
            raise SnapshotError("encrypted zip entries are not supported")
        if info.file_size != expected[name].size or info.file_size > MAX_ENTRY_BYTES:
            raise SnapshotError(f"zip entry {name} has the wrong size")
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise SnapshotError(f"zip entry {name} has a suspicious compression ratio")
        total += info.file_size
    if total > MAX_TOTAL_BYTES:
        raise SnapshotError("snapshot is too large")
    missing = set(expected) - names
    if missing:
        raise SnapshotError(f"zip is missing {len(missing)} files")
    return expected


def verify_blob(blob_path: str, meta: Mapping[str, Any]) -> None:
    """Check the blob hash, structure and every file's SHA-256."""
    if hash_file(blob_path)[1] != meta["blobSha256"]:
        raise SnapshotError("blob hash does not match the metadata")
    with zipfile.ZipFile(blob_path) as archive:
        expected = _check_zip(archive, meta)
        for name, entry in expected.items():
            digest = hashlib.sha256()
            with archive.open(name) as handle:
                while chunk := handle.read(CHUNK):
                    digest.update(chunk)
            if digest.hexdigest() != entry.sha256:
                raise SnapshotError(f"{name} does not match its hash")


def extract(
    blob_path: str,
    meta: Mapping[str, Any],
    wanted: Iterable[FileEntry],
    destination: Callable[[FileEntry], tuple[str, str]],
) -> None:
    """Extract ``wanted`` entries. ``destination(entry)`` returns ``(base folder, relative path)``.

    Each file is written beside nothing it could escape: the path is joined
    inside its base folder with traversal checks, written, hash-checked and
    fsynced.
    """
    with zipfile.ZipFile(blob_path) as archive:
        expected = _check_zip(archive, meta)
        for entry in wanted:
            if expected.get(entry.arcname) != entry:
                raise SnapshotError(f"{entry.arcname} is not in this snapshot")
            base, rel = destination(entry)
            os.makedirs(base, exist_ok=True)
            target = join_within(base, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            ensure_within(base, os.path.dirname(target))
            digest = hashlib.sha256()
            with archive.open(entry.arcname) as source, open(target, "wb") as out:
                while chunk := source.read(CHUNK):
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if digest.hexdigest() != entry.sha256:
                raise SnapshotError(f"{entry.arcname} failed its hash check")
