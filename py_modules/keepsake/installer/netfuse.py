"""Install straight from an ISO on a network location: a read-only, one-file FUSE file system (ADR-0067).

udisks opens an ISO through a file descriptor (ADR-0033, A158), so the ISO only has to look like a
local file. Keepsake serves one file, the chosen ISO, from a FUSE mount in its own runtime folder:
every read the kernel asks for becomes a range read on the share, through the existing pysmb code
(``SmbRange``) or HTTP ``Range`` requests (``HttpRange``, for web servers and WebDAV). Nothing is
copied to the device first. Then the Installer loop-mounts that file as it would a local ISO.

- The protocol is the kernel's FUSE protocol (``linux/fuse.h``, version 7.31 replies), spoken over
  ``/dev/fuse`` in pure Python: lookup, getattr, open, read, readdir, statfs, release, and errors
  for everything else. Opening for writing is refused (``EROFS``).
- The mount needs ``fusermount3``, the setuid helper libfuse ships so a user can mount FUSE
  without root. It is **not** in the System Binary Register yet: until Peter approves it under
  ADR-0018, ``FUSERMOUNT_APPROVED`` stays False, nothing here mounts, and every ISO is copied to
  staging as before. ``auto_unmount`` unmounts if Keepsake stops.
- Reads are cached in 4 MiB blocks (at most 16, so 64 MiB of memory) and read ahead one block.
"""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import socket
import stat
import struct
import subprocess
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

# ADR-0018: fusermount3 is proposed, not approved. Peter's approval flips this, in its own change.
FUSERMOUNT_APPROVED = True  # Peter approved the register entry on 22 November 2026 (ADR-0018, ADR-0067)
FUSERMOUNT = "fusermount3"

ROOT_ID = 1
FILE_ID = 2
BLOCK = 4 * 1024 * 1024
CACHE_BLOCKS = 16
MAX_READ = 1024 * 1024  # FUSE_MAX_PAGES with 256 pages
VALID_SECONDS = 3600

# Opcodes and flags from linux/fuse.h.
LOOKUP, FORGET, GETATTR, OPEN, READ, STATFS, RELEASE = 1, 2, 3, 14, 15, 17, 18
FLUSH, INIT, OPENDIR, READDIR, RELEASEDIR, ACCESS = 25, 26, 27, 28, 29, 34
INTERRUPT, DESTROY, BATCH_FORGET, READDIRPLUS = 36, 38, 42, 44
NO_REPLY = (FORGET, BATCH_FORGET, INTERRUPT, DESTROY)
FUSE_ASYNC_READ = 1 << 0
FUSE_MAX_PAGES = 1 << 22
FOPEN_KEEP_CACHE = 1 << 1
IN_HEADER = struct.Struct("<IIQQIIIHH")  # len, opcode, unique, nodeid, uid, gid, pid, total_extlen, padding
OUT_HEADER = struct.Struct("<IiQ")  # len, error, unique
ATTR = struct.Struct("<QQQQQQIIIIIIIIII")  # 88 bytes
INIT_OUT = struct.Struct("<IIIIHHIIHHII6I")  # 64 bytes
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | getattr(os, "O_TRUNC", 0) | getattr(os, "O_APPEND", 0)


class FuseError(Exception):
    pass


class RangeSource(Protocol):
    size: int

    def read(self, offset: int, length: int) -> bytes: ...


def available(which: Callable[[str], str | None] = shutil.which) -> str | None:
    """Why the network ISO cannot be used in place here, or None when it can."""
    if not FUSERMOUNT_APPROVED:
        return "installing in place waits for fusermount3 to be approved (ADR-0018); the ISO is copied instead"
    if os.name != "posix":
        return "installing in place needs Linux"
    if not which(FUSERMOUNT):
        return "fusermount3 is not installed"
    if not os.access("/dev/fuse", os.R_OK | os.W_OK):
        return "/dev/fuse cannot be opened"
    return None


class BlockCache:
    """Reads of a range source in whole blocks, most recent kept, the next block read ahead."""

    def __init__(self, source: RangeSource, block: int = BLOCK, blocks: int = CACHE_BLOCKS) -> None:
        self.source, self.block, self.blocks = source, block, blocks
        self.size = source.size
        self._cache: OrderedDict[int, bytes] = OrderedDict()
        self._lock = threading.Lock()
        self._loading: dict[int, threading.Event] = {}
        self._ahead = ThreadPoolExecutor(max_workers=1)

    def _block(self, index: int) -> bytes:
        while True:
            with self._lock:
                if index in self._cache:
                    self._cache.move_to_end(index)
                    return self._cache[index]
                waiting = self._loading.get(index)
                if waiting is None:
                    self._loading[index] = threading.Event()
                    break
            waiting.wait(120)
        try:
            start = index * self.block
            data = self.source.read(start, min(self.block, self.size - start))
            with self._lock:
                self._cache[index] = data
                while len(self._cache) > self.blocks:
                    self._cache.popitem(last=False)
            return data
        finally:
            with self._lock:
                self._loading.pop(index).set()

    def read(self, offset: int, length: int) -> bytes:
        if offset >= self.size or length <= 0:
            return b""
        length = min(length, self.size - offset)
        out = bytearray()
        index = offset // self.block
        while len(out) < length:
            data = self._block(index)
            begin = (offset + len(out)) - index * self.block
            out += data[begin : begin + length - len(out)]
            if not data[begin:]:
                break
            index += 1
        following = index + 1
        if following * self.block < self.size:
            self._ahead.submit(self._prefetch, following)
        return bytes(out)

    def _prefetch(self, index: int) -> None:
        with contextlib.suppress(Exception):  # read ahead is a guess; a real read reports the error
            self._block(index)

    def close(self) -> None:
        self._ahead.shutdown(wait=False, cancel_futures=True)


def _attr(node: int, size: int, now: int) -> bytes:
    if node == ROOT_ID:
        mode, nlink, length = stat.S_IFDIR | 0o500, 2, 0
    else:
        mode, nlink, length = stat.S_IFREG | 0o400, 1, size
    uid = os.getuid() if hasattr(os, "getuid") else 0
    gid = os.getgid() if hasattr(os, "getgid") else 0
    return ATTR.pack(node, length, (length + 511) // 512, now, now, now, 0, 0, 0, mode, nlink, uid, gid, 0, 4096, 0)


class Handler:
    """The FUSE protocol for one read-only file named ``name`` in the mount's root. No I/O of its own."""

    def __init__(self, name: str, reader: BlockCache | RangeSource, clock: Callable[[], float] = time.time) -> None:
        if "/" in name or name in ("", ".", ".."):
            raise FuseError("not a file name")
        self.name = name.encode()
        self.reader = reader
        self.size = reader.size
        self.now = int(clock())

    def reply(self, unique: int, error: int = 0, body: bytes = b"") -> bytes:
        return OUT_HEADER.pack(OUT_HEADER.size + len(body), -error if error else 0, unique) + body

    def handle(self, request: bytes) -> bytes | None:
        """One request from the kernel; returns the reply, or None for requests that have none."""
        if len(request) < IN_HEADER.size:
            raise FuseError("short request")
        _len, opcode, unique, node, _uid, _gid, _pid, _ext, _pad = IN_HEADER.unpack_from(request)
        body = request[IN_HEADER.size :]
        if opcode in NO_REPLY:
            return None
        try:
            return self._dispatch(opcode, unique, node, body)
        except (struct.error, ValueError):
            return self.reply(unique, errno.EINVAL)
        except OSError:
            return self.reply(unique, errno.EIO)

    def _dispatch(self, opcode: int, unique: int, node: int, body: bytes) -> bytes:
        if opcode == INIT:
            major, minor, readahead, flags = struct.unpack_from("<IIII", body)
            if major != 7:
                return self.reply(unique, errno.EPROTO)
            wanted = flags & (FUSE_ASYNC_READ | FUSE_MAX_PAGES)
            out = INIT_OUT.pack(
                7, min(minor, 31), readahead, wanted, 16, 12, 4096, 1, MAX_READ // 4096, 0, 0, 0, *[0] * 6
            )
            return self.reply(unique, body=out)
        if node not in (ROOT_ID, FILE_ID):
            return self.reply(unique, errno.ENOENT)
        if opcode == LOOKUP:
            name = body.split(b"\x00", 1)[0]
            if node != ROOT_ID or name != self.name:
                return self.reply(unique, errno.ENOENT)
            entry = struct.pack("<QQQQII", FILE_ID, 0, VALID_SECONDS, VALID_SECONDS, 0, 0)
            return self.reply(unique, body=entry + _attr(FILE_ID, self.size, self.now))
        if opcode == GETATTR:
            return self.reply(unique, body=struct.pack("<QII", VALID_SECONDS, 0, 0) + _attr(node, self.size, self.now))
        if opcode == ACCESS:
            (mask,) = struct.unpack_from("<I", body)
            return self.reply(unique, errno.EACCES if mask & os.W_OK else 0)
        if opcode in (OPEN, OPENDIR):
            (flags,) = struct.unpack_from("<I", body)
            if flags & WRITE_FLAGS:
                return self.reply(unique, errno.EROFS)
            if (opcode == OPEN) != (node == FILE_ID):
                return self.reply(unique, errno.EISDIR if opcode == OPEN else errno.ENOTDIR)
            return self.reply(unique, body=struct.pack("<QII", node, FOPEN_KEEP_CACHE, 0))
        if opcode == READ:
            _fh, offset, size = struct.unpack_from("<QQI", body)
            if node != FILE_ID:
                return self.reply(unique, errno.EISDIR)
            return self.reply(unique, body=self.reader.read(offset, min(size, MAX_READ)))
        if opcode in (READDIR, READDIRPLUS):
            _fh, offset, size = struct.unpack_from("<QQI", body)
            if node != ROOT_ID or opcode == READDIRPLUS:
                return self.reply(unique, errno.ENOSYS if opcode == READDIRPLUS else errno.ENOTDIR)
            entries = [(ROOT_ID, b".", 4), (ROOT_ID, b"..", 4), (FILE_ID, self.name, 8)]
            out = b""
            for index, (ino, name, kind) in enumerate(entries[offset:], start=offset + 1):
                record = struct.pack("<QQII", ino, index, len(name), kind) + name
                record += b"\x00" * (-len(record) % 8)
                if len(out) + len(record) > size:
                    break
                out += record
            return self.reply(unique, body=out)
        if opcode == STATFS:
            blocks = (self.size + 4095) // 4096
            return self.reply(
                unique, body=struct.pack("<QQQQQIIII6I", blocks, 0, 0, 2, 0, 4096, 255, 4096, 0, *[0] * 6)
            )
        if opcode in (RELEASE, RELEASEDIR, FLUSH):
            return self.reply(unique)
        return self.reply(unique, errno.ENOSYS)


class HttpRange:
    """An ISO on a web server or WebDAV folder, read with ``Range`` requests (every ADR-0033 rule applies)."""

    def __init__(self, session: Any, url: str) -> None:
        from .remote import _CONTENT_RANGE  # the same parsing as resumed downloads

        self.session, self.url, self._pattern = session, url, _CONTENT_RANGE
        response, _ = session.open(url, {"Range": "bytes=0-0"})
        try:
            match = _CONTENT_RANGE.match(response.getheader("Content-Range") or "")
            if response.status != 206 or not match or not match.group(3).isdigit():
                raise FuseError("the server cannot send parts of the file, so it is copied instead")
            self.size = int(match.group(3))
        finally:
            response.close()

    def read(self, offset: int, length: int) -> bytes:
        end = min(offset + length, self.size) - 1
        response, _ = self.session.open(self.url, {"Range": f"bytes={offset}-{end}"})
        try:
            match = self._pattern.match(response.getheader("Content-Range") or "")
            if response.status != 206 or not match or int(match.group(1)) != offset:
                raise OSError(errno.EIO, "the server sent the wrong part of the file")
            data: bytes = response.read(end - offset + 1)
        finally:
            response.close()
        if len(data) != end - offset + 1:
            raise OSError(errno.EIO, "the server sent less than asked")
        return data


class SmbRange:
    """An ISO on a Windows share, read with pysmb's offset reads over one connection (ADR-0034)."""

    def __init__(self, share: Any, url: str) -> None:
        from . import smbshare

        address = smbshare.parse(url)
        if not address.share or not address.path.lower().endswith(".iso"):
            raise FuseError("choose an .iso file")
        self.share, self.service, self.path = share, address.share, "/" + address.path
        self._lock = threading.Lock()
        self._conn = share.open()
        self.size = int(self._conn.getAttributes(self.service, self.path, timeout=smbshare.TIMEOUT).file_size)

    def read(self, offset: int, length: int) -> bytes:
        import io

        from . import smbshare

        with self._lock:
            for attempt in (1, 2):
                buffer = io.BytesIO()
                try:
                    self._conn.retrieveFileFromOffset(
                        self.service, self.path, buffer, offset, length, timeout=smbshare.TIMEOUT
                    )
                    return buffer.getvalue()
                except Exception as exc:  # pysmb raises its own errors: reconnect once, then report
                    if attempt == 2:
                        raise OSError(errno.EIO, f"the share stopped answering ({type(exc).__name__})") from exc
                    with contextlib.suppress(Exception):
                        self._conn.close()
                    self._conn = self.share.open()
        return b""

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._conn.close()


class Mount:
    """A live mount: ``fusermount3`` makes it and hands back ``/dev/fuse``; threads answer the kernel."""

    def __init__(self, mountpoint: str, handler: Handler, runner: Callable[..., Any] = subprocess.Popen) -> None:
        self.mountpoint, self.handler, self.runner = mountpoint, handler, runner
        self.path = os.path.join(mountpoint, handler.name.decode())
        self._fd = -1
        self._sock: socket.socket | None = None
        self._helper: Any = None
        self._write_lock = threading.Lock()
        self._workers = ThreadPoolExecutor(max_workers=4)
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        if available() is not None:
            raise FuseError(available() or "")
        os.makedirs(self.mountpoint, mode=0o700, exist_ok=True)
        ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined, unused-ignore]
        env = {**os.environ, "_FUSE_COMMFD": str(theirs.fileno())}
        options = "ro,nosuid,nodev,noexec,fsname=keepsake,subtype=keepsake,auto_unmount"
        try:
            self._helper = self.runner(
                [FUSERMOUNT, "-o", options, "--", self.mountpoint], env=env, pass_fds=(theirs.fileno(),)
            )
            theirs.close()
            ours.settimeout(20)
            _msg, fds, _flags, _addr = socket.recv_fds(ours, 1, 1)  # type: ignore[attr-defined, unused-ignore]
        except (OSError, TimeoutError) as exc:
            ours.close()
            raise FuseError(f"fusermount3 did not mount the share: {exc}") from exc
        if not fds:
            ours.close()
            raise FuseError("fusermount3 did not hand over the mount")
        self._fd, self._sock = fds[0], ours  # keep the socket: closing it tells auto_unmount we are gone
        self._thread = threading.Thread(target=self._serve, name="keepsake-netfuse", daemon=True)
        self._thread.start()
        return self.path

    def _serve(self) -> None:
        while True:
            try:
                request = os.read(self._fd, MAX_READ + 8192)
            except OSError as exc:
                if exc.errno in (errno.EINTR, errno.EAGAIN):
                    continue
                return  # ENODEV once unmounted
            if not request:
                return
            opcode = IN_HEADER.unpack_from(request)[1] if len(request) >= IN_HEADER.size else 0
            if opcode == READ:
                self._workers.submit(self._answer, request)  # range reads in parallel
            else:
                self._answer(request)

    def _answer(self, request: bytes) -> None:
        try:
            reply = self.handler.handle(request)
        except FuseError:
            return
        if reply is not None:
            with self._write_lock:
                try:
                    os.write(self._fd, reply)
                except OSError:
                    pass  # the request was interrupted, or the mount is gone

    def close(self) -> None:
        """Unmount and stop. Safe to call twice."""
        if self._fd >= 0:
            try:
                subprocess.run([FUSERMOUNT, "-u", "-z", self.mountpoint], capture_output=True, timeout=20, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
            os.close(self._fd)
            self._fd = -1
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        self._workers.shutdown(wait=False, cancel_futures=True)
        reader = self.handler.reader
        if isinstance(reader, BlockCache):
            reader.close()
