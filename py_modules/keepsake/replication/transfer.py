"""The receiving side: pull a shared folder into place, exactly (slice 18a, ADR-0057).

Everything a job writes is inside one staging folder beside the target, so promote is a
rename on the same file system and "Stop and remove" is one folder to delete:

    <target parent>/.keepsake-incoming-<job>/
        journal.json      state and verified chunks (write, fsync, rename, fsync folder)
        manifest.json     the manifest, checked against the offered root hash
        tree/             the copy being built
        previous/         the target it replaces, held until the job completes

A chunk counts as done only once its bytes are fsynced and the journal says so. On resume,
chunks the journal does not list are hashed again from disk, so only those that might be
incomplete are checked, and only bad ones are fetched again. Nothing is promoted until every
file matches its whole-file hash from the manifest.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import errno
import hashlib
import json
import os
import shutil
import stat
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..fsutil import atomic_write_bytes, atomic_write_json, read_json
from . import manifest as mf
from . import policy
from .link import Connection, LinkError, Refused

STAGING_PREFIX = ".keepsake-incoming-"
STATES = ("running", "waiting", "paused", "verifying", "promoting", "done", "failed", "stopped")
JOURNAL_EVERY_SECONDS = 2.0
JOURNAL_EVERY_CHUNKS = 16
CORRUPT_LIMIT = 3
MAX_KEEP = 50_000  # files an update keeps from the target (ADR-0060)
RETRY_MIN, RETRY_MAX = 1.0, 60.0
MAX_STREAMS = 4
ADAPT_SECONDS = 3.0  # how often the rate is measured and a stream may be added
ADD_STREAM_GAIN = 1.10  # another stream is added only while the rate rose by 10 percent

Connect = Callable[[], Awaitable[Connection]]
_rename = os.replace  # promote's two renames (tests interrupt them here)


class TransferError(Exception):
    pass


class DiskFull(TransferError):
    pass


def staging_for(target: str, job_id: str) -> str:
    parent = os.path.dirname(os.path.abspath(target))
    return os.path.join(parent, f"{STAGING_PREFIX}{job_id}")


@dataclass
class Job:
    id: str
    peer_id: str
    share: str
    root: str  # the manifest root hash the user agreed to receive
    target: str
    state: str = "running"
    reason: str | None = None
    done: dict[str, list[int]] = field(default_factory=dict)
    total: int = 0
    received: int = 0
    rate_limit: int = 0  # bytes a second; 0 is no cap
    held: bool = False  # paused by the battery or a running game, not by the user: resumes by itself
    by_user: bool = False  # paused by the user: waits for Resume
    peers: list[str] = field(default_factory=list)  # every device offering this root (ADR-0058)
    keep: list[str] = field(default_factory=list)  # files of the target that stay as they are (ADR-0060, P14)
    rate: float = 0.0  # bytes a second, smoothed
    streams: int = 0

    @property
    def staging(self) -> str:
        return staging_for(self.target, self.id)

    def journal(self) -> dict[str, Any]:
        return {
            "version": 1,
            "id": self.id,
            "peer": self.peer_id,
            "share": self.share,
            "root": self.root,
            "target": self.target,
            "state": self.state,
            "reason": self.reason,
            "done": self.done,
            "rateLimit": self.rate_limit,
            "held": self.held,
            "byUser": self.by_user,
            "peers": self.peers,
            "keep": self.keep,
        }

    @classmethod
    def from_journal(cls, data: dict[str, Any]) -> Job:
        raw = data.get("done")
        done: dict[str, Any] = raw if isinstance(raw, dict) else {}
        return cls(
            id=str(data["id"]),
            peer_id=str(data["peer"]),
            share=str(data["share"]),
            root=str(data["root"]),
            target=str(data["target"]),
            state=str(data.get("state") or "paused"),
            reason=data.get("reason"),
            done={str(k): sorted({int(i) for i in v}) for k, v in done.items() if isinstance(v, list)},
            rate_limit=int(data.get("rateLimit") or 0),
            held=bool(data.get("held")),
            by_user=bool(data.get("byUser")),
            peers=[str(p) for p in data.get("peers") or [] if isinstance(p, str)][:8],
            keep=[str(p) for p in data.get("keep") or [] if isinstance(p, str)][:MAX_KEEP],
        )

    def public(self) -> dict[str, Any]:
        left = max(0, self.total - self.received)
        return {
            "id": self.id,
            "peer": self.peer_id,
            "peers": self.peers or [self.peer_id],
            "target": os.path.basename(self.target),
            "state": self.state,
            "reason": self.reason,
            "held": self.held,
            "total": self.total,
            "received": self.received,
            "megabytesPerSecond": round(self.rate / 1_000_000, 1),
            "secondsLeft": int(left / self.rate) if self.rate > 0 and self.state == "running" else None,
            "streams": self.streams,
            "rateLimit": self.rate_limit,
        }


def save_journal(job: Job, done: dict[str, list[int]] | None = None) -> None:
    """Write the journal durably. ``done`` is the chunk list as it was when its data was flushed."""
    data = job.journal()
    if done is not None:
        data["done"] = done
    atomic_write_json(os.path.join(job.staging, "journal.json"), data)


def load_journal(staging: str) -> Job | None:
    try:
        data = read_json(os.path.join(staging, "journal.json"), default=None)
        return Job.from_journal(data) if isinstance(data, dict) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


class RateLimit:
    """A simple pacing cap: sleep so that the average stays under ``per_second``."""

    def __init__(self, per_second: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_second = per_second
        self.clock = clock
        self.started = clock()
        self.sent = 0

    async def take(self, size: int) -> None:
        if self.per_second <= 0:
            return
        self.sent += size
        ahead = self.sent / self.per_second - (self.clock() - self.started)
        if ahead > 0:
            await asyncio.sleep(ahead)


def _fsync(path: str) -> None:
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))  # Windows cannot flush a read-only handle
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_at(path: str, offset: int, data: bytes) -> None:
    try:
        with open(path, "r+b") as handle:
            handle.seek(offset)
            handle.write(data)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise DiskFull("the disk is full") from exc
        raise


def _read_at(path: str, offset: int, size: int) -> bytes:
    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            return handle.read(size)
    except OSError:
        return b""


def _prepare_file(path: str, size: int, zero: list[bool]) -> None:
    """Create the staged file at full size. Data chunks are preallocated where Linux allows;
    zero chunks stay holes, so a sparse file stays sparse."""
    fresh = not os.path.exists(path)
    with open(path, "ab"):
        pass
    if os.path.getsize(path) != size:
        os.truncate(path, size)
    if not fresh or not hasattr(os, "posix_fallocate"):
        return
    fd = os.open(path, os.O_RDWR)
    try:
        offset = 0
        for sz, is_zero in zip(mf.chunk_sizes(size), zero, strict=True):
            if not is_zero:
                try:
                    os.posix_fallocate(fd, offset, sz)
                except OSError as exc:
                    if exc.errno == errno.ENOSPC:
                        raise DiskFull("the disk is full") from exc
                    break  # a file system without preallocation: carry on without it
            offset += sz
    finally:
        os.close(fd)


class Held(TransferError):
    """The battery or a running game asks the transfer to wait (ADR-0058). It resumes by itself."""


class _Pull:
    """What the streams of one pull share."""

    def __init__(self, items: list[tuple[str, int, str, int]], rate_limit: int) -> None:
        self.queue = collections.deque(items)
        self.pending: set[str] = set()
        self.pace = RateLimit(rate_limit)
        self.window_bytes = 0
        self.lock = asyncio.Lock()  # one journal commit at a time


class Receiver:
    """Runs one job to the end, or until it is paused, stopped or fails.

    Chunks are pulled by up to ``max_streams`` streams spread over one or more sources (paired
    devices offering the same root). It starts with one stream and adds another only while the
    measured rate keeps rising, so a slow link is not crowded and a fast one is filled (ADR-0058).
    A source whose connection fails is dropped; the job waits and retries only when none is left.
    """

    def __init__(
        self,
        job: Job,
        connect: Connect | Sequence[Connect],
        windows_target: bool = False,
        retries: int | None = None,
        on_progress: Callable[[Job], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        hold: Callable[[], str | None] | None = None,
        max_streams: int = MAX_STREAMS,
        adapt_seconds: float = ADAPT_SECONDS,
    ) -> None:
        self.job = job
        self.sources: list[Connect] = list(connect) if isinstance(connect, (list, tuple)) else [connect]  # type: ignore[list-item]
        self.windows_target = windows_target
        self.retries = retries  # None: keep trying (with backoff) until paused or stopped
        self.on_progress = on_progress
        self.sleep = sleep
        self.hold = hold
        self.max_streams = max(1, max_streams)
        self.adapt_seconds = adapt_seconds
        self.manifest: dict[str, Any] | None = None
        self._control: Connection | None = None

    # The whole job

    async def run(self) -> Job:
        job = self.job
        attempt = 0
        os.makedirs(os.path.join(job.staging, "tree"), exist_ok=True)
        while True:
            job.state, job.reason, job.held = "running", None, False
            await asyncio.to_thread(save_journal, job)
            try:
                await self._pull()
                await self._finish()
                return job
            except Refused as exc:
                return await self._end("failed", str(exc))
            except (LinkError, ConnectionError, TimeoutError) as exc:
                attempt += 1
                if self.retries is not None and attempt > self.retries:
                    return await self._end("failed", f"the other device could not be reached: {exc}")
                job.state, job.reason = "waiting", f"waiting for the other device: {exc}"
                await asyncio.to_thread(save_journal, job)
                self._notify()
                await self.sleep(min(RETRY_MAX, RETRY_MIN * 2 ** (attempt - 1)))
            except Held as exc:
                job.held = True
                return await self._end("paused", str(exc))
            except DiskFull as exc:
                return await self._end("paused", f"{exc}: free some space, then resume")
            except (TransferError, mf.ManifestError, policy.PolicyError) as exc:
                return await self._end("failed", str(exc))
            finally:
                await self._disconnect()
                job.rate, job.streams = 0.0, 0

    async def _end(self, state: str, reason: str | None) -> Job:
        self.job.state, self.job.reason = state, reason
        with contextlib.suppress(OSError):
            await asyncio.to_thread(save_journal, self.job)
        self._notify()
        return self.job

    def _notify(self) -> None:
        if self.on_progress:
            self.on_progress(self.job)

    async def _first_connection(self) -> Connection:
        """A connection for the manifest: the first source that answers."""
        if self._control is not None:
            return self._control
        error: Exception | None = None
        for source in self.sources:
            try:
                self._control = await source()
                return self._control
            except (LinkError, ConnectionError, TimeoutError) as exc:
                error = exc
        raise error if error else LinkError("no device offers this folder")

    async def _disconnect(self) -> None:
        if self._control is not None:
            with contextlib.suppress(Exception):
                await self._control.close()
            self._control = None

    # Manifest and space

    async def _manifest(self) -> dict[str, Any]:
        if self.manifest is not None:
            return self.manifest
        job = self.job
        path = os.path.join(job.staging, "manifest.json")
        try:
            with open(path, "rb") as handle:
                data = json.loads(handle.read())
        except (OSError, ValueError):
            header, raw = await (await self._first_connection()).request_blob({"type": "manifest", "share": job.share})
            try:
                data = json.loads(raw)
            except ValueError as exc:
                raise TransferError("the other device sent a damaged manifest") from exc
            data["root"] = header.get("root")
            mf.validate(data, job.root, self.windows_target)
            await asyncio.to_thread(atomic_write_bytes, path, json.dumps(data).encode())
        self.manifest = mf.validate(data, job.root, self.windows_target)
        job.total = mf.total_bytes(self.manifest)
        return self.manifest

    def _check_space(self, manifest: dict[str, Any]) -> None:
        remaining = 0
        for entry in manifest["entries"]:
            if entry["type"] == "file":
                done = set(self.job.done.get(entry["path"], []))
                sizes = mf.chunk_sizes(entry["size"])
                remaining += sum(s for i, s in enumerate(sizes) if i not in done)
        free = shutil.disk_usage(self.job.staging).free
        needed = policy.space_needed(remaining)
        if free < needed:
            raise DiskFull(f"not enough space: {needed // 2**20} MiB needed with margin, {free // 2**20} MiB free")

    # Pulling chunks

    def _staged(self, rel: str) -> str:
        return os.path.join(self.job.staging, "tree", *rel.split("/"))

    def _wanted(self, manifest: dict[str, Any]) -> list[tuple[str, int, str, int]]:
        items = []
        for entry in manifest["entries"]:
            if entry["type"] != "file":
                continue
            done = set(self.job.done.get(entry["path"], []))
            for index, (expected, size) in enumerate(zip(entry["chunks"], mf.chunk_sizes(entry["size"]), strict=True)):
                if index not in done and not mf.is_zero_chunk(expected, size):
                    items.append((entry["path"], index, expected, size))
        return items

    async def _pull(self) -> None:
        manifest = await self._manifest()
        job = self.job
        await asyncio.to_thread(self._check_space, manifest)
        await asyncio.to_thread(self._make_tree, manifest)
        await asyncio.to_thread(self._recheck, manifest)
        shared = _Pull(self._wanted(manifest), job.rate_limit)
        alive = list(range(len(self.sources)))
        workers: dict[asyncio.Task[None], int] = {}

        def spawn() -> None:
            source = alive[len(workers) % len(alive)]
            reuse, self._control = (self._control, None) if not workers else (None, self._control)
            task = asyncio.create_task(self._worker(source, shared, reuse))
            workers[task] = source

        if shared.queue:
            spawn()
        last_journal = window_start = time.monotonic()
        last_rate: float | None = None
        growing = True
        try:
            while workers:
                finished, _ = await asyncio.wait(
                    workers, timeout=self.adapt_seconds, return_when=asyncio.FIRST_COMPLETED
                )
                for task in finished:
                    source = workers.pop(task)
                    error = task.exception()
                    if error is None:
                        continue
                    if isinstance(error, (LinkError, ConnectionError, TimeoutError)) and not isinstance(error, Refused):
                        if source in alive:
                            alive.remove(source)  # this source is gone for now; others carry on
                        if not alive:
                            raise error
                        if not workers and shared.queue:
                            spawn()
                        continue
                    raise error
                reason = self.hold() if self.hold else None
                if reason:
                    raise Held(reason)
                now = time.monotonic()
                if now - window_start >= self.adapt_seconds:
                    rate = shared.window_bytes / (now - window_start)
                    job.rate = rate if not job.rate else 0.7 * job.rate + 0.3 * rate
                    shared.window_bytes, window_start = 0, now
                    if growing and len(workers) < self.max_streams and shared.queue:
                        if last_rate is None or rate > last_rate * ADD_STREAM_GAIN:
                            spawn()
                        else:
                            growing = False  # one more stream did not help: this is the link's speed
                    last_rate = rate
                job.streams = len(workers)
                if shared.pending and now - last_journal > JOURNAL_EVERY_SECONDS:
                    await self._commit_now(shared)
                    last_journal = now
                    self._notify()
        finally:
            for task in workers:
                task.cancel()
            for task in workers:
                with contextlib.suppress(BaseException):
                    await task
        await self._commit_now(shared)

    async def _commit_now(self, shared: _Pull) -> None:
        async with shared.lock:
            # What to record is fixed before the flush: chunks written meanwhile wait for the next commit.
            pending, shared.pending = shared.pending, set()
            listed = {rel: list(chunks) for rel, chunks in self.job.done.items()}
            await asyncio.to_thread(self._commit, pending, listed)

    async def _worker(self, source: int, shared: _Pull, connection: Connection | None) -> None:
        connection = connection or await self.sources[source]()
        try:
            while shared.queue:
                item = shared.queue.popleft()
                rel, index, expected, size = item
                try:
                    data = await self._fetch(connection, rel, index, expected, size)
                    await shared.pace.take(size)
                    await asyncio.to_thread(_write_at, self._staged(rel), index * mf.CHUNK, data)
                except BaseException:
                    shared.queue.appendleft(item)  # not done: another stream, or the next try, takes it
                    raise
                self.job.done.setdefault(rel, []).append(index)
                self.job.received += size
                shared.window_bytes += size
                shared.pending.add(rel)
                if len(shared.pending) >= JOURNAL_EVERY_CHUNKS:
                    await self._commit_now(shared)  # the stream that fills a batch records it
        finally:
            with contextlib.suppress(Exception):
                await connection.close()

    async def _fetch(self, connection: Connection, rel: str, index: int, expected: str, size: int) -> bytes:
        for _ in range(CORRUPT_LIMIT):
            _header, data = await connection.request_blob(
                {"type": "chunk", "share": self.job.share, "path": rel, "index": index}, max_size=mf.CHUNK
            )
            if len(data) == size and hashlib.sha256(data).hexdigest() == expected:
                return data
        raise TransferError(f"a piece of {rel[:80]} arrived damaged {CORRUPT_LIMIT} times; the transfer stopped")

    def _commit(self, paths: set[str], listed: dict[str, list[int]] | None = None) -> None:
        """Make the written chunks durable, then record them: data first, journal second."""
        for rel in paths:
            _fsync(self._staged(rel))
        save_journal(self.job, listed)

    def _make_tree(self, manifest: dict[str, Any]) -> None:
        for entry in manifest["entries"]:
            path = self._staged(entry["path"])
            if entry["type"] == "dir":
                os.makedirs(path, exist_ok=True)
            elif entry["type"] == "file":
                os.makedirs(os.path.dirname(path), exist_ok=True)
                sizes = mf.chunk_sizes(entry["size"])
                zero = [mf.is_zero_chunk(h, s) for h, s in zip(entry["chunks"], sizes, strict=True)]
                _prepare_file(path, int(entry["size"]), zero)

    def _recheck(self, manifest: dict[str, Any]) -> None:
        """After a restart: chunks not in the journal may be complete on disk. Hash only those."""
        job = self.job
        job.received = 0
        for entry in manifest["entries"]:
            if entry["type"] != "file":
                continue
            done = set(job.done.get(entry["path"], []))
            path = self._staged(entry["path"])
            for index, (expected, size) in enumerate(zip(entry["chunks"], mf.chunk_sizes(entry["size"]), strict=True)):
                if mf.is_zero_chunk(expected, size):
                    continue
                if index not in done and hashlib.sha256(_read_at(path, index * mf.CHUNK, size)).hexdigest() == expected:
                    done.add(index)
                if index in done:
                    job.received += size
            job.done[entry["path"]] = sorted(done)
        save_journal(job)

    # Verify, then promote

    async def _finish(self) -> None:
        manifest = await self._manifest()
        job = self.job
        job.state = "verifying"
        await asyncio.to_thread(save_journal, job)
        self._notify()
        bad = await asyncio.to_thread(self._verify, manifest)
        if bad:
            for rel in bad:
                job.done.pop(rel, None)
            await asyncio.to_thread(save_journal, job)
            await self._pull()  # fetch those files again, once
            if await asyncio.to_thread(self._verify, manifest):
                raise TransferError("the copy does not match the original after a second try")
        await asyncio.to_thread(self._apply_metadata, manifest)
        if mf.root_hash(manifest) != job.root:
            raise TransferError("the copy does not match what was offered")
        job.state = "promoting"
        await asyncio.to_thread(save_journal, job)
        if job.keep:
            await asyncio.to_thread(carry_over, job)  # after every check: these files are this device's own
        await asyncio.to_thread(promote, job)
        job.state = "done"
        self._notify()
        await asyncio.to_thread(remove_staging, job.staging)

    def _verify(self, manifest: dict[str, Any]) -> list[str]:
        bad = []
        for entry in manifest["entries"]:
            if entry["type"] == "file":
                whole, _ = mf.hash_file(self._staged(entry["path"]))
                if whole != entry["sha256"]:
                    bad.append(entry["path"])
        return bad

    def _apply_metadata(self, manifest: dict[str, Any]) -> None:
        entries = manifest["entries"]
        for entry in entries:
            path = self._staged(entry["path"])
            if entry["type"] == "link":
                if os.path.lexists(path):
                    os.unlink(path)
                try:
                    os.symlink(entry["target"], path)
                except OSError as exc:
                    raise TransferError(f"this device cannot make the link {entry['path'][:80]}") from exc
        for entry in entries:
            if entry["type"] == "file" and os.name == "posix":
                os.chmod(self._staged(entry["path"]), entry["mode"] & 0o7777)
        # Times last, deepest first, so setting a file's time does not change its folder's again.
        for entry in sorted(entries, key=lambda e: -e["path"].count("/")):
            path = self._staged(entry["path"])
            mtime = int(entry["mtime"])
            if entry["type"] == "link":
                if os.utime in os.supports_follow_symlinks:
                    with contextlib.suppress(OSError):
                        os.utime(path, ns=(mtime, mtime), follow_symlinks=False)
            else:
                os.utime(path, ns=(mtime, mtime))
        for entry in entries:
            if entry["type"] == "dir" and os.name == "posix":
                os.chmod(self._staged(entry["path"]), (entry["mode"] & 0o7777) | stat.S_IRWXU)


def carry_over(job: Job) -> int:
    """Copy the files ``job.keep`` names from the current target into the new copy, over anything there.

    An update replaces a game's folder, but this device's own saves and settings must stay exactly as
    they are (P14): they are copied, never moved, so the target is untouched until promote swaps it.
    """
    tree = os.path.join(job.staging, "tree")
    real_tree = os.path.realpath(tree)
    copied = 0
    for rel in job.keep:
        try:
            mf.check_path(rel)
        except mf.ManifestError:
            continue
        source = os.path.join(job.target, *rel.split("/"))
        if os.path.islink(source) or not os.path.isfile(source):
            continue
        dest = os.path.join(tree, *rel.split("/"))
        parent = os.path.dirname(dest)
        if os.path.commonpath([os.path.realpath(parent), real_tree]) != real_tree:
            continue  # a link in the new copy must not lead the copy outside it
        os.makedirs(parent, exist_ok=True)
        if os.path.islink(dest):
            os.unlink(dest)
        shutil.copy2(source, dest)
        copied += 1
    return copied


RENAME_ATTEMPTS = 20
RENAME_PAUSE = 0.1


def _rename_settled(src: str, dst: str) -> None:
    """Rename, waiting out Windows' brief sharing violations (a scanner holding a just-written file)."""
    for attempt in range(RENAME_ATTEMPTS):
        try:
            _rename(src, dst)
            return
        except PermissionError:
            if os.name != "nt" or attempt == RENAME_ATTEMPTS - 1:
                raise
            time.sleep(RENAME_PAUSE)


def promote(job: Job) -> None:
    """Swap the copy into place. A target that exists is moved aside first and put back on any error."""
    tree = os.path.join(job.staging, "tree")
    previous = os.path.join(job.staging, "previous")
    moved_aside = False
    try:
        if os.path.lexists(job.target):
            _rename_settled(job.target, previous)
            moved_aside = True
        _rename_settled(tree, job.target)
    except OSError as exc:
        if moved_aside and not os.path.lexists(job.target):
            os.replace(previous, job.target)
        raise TransferError(f"could not put the copy in place: {exc.strerror or exc}") from exc


def roll_back(job: Job) -> None:
    """Undo a promote that stopped half way (a crash between its two renames)."""
    # Before the first rename nothing moved; after the second the copy is in place. Only between
    # them is the old target under previous/ with nothing at the target, so only then is it moved back.
    previous = os.path.join(job.staging, "previous")
    if os.path.lexists(previous) and not os.path.lexists(job.target):
        os.replace(previous, job.target)


def remove_staging(staging: str) -> None:
    """Delete a job's staging folder. Only ever a folder named like one, never anything else."""
    if not os.path.basename(staging).startswith(STAGING_PREFIX):
        raise TransferError("refusing to remove a folder that is not Haversack staging")
    if not os.path.lexists(staging):
        return

    def make_writable(func: Any, path: str, _exc: Any) -> None:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)  # read-only files copied from a game
        func(path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(staging, onexc=make_writable)
    else:  # pragma: no cover - Python 3.11
        shutil.rmtree(staging, onerror=make_writable)


def stop_and_remove(job: Job) -> None:
    """The user's "Stop and remove": put any replaced target back, then delete everything the job made."""
    roll_back(job)
    job.state = "stopped"
    remove_staging(job.staging)


def recover(staging: str) -> Job | None:
    """At startup: a job left running is paused; a promote cut short is rolled back; a stopped one is removed."""
    job = load_journal(staging)
    if job is None:
        return None
    if job.state == "stopped":
        remove_staging(staging)
        return None
    if job.state == "promoting":
        roll_back(job)
        if not os.path.lexists(os.path.join(staging, "tree")):
            job.state = "done"  # the copy is in place: only the clean-up was cut short
            remove_staging(staging)
            return job
    if job.state in ("running", "waiting", "verifying", "promoting"):
        job.state, job.reason = "paused", "Haversack restarted; resume to carry on"
        save_journal(job)
    return job
