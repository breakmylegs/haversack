"""Save sync directly between paired devices, with no cloud account (slice R7, ADR-0061).

Every device keeps its own snapshot store, a folder on the device. The sync engine works on
that store exactly as it does on a cloud one. When two paired devices can reach each other,
each copies the objects it lacks from the other. Every Saves object is written once
(principle 2), so copying what is missing, in both directions, gives both devices the same
history. Saves changed on both devices meet as two branches of that history, and the engine
shows a conflict as it always does (principle 1).

Two rules keep the history consistent:
- a blob is copied before the snapshot that names it, as the engine itself writes them;
- a blob with a ``pruned`` marker is never copied, and is removed here once the marker
  arrives: retention on either device decides for both, as it does in a shared cloud store.

This module is Saves' side of the exchange. It does not import Replication (P13): the app
hands it a connection with ``request`` and ``request_blob``, and registers its handlers on the
Replication listener.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from collections.abc import Awaitable, Callable
from typing import Any

from .store import AlreadyExistsError, LocalFolderStore, NotFoundError, StoreError
from .store.base import validate_key

PART = 4 * 1024 * 1024
MAX_KEYS = 200_000
PREFIX = "games/"
BLOB = re.compile(r"^games/([^/]+)/blobs/([^/]+)\.zip$")
PRUNED = re.compile(r"^games/([^/]+)/pruned/([^/]+)$")
INCOMING = ".direct-incoming"
NOT_DIRECT = "this device does not sync saves directly; choose Direct between my devices in its Cloud settings"


def _refuse(reason: str) -> dict[str, Any]:
    return {"type": "error", "reason": reason}


def _key(value: Any) -> str:
    key = validate_key(str(value))
    if not key.startswith(PREFIX):
        raise StoreError("only save objects can be asked for")
    return key


def _pruned(keys: set[str]) -> set[tuple[str, str]]:
    return {(m.group(1), m.group(2)) for k in keys if (m := PRUNED.match(k))}


def _order(keys: list[str]) -> list[str]:
    """Snapshots last: a snapshot must never arrive before the blob it names."""
    return sorted(keys, key=lambda k: (1 if "/snapshots/" in k else 0, k))


def read_part(store: LocalFolderStore, key: str, offset: int, length: int) -> bytes:
    path = store._path(key)
    with open(path, "rb") as handle:
        handle.seek(offset)
        return handle.read(length)


def handlers(
    store: Callable[[], LocalFolderStore | None], on_changed: Callable[[str], None] | None = None
) -> dict[str, Callable[[Any, dict[str, Any]], Awaitable[Any]]]:
    """``store-list``, ``store-get`` and ``store-changed`` for the Replication listener (ADR-0061)."""

    async def store_list(_session: Any, _message: dict[str, Any]) -> Any:
        local = store()
        if local is None:
            return _refuse(NOT_DIRECT)
        infos = await asyncio.to_thread(local.list, PREFIX)
        listing = [[i.key, i.size] for i in infos][:MAX_KEYS]
        return {"count": len(listing)}, json.dumps(listing, separators=(",", ":")).encode()

    async def store_get(_session: Any, message: dict[str, Any]) -> Any:
        local = store()
        if local is None:
            return _refuse(NOT_DIRECT)
        try:
            key = _key(message.get("key"))
        except StoreError as exc:
            return _refuse(str(exc))
        offset, length = message.get("offset"), message.get("length")
        if not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or not 0 < length <= PART:
            return _refuse("ask for at most 4 MiB at a time")
        try:
            data = await asyncio.to_thread(read_part, local, key, offset, length)
        except FileNotFoundError:
            return _refuse("that object is not on this device")
        return {"key": key, "offset": offset}, data

    async def store_changed(session: Any, _message: dict[str, Any]) -> Any:
        if store() is None:
            return _refuse(NOT_DIRECT)
        if on_changed:
            on_changed(str(getattr(session, "peer_id", "")))
        return {"type": "store-noted"}

    return {"store-list": store_list, "store-get": store_get, "store-changed": store_changed}


async def exchange(store: LocalFolderStore, connection: Any) -> dict[str, int]:
    """Copy every save object the other device has and this one lacks. Never overwrites anything."""
    _header, raw = await connection.request_blob({"type": "store-list", "prefix": PREFIX})
    try:
        listing = json.loads(raw)
        remote = {_key(k): int(size) for k, size in listing}
    except (ValueError, TypeError, StoreError) as exc:
        raise StoreError("the other device sent a list that is not valid") from exc
    local_infos = await asyncio.to_thread(store.list, PREFIX)
    local = {i.key: i.size for i in local_infos}
    pruned = _pruned(set(remote) | set(local))
    wanted = []
    for key in remote:
        if key in local:
            continue
        blob = BLOB.match(key)
        if blob and (blob.group(1), blob.group(2)) in pruned:
            continue  # retention removed it on the other device: it is not copied back
        wanted.append(key)
    copied = received = 0
    incoming = os.path.join(store._root, INCOMING)  # inside the store's own folder, never elsewhere
    os.makedirs(incoming, exist_ok=True)
    for key in _order(wanted):
        size = remote[key]
        fd, tmp = tempfile.mkstemp(prefix="part-", dir=incoming)
        try:
            with os.fdopen(fd, "wb") as handle:
                offset = 0
                while offset < size:
                    _h, data = await connection.request_blob(
                        {"type": "store-get", "key": key, "offset": offset, "length": min(PART, size - offset)},
                        max_size=PART,
                    )
                    if not data:
                        break
                    handle.write(data)
                    offset += len(data)
            if os.path.getsize(tmp) != size:
                raise StoreError(f"{key} arrived with the wrong size")
            try:
                await asyncio.to_thread(store.put_new_file, key, tmp)
                copied += 1
                received += size
            except AlreadyExistsError:
                pass  # written here meanwhile: write-once means it is the same object
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    removed = 0
    for key in [k for k in local if BLOB.match(k)]:
        match = BLOB.match(key)
        if match and (match.group(1), match.group(2)) in pruned:
            try:
                await asyncio.to_thread(store.delete, key)
                removed += 1
            except NotFoundError:
                pass
    return {"copied": copied, "bytes": received, "removed": removed}


async def tell_changed(connection: Any) -> None:
    """Ask the other device to fetch what this one just wrote."""
    await connection.request({"type": "store-changed"})
