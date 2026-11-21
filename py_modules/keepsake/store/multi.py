"""Several save locations at once: one store made of several (ADR-0071).

Snapshots are written once and named by content or by a unique ID (principle 2), so the same
object in two locations is the same object. This store therefore:

- **writes** to every location a key belongs to. It succeeds when at least one location took the
  object or already had it; a location that cannot be reached is caught up later. Only when no
  location can be reached does it fail as unavailable, so the offline queue keeps it, as today.
- **reads** from the first location that has the object. If it is in none of the locations that
  answered and one did not answer, it fails as unavailable (fail closed, P5), never "not found".
- **lists** the union of every location that answers, so heads from all of them are seen together.
- **deletes** (retention only) wherever the object is.
- **catches up**: copies to each location what another one has and it lacks. It never copies a blob
  retention pruned (it has a ``pruned`` marker somewhere), nor an orphan blob without its snapshot,
  and removes a pruned blob a location kept while it was away.

Which locations a key belongs to comes from ``route``: a game can use some of them only.

**Known history stays known.** Snapshot metadata, pruned markers and base records are written once
and never deleted (retention only removes blobs), so each one this store has written or read is
kept in ``cache_dir``. A location that is down then never hides history this device has already
seen: without that, a push while one location is away could miss its base and start a false fork.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any

from ..fsutil import atomic_write_json, read_json
from .base import AlreadyExistsError, NotFoundError, ObjectInfo, Store, StoreError, StoreUnavailable

BLOB = re.compile(r"^games/([^/]+)/blobs/([^/]+)\.zip$")
SNAPSHOT = re.compile(r"^games/([^/]+)/snapshots/([^/]+)\.json$")
PRUNED = re.compile(r"^games/([^/]+)/pruned/([^/]+)$")
GAME = re.compile(r"^games/([^/]+)/")
KEPT = re.compile(r"^games/[^/]+/(snapshots|pruned|bases)/")  # written once, never deleted: safe to keep
CATCH_UP_LIMIT = 200  # objects copied per pass, so a long-offline location never blocks anything
SMALL = 4 * 1024 * 1024


_STATE_LOCKS: dict[str, threading.Lock] = {}
_STATE_LOCKS_LOCK = threading.Lock()


class LocationState:
    """Per location: last success, last problem, objects still to copy, and space used."""

    def __init__(self, path: str | None, clock: Callable[[], float] = time.time) -> None:
        self.path, self.clock = path, clock
        with _STATE_LOCKS_LOCK:  # one lock per file: every store made for it shares it
            self._lock = _STATE_LOCKS.setdefault(path or "", threading.Lock())

    def load(self) -> dict[str, dict[str, Any]]:
        data = read_json(self.path, default={}) if self.path else {}
        return data if isinstance(data, dict) else {}

    def _update(self, name: str, **changes: Any) -> None:
        if not self.path:
            return
        with self._lock:
            data = self.load()
            found = data.get(name)
            entry: dict[str, Any] = found if isinstance(found, dict) else {}
            entry.update(changes)
            data[name] = entry
            atomic_write_json(self.path, data)

    def ok(self, name: str) -> None:
        self._update(name, lastOk=self.clock(), problem=None)

    def failed(self, name: str, problem: str) -> None:
        self._update(name, problem=problem[:200], lastProblem=self.clock())

    def counted(self, name: str, missing: int, used: int) -> None:
        self._update(name, missing=missing, bytes=used, counted=self.clock())


class MultiStore(Store):
    def __init__(
        self,
        locations: dict[str, Store],
        route: Callable[[str], list[str]] | None = None,
        state: LocationState | None = None,
        cache_dir: str | None = None,
    ) -> None:
        if not locations:
            raise StoreError("no save location is set")
        self.locations = dict(locations)
        self.route = route or (lambda key: list(self.locations))
        self.state = state or LocationState(None)
        self.cache_dir = cache_dir

    # The local copy of write-once history

    def _cached_path(self, key: str) -> str | None:
        if not self.cache_dir or not KEPT.match(key):
            return None
        return os.path.join(self.cache_dir, *key.split("/"))

    def _keep(self, key: str, data: bytes) -> None:
        path = self._cached_path(key)
        if path and not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            part = f"{path}.{os.getpid()}.part"
            with open(part, "wb") as handle:
                handle.write(data)
            os.replace(part, path)

    def _cached(self, key: str) -> bytes | None:
        path = self._cached_path(key)
        if path is None or not os.path.isfile(path):
            return None
        with open(path, "rb") as handle:
            return handle.read()

    def _cached_keys(self, prefix: str) -> list[ObjectInfo]:
        if not self.cache_dir:
            return []
        root = os.path.join(self.cache_dir, *[p for p in prefix.split("/") if p])
        folder = root if os.path.isdir(root) else os.path.dirname(root)
        found = []
        for top, _dirs, files in os.walk(folder):
            for name in files:
                if name.endswith(".part"):
                    continue
                full = os.path.join(top, name)
                key = os.path.relpath(full, self.cache_dir).replace(os.sep, "/")
                if key.startswith(prefix) and KEPT.match(key):
                    found.append(ObjectInfo(key, os.path.getsize(full)))
        return found

    def _targets(self, key: str) -> list[tuple[str, Store]]:
        names = [n for n in self.route(key) if n in self.locations] or list(self.locations)
        return [(n, self.locations[n]) for n in names]

    def _write(self, key: str, write: Callable[[Store], ObjectInfo]) -> ObjectInfo:
        created: ObjectInfo | None = None
        exists = False
        unavailable: list[StoreUnavailable] = []
        errors: list[StoreError] = []
        for name, store in self._targets(key):
            try:
                info = write(store)
                created = created or info
                self.state.ok(name)
            except AlreadyExistsError:
                exists = True
                self.state.ok(name)
            except StoreUnavailable as exc:
                unavailable.append(exc)
                self.state.failed(name, str(exc))
            except StoreError as exc:
                errors.append(exc)
                self.state.failed(name, str(exc))
        if created is not None:
            return created  # the others catch up later
        if exists:
            raise AlreadyExistsError(key)
        if errors:
            raise errors[0]
        raise unavailable[0] if unavailable else StoreUnavailable("no save location could be reached")

    def put_new(self, key: str, data: bytes) -> ObjectInfo:
        info = self._write(key, lambda store: store.put_new(key, data))
        self._keep(key, data)
        return info

    def put_new_file(self, key: str, path: str) -> ObjectInfo:
        return self._write(key, lambda store: store.put_new_file(key, path))

    def _read(self, key: str, read: Callable[[Store], Any]) -> Any:
        unavailable = False
        for name, store in self._targets(key):
            try:
                return read(store)
            except NotFoundError:
                continue
            except StoreUnavailable as exc:
                unavailable = True
                self.state.failed(name, str(exc))
        if unavailable:
            raise StoreUnavailable(f"{key} is not in the locations that answered, and one did not answer")
        raise NotFoundError(key)

    def get(self, key: str) -> bytes:
        kept = self._cached(key)
        if kept is not None:
            return kept
        data: bytes = self._read(key, lambda store: store.get(key))
        self._keep(key, data)
        return data

    def get_to_file(self, key: str, dest: str) -> ObjectInfo:
        info: ObjectInfo = self._read(key, lambda store: store.get_to_file(key, dest))
        return info

    def listing(self, prefix: str = "") -> dict[str, dict[str, ObjectInfo]]:
        """Each location that answered, with its objects under ``prefix``."""
        found: dict[str, dict[str, ObjectInfo]] = {}
        for name, store in self._targets(prefix or "-"):
            try:
                found[name] = {info.key: info for info in store.list(prefix)}
                self.state.ok(name)
            except StoreUnavailable as exc:
                self.state.failed(name, str(exc))
        if not found:
            raise StoreUnavailable("no save location could be reached")
        return found

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        union: dict[str, ObjectInfo] = {}
        for objects in self.listing(prefix).values():
            for key, info in objects.items():
                union.setdefault(key, info)
        for info in self._cached_keys(prefix):  # history seen before, wherever it is now
            union.setdefault(info.key, info)
        return [union[k] for k in sorted(union)]

    def delete(self, key: str) -> None:
        reached = False
        for name, store in self._targets(key):
            try:
                store.delete(key)
                reached = True
            except NotFoundError:
                reached = True
            except StoreUnavailable as exc:
                self.state.failed(name, str(exc))
        if not reached:
            raise StoreUnavailable("no save location could be reached")

    # Catching up

    def catch_up(self, prefix: str = "games/", limit: int = CATCH_UP_LIMIT) -> dict[str, int]:
        """Copy to each location what another has and it lacks; returns objects copied per location."""
        listing = self.listing(prefix)
        union: dict[str, str] = {}
        for name, objects in listing.items():
            for key in objects:
                union.setdefault(key, name)
        pruned = {(m.group(1), m.group(2)) for k in union if (m := PRUNED.match(k))}
        snapshots = {(m.group(1), m.group(2)) for k in union if (m := SNAPSHOT.match(k))}
        copied = dict.fromkeys(listing, 0)
        budget = limit
        for name, objects in listing.items():
            store = self.locations[name]
            missing = []
            for key, source in union.items():
                if key in objects or name not in [n for n, _ in self._targets(key)]:
                    continue
                blob = BLOB.match(key)
                if blob and (
                    (blob.group(1), blob.group(2)) in pruned or (blob.group(1), blob.group(2)) not in snapshots
                ):
                    continue  # pruned by retention, or an orphan: never copied back
                missing.append((key, source))
            for key in [k for k in objects if (b := BLOB.match(k)) and (b.group(1), b.group(2)) in pruned]:
                try:
                    store.delete(key)  # pruned while this location was away
                except (NotFoundError, StoreUnavailable):
                    pass
            for key, source in missing[: max(0, budget)]:
                try:
                    self._copy(key, self.locations[source], store, listing[source][key].size)
                    copied[name] += 1
                except AlreadyExistsError:
                    pass
                except StoreUnavailable as exc:
                    self.state.failed(name, str(exc))
                    break
            budget -= copied[name]
            self.state.counted(name, len(missing) - copied[name], sum(i.size for i in objects.values()))
        return copied

    @staticmethod
    def _copy(key: str, source: Store, target: Store, size: int) -> None:
        if size <= SMALL:
            target.put_new(key, source.get(key))
            return
        handle, path = tempfile.mkstemp(prefix="keepsake-copy-")
        os.close(handle)
        try:
            source.get_to_file(key, path)
            target.put_new_file(key, path)
        finally:
            os.unlink(path)


def game_of(key: str) -> str | None:
    match = GAME.match(key)
    return match.group(1) if match else None
