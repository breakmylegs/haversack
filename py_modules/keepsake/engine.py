"""Snapshot engine: take, publish, restore, quarantine, pin and prune, against any :class:`Store`.

Cloud layout (inside the backend's app folder, build prompt section 9):

    games/<gameKey>/snapshots/<snapId>.json
    games/<gameKey>/blobs/<snapId>.zip
    games/<gameKey>/pruned/<snapId>
    games/<gameKey>/pins/<snapId>.json      (added in slice 5, ADR-0007)

Every object is written once; the blob goes first and the metadata second,
so metadata commits a snapshot. Local state lives in the runtime folder:
quarantined snapshots, up to five pre-restore snapshots per game, and
restore journals.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from . import gates, restore, retention
from .fsutil import atomic_write_json, read_json
from .restore import Hook as RestoreHook
from .snapshot import (
    FileEntry,
    NewerSchemaError,
    SnapshotError,
    build_meta,
    content_hash,
    entries_of,
    meta_bytes,
    pack,
    scan_entries,
    validate_meta,
    verify_blob,
)
from .store import AlreadyExistsError, NotFoundError, Store

PRERESTORE_KEEP = 5
ORPHAN_GRACE_SECONDS = 24 * 3600


def snapshot_key(game_key: str, snap_id: str) -> str:
    return f"games/{game_key}/snapshots/{snap_id}.json"


def blob_key(game_key: str, snap_id: str) -> str:
    return f"games/{game_key}/blobs/{snap_id}.zip"


def pruned_key(game_key: str, snap_id: str) -> str:
    return f"games/{game_key}/pruned/{snap_id}"


def pin_key(game_key: str, snap_id: str) -> str:
    return f"games/{game_key}/pins/{snap_id}.json"


class DeviceSeq:
    """Monotonic per-device counter. Lives in the settings folder so updates never reset it."""

    def __init__(self, settings_dir: str) -> None:
        self._path = os.path.join(settings_dir, "device-seq.json")
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            data = read_json(self._path, default={"seq": 0})
            seq = int(data.get("seq", 0)) + 1
            atomic_write_json(self._path, {"seq": seq})
            return seq


class LocalSnapshots:
    """Quarantined and pre-restore snapshots kept on this device only."""

    def __init__(self, runtime_dir: str, kind: str) -> None:
        self._dir = os.path.join(runtime_dir, kind)

    def _folder(self, game_key: str) -> str:
        path = os.path.join(self._dir, game_key)
        os.makedirs(path, exist_ok=True)
        return path

    def save(
        self, game_key: str, meta: Mapping[str, Any], blob_path: str, extra: Mapping[str, Any] | None = None
    ) -> None:
        folder = self._folder(game_key)
        shutil.move(blob_path, os.path.join(folder, f"{meta['snapId']}.zip"))
        atomic_write_json(os.path.join(folder, f"{meta['snapId']}.json"), {"meta": dict(meta), **(extra or {})})

    def list(self, game_key: str) -> list[dict[str, Any]]:
        folder = os.path.join(self._dir, game_key)
        if not os.path.isdir(folder):
            return []
        out = []
        for name in sorted(os.listdir(folder)):
            if name.endswith(".json"):
                try:
                    record = read_json(os.path.join(folder, name))
                except (OSError, ValueError):
                    continue
                if isinstance(record, dict) and isinstance(record.get("meta"), dict):
                    out.append(record)
        return sorted(out, key=lambda r: (retention.created_epoch(r["meta"]), r["meta"]["snapId"]), reverse=True)

    def blob(self, game_key: str, snap_id: str) -> str:
        return os.path.join(self._folder(game_key), f"{snap_id}.zip")

    def get(self, game_key: str, snap_id: str) -> dict[str, Any]:
        record = read_json(os.path.join(self._folder(game_key), f"{snap_id}.json"))
        if not isinstance(record, dict):
            raise SnapshotError("local snapshot not found")
        return record

    def remove(self, game_key: str, snap_id: str) -> None:
        for ext in (".zip", ".json"):
            try:
                os.unlink(os.path.join(self._folder(game_key), snap_id + ext))
            except FileNotFoundError:
                pass


class SnapshotEngine:
    def __init__(
        self,
        store: Store,
        runtime_dir: str,
        settings_dir: str,
        device_id: str,
        device_name: str,
        plugin_version: str,
        settings: Callable[[], Mapping[str, Any]] = dict,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.runtime_dir = runtime_dir
        self.device_id = device_id
        self.device_name = device_name
        self.plugin_version = plugin_version
        self.settings = settings
        self.clock = clock
        self.seq = DeviceSeq(settings_dir)
        self.quarantine = LocalSnapshots(runtime_dir, "quarantine")
        self.prerestore = LocalSnapshots(runtime_dir, "prerestore")
        self._tmp = os.path.join(runtime_dir, "tmp")

    def _temp(self, suffix: str) -> str:
        os.makedirs(self._tmp, exist_ok=True)
        fd, path = tempfile.mkstemp(dir=self._tmp, suffix=suffix)
        os.close(fd)
        return path

    # Reading the cloud

    def list_metas(self, game_key: str) -> list[dict[str, Any]]:
        """Valid snapshot metadata for a game, oldest first. Raises :class:`NewerSchemaError`."""
        metas: list[dict[str, Any]] = []
        for info in self.store.list(f"games/{game_key}/snapshots/"):
            try:
                meta = validate_meta(json.loads(self.store.get(info.key).decode("utf-8")))
            except NewerSchemaError:
                raise
            except (SnapshotError, ValueError, NotFoundError):
                continue  # unreadable metadata is ignored, never trusted
            if meta["gameKey"] == game_key and info.key == snapshot_key(game_key, meta["snapId"]):
                metas.append(meta)
        return sorted(metas, key=lambda m: (retention.created_epoch(m), m["snapId"]))

    def pruned(self, game_key: str) -> set[str]:
        return {info.key.rsplit("/", 1)[1] for info in self.store.list(f"games/{game_key}/pruned/")}

    def pins(self, game_key: str) -> list[dict[str, Any]]:
        out = []
        for info in self.store.list(f"games/{game_key}/pins/"):
            try:
                pin = json.loads(self.store.get(info.key).decode("utf-8"))
            except (ValueError, NotFoundError):
                continue
            if isinstance(pin, dict) and isinstance(pin.get("snapId"), str):
                out.append(pin)
        return out

    def get_meta(self, game_key: str, snap_id: str) -> dict[str, Any]:
        return validate_meta(json.loads(self.store.get(snapshot_key(game_key, snap_id)).decode("utf-8")))

    # Taking snapshots

    def take(
        self,
        game_key: str,
        files_by_root: Mapping[str, list[str]],
        roots: Mapping[str, str | None],
        kind: str,
        base: Mapping[str, Any] | None,
        parents: list[str] | None = None,
        force: bool = False,
        gate: bool = True,
        flags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Scan, gate and publish a snapshot. Refused snapshots are quarantined locally, never uploaded.

        ``force`` publishes even when nothing changed (merge snapshots); ``gate``
        False skips the safety gates for a snapshot the user explicitly chose.
        """
        self.list_metas(game_key)  # raises NewerSchemaError before anything is written
        entries = scan_entries(files_by_root, roots)
        if not force and base is not None and content_hash(entries) == base["contentHash"]:
            return {"status": "no-change", "snapId": base["snapId"]}
        if not entries and (base is None or force):
            return {"status": "nothing-to-save"}
        reasons = gates.check(entries_of(base) if base else None, entries, self.settings()) if gate else []
        blob_path = self._temp(".zip")
        try:
            blob_sha = pack(entries, roots, blob_path)
            meta = build_meta(
                game_key=game_key,
                entries=entries,
                parents=parents if parents is not None else ([base["snapId"]] if base else []),
                device_id=self.device_id,
                device_name=self.device_name,
                device_seq=self.seq.next(),
                kind=kind,
                flags=flags,
                blob_sha256=blob_sha,
                plugin_version=self.plugin_version,
                created=self.clock(),
            )
            if reasons:
                self.quarantine.save(game_key, meta, blob_path, {"reasons": reasons})
                return {"status": "quarantined", "snapId": meta["snapId"], "reasons": reasons}
            self.publish(game_key, meta, blob_path)
            return {"status": "published", "snapId": meta["snapId"], "meta": meta}
        finally:
            if os.path.exists(blob_path):
                os.unlink(blob_path)

    def publish(self, game_key: str, meta: Mapping[str, Any], blob_path: str) -> None:
        """Upload blob then metadata, both create-only, verifying the blob hash."""
        validate_meta(dict(meta))
        verify_blob(blob_path, meta)
        key = blob_key(game_key, meta["snapId"])
        try:
            info = self.store.put_new_file(key, blob_path)
            uploaded = info.sha256
        except AlreadyExistsError:
            uploaded = None  # a previous attempt uploaded it; verify below
        if uploaded != meta["blobSha256"]:
            check = self._temp(".zip")
            try:
                received = self.store.get_to_file(key, check).sha256
            finally:
                os.unlink(check)
            if received != meta["blobSha256"]:
                raise SnapshotError("uploaded blob does not match its hash")
        try:
            self.store.put_new(snapshot_key(game_key, meta["snapId"]), meta_bytes(meta))
        except AlreadyExistsError:
            existing = self.store.get(snapshot_key(game_key, meta["snapId"]))
            if existing != meta_bytes(meta):
                raise SnapshotError("a different snapshot already uses this id") from None

    def release_quarantined(self, game_key: str, snap_id: str, confirmed: bool) -> dict[str, Any]:
        """Upload a quarantined snapshot after the user explicitly confirms."""
        if not confirmed:
            return {"status": "needs-confirmation"}
        record = self.quarantine.get(game_key, snap_id)
        meta = dict(record["meta"])
        blob = self.quarantine.blob(game_key, snap_id)
        self.publish(game_key, meta, blob)
        self.quarantine.remove(game_key, snap_id)
        return {"status": "published", "snapId": snap_id}

    # Restoring

    def restore(
        self,
        game_key: str,
        snap_id: str,
        current_files: Mapping[str, list[str]],
        roots: Mapping[str, str | None],
        game_running: bool,
        hook: RestoreHook | None = None,
        staged_blob: str | None = None,
    ) -> dict[str, Any]:
        """Restore a cloud snapshot after taking and verifying a local pre-restore snapshot.

        ``staged_blob`` is a prefetched copy on local disk (section 10: restores
        during the launch gate are local only); it is verified like a download.
        """
        meta = self.get_meta(game_key, snap_id)
        if snap_id in self.pruned(game_key):
            raise SnapshotError("that snapshot's files were pruned by retention")
        blob_path = self._temp(".zip")
        try:
            if staged_blob and os.path.exists(staged_blob):
                shutil.copyfile(staged_blob, blob_path)
            else:
                try:
                    self.store.get_to_file(blob_key(game_key, snap_id), blob_path)
                except NotFoundError as exc:
                    raise SnapshotError("that snapshot's files are missing from the cloud") from exc
            return self._restore_from(game_key, blob_path, meta, current_files, roots, game_running, hook)
        finally:
            os.unlink(blob_path)

    def restore_prerestore(
        self,
        game_key: str,
        snap_id: str,
        current_files: Mapping[str, list[str]],
        roots: Mapping[str, str | None],
        game_running: bool,
    ) -> dict[str, Any]:
        """Undo a restore by restoring one of this device's pre-restore snapshots."""
        record = self.prerestore.get(game_key, snap_id)
        blob = self.prerestore.blob(game_key, snap_id)
        copy = self._temp(".zip")
        shutil.copyfile(blob, copy)
        try:
            return self._restore_from(game_key, copy, record["meta"], current_files, roots, game_running, None)
        finally:
            os.unlink(copy)

    def _restore_from(
        self,
        game_key: str,
        blob_path: str,
        meta: Mapping[str, Any],
        current_files: Mapping[str, list[str]],
        roots: Mapping[str, str | None],
        game_running: bool,
        hook: RestoreHook | None,
    ) -> dict[str, Any]:
        if game_running:
            raise SnapshotError("the game is running; restores happen only before launch or after exit")
        restore.recover(self.runtime_dir)
        verify_blob(blob_path, meta)
        current = scan_entries(current_files, roots)
        if content_hash(current) == meta["contentHash"]:
            return {"status": "already-current", "snapId": meta["snapId"]}
        pre = self._take_prerestore(game_key, current, roots)
        result = restore.restore(blob_path, meta, current, roots, self.runtime_dir, hook)
        return {"status": "restored", "snapId": meta["snapId"], "prerestore": pre, **result}

    def _take_prerestore(self, game_key: str, current: list[FileEntry], roots: Mapping[str, str | None]) -> str:
        blob_path = self._temp(".zip")
        try:
            blob_sha = pack(current, roots, blob_path)
            meta = build_meta(
                game_key=game_key,
                entries=current,
                parents=[],
                device_id=self.device_id,
                device_name=self.device_name,
                device_seq=self.seq.next(),
                kind="manual",
                flags=["pre-restore"],
                blob_sha256=blob_sha,
                plugin_version=self.plugin_version,
                created=self.clock(),
            )
            verify_blob(blob_path, meta)  # principle 3: verified before anything is replaced
            self.prerestore.save(game_key, meta, blob_path)
        finally:
            if os.path.exists(blob_path):
                os.unlink(blob_path)
        for record in self.prerestore.list(game_key)[PRERESTORE_KEEP:]:
            self.prerestore.remove(game_key, record["meta"]["snapId"])
        return str(meta["snapId"])

    # Pins and retention

    def pin(self, game_key: str, snap_id: str, until: float | None = None) -> None:
        self.get_meta(game_key, snap_id)
        body = {"snapId": snap_id, "until": until, "deviceId": self.device_id, "created": self.clock()}
        try:
            self.store.put_new(pin_key(game_key, snap_id), json.dumps(body, sort_keys=True).encode())
        except AlreadyExistsError:
            pass  # already pinned; pins are write-once (ADR-0007)

    def cloud_bases(self, game_key: str) -> dict[str, str]:
        """Each device's current base: the highest ``deviceSeq`` under ``bases/<deviceId>/``."""
        newest: dict[str, tuple[int, str]] = {}
        for info in self.store.list(f"games/{game_key}/bases/"):
            parts = info.key.split("/")
            if len(parts) != 5 or not parts[4].endswith(".json"):
                continue
            device, seq_text = parts[3], parts[4][:-5]
            if not seq_text.isdigit():
                continue
            seq = int(seq_text)
            if device not in newest or seq > newest[device][0]:
                newest[device] = (seq, info.key)
        out: dict[str, str] = {}
        for device, (_seq, key) in newest.items():
            try:
                record = json.loads(self.store.get(key).decode("utf-8"))
            except (ValueError, NotFoundError):
                continue
            if isinstance(record, dict) and isinstance(record.get("snapId"), str):
                out[device] = record["snapId"]
        return out

    def publish_base(self, game_key: str, snap_id: str) -> None:
        """Record this device's base in the cloud (write-once, ``bases/<deviceId>/<deviceSeq>.json``)."""
        seq = self.seq.next()
        body = {"snapId": snap_id, "deviceId": self.device_id, "deviceSeq": seq, "created": self.clock()}
        key = f"games/{game_key}/bases/{self.device_id}/{seq:06d}.json"
        self.store.put_new(key, json.dumps(body, sort_keys=True).encode())

    def apply_retention(self, game_key: str, bases: set[str]) -> dict[str, Any]:
        bases = set(bases) | set(self.cloud_bases(game_key).values())
        metas = self.list_metas(game_key)
        now = self.clock()
        result = retention.plan(
            metas, retention.active_pins(self.pins(game_key), now), bases, self.pruned(game_key), now
        )
        for snap_id in result["prune"]:
            # Marker first: if interrupted, the next run still deletes the blob.
            try:
                marker = {"snapId": snap_id, "prunedAt": now, "deviceId": self.device_id}
                self.store.put_new(pruned_key(game_key, snap_id), json.dumps(marker, sort_keys=True).encode())
            except AlreadyExistsError:
                pass
            try:
                self.store.delete(blob_key(game_key, snap_id))
            except NotFoundError:
                pass
        result["orphansDeleted"] = self._prune_orphans(game_key, {m["snapId"] for m in metas}, now)
        return result

    def _prune_orphans(self, game_key: str, committed: set[str], now: float) -> list[str]:
        """Delete blobs without metadata once seen for longer than the grace period."""
        path = os.path.join(self.runtime_dir, "orphan-blobs.json")
        seen = read_json(path, default={})
        seen = seen if isinstance(seen, dict) else {}
        deleted: list[str] = []
        current: dict[str, float] = {}
        for info in self.store.list(f"games/{game_key}/blobs/"):
            snap_id = info.key.rsplit("/", 1)[1].removesuffix(".zip")
            if snap_id in committed:
                continue
            first = float(seen.get(info.key, now))
            if now - first >= ORPHAN_GRACE_SECONDS:
                try:
                    self.store.delete(info.key)
                    deleted.append(snap_id)
                except NotFoundError:
                    pass
            else:
                current[info.key] = first
        others = {k: v for k, v in seen.items() if not k.startswith(f"games/{game_key}/blobs/")}
        atomic_write_json(path, {**others, **current})
        return deleted
