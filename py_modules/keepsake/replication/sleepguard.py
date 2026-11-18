"""Keep the device awake while a transfer runs, and give it time to checkpoint (slice 18b, ADR-0058).

Linux: logind's ``Inhibit`` over the system D-Bus, called by a minimal stdlib client (no
binary, no library). Two locks are taken:
- "idle" in block mode, so an idle timer does not send the device to sleep mid-copy;
- "sleep" in delay mode, so a sleep the user asks for waits a few seconds (logind's
  ``InhibitDelayMaxSec``), long enough for the journal's regular commit.
A lock is a file descriptor logind hands back; closing it releases the lock.

Windows: ``SetThreadExecutionState`` with ``ES_SYSTEM_REQUIRED``, from the event loop's thread.

Either way, failure is reported, never fatal: the transfer still runs, and resumes after sleep.
"""

from __future__ import annotations

import array
import os
import socket
import struct
import sys
from typing import Any

SYSTEM_BUS = "/run/dbus/system_bus_socket"
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
MAX_MESSAGE = 1 << 20


class SleepGuardError(Exception):
    pass


def _pad(data: bytearray, boundary: int) -> None:
    data.extend(b"\x00" * (-len(data) % boundary))


def _string(data: bytearray, value: str, kind: str = "s") -> None:
    raw = value.encode("utf-8")
    if kind == "g":
        data.append(len(raw))
    else:
        _pad(data, 4)
        data.extend(struct.pack("<I", len(raw)))
    data.extend(raw + b"\x00")


def method_call(serial: int, destination: str, path: str, interface: str, member: str, args: list[str]) -> bytes:
    """A little-endian D-Bus METHOD_CALL whose arguments are all strings."""
    body = bytearray()
    for arg in args:
        _string(body, arg)
    signature = "s" * len(args)
    fields = bytearray()
    for code, kind, value in (
        (1, "o", path),
        (2, "s", interface),
        (3, "s", member),
        (6, "s", destination),
        *(((8, "g", signature),) if signature else ()),
    ):
        _pad(fields, 8)
        fields.extend(bytes([code, 1]) + kind.encode() + b"\x00")
        _string(fields, value, kind)
    header = bytearray(b"l" + bytes([1, 0, 1]) + struct.pack("<III", len(body), serial, len(fields)))
    header.extend(fields)
    _pad(header, 8)
    return bytes(header + body)


def parse_header(data: bytes) -> dict[str, Any]:
    """The fixed header and the fields Keepsake reads: type, reply serial, error name, fd count."""
    if len(data) < 16 or data[0:1] != b"l":
        raise SleepGuardError("not a little-endian D-Bus message")
    kind = data[1]
    body_len, serial, fields_len = struct.unpack("<III", data[4:16])
    end = 16 + fields_len
    if end > len(data) or body_len > MAX_MESSAGE:
        raise SleepGuardError("truncated D-Bus message")
    out: dict[str, Any] = {"type": kind, "serial": serial, "bodyLength": body_len, "fdCount": 0}
    offset = 16
    while offset < end:
        offset += -offset % 8
        if offset >= end:
            break
        code = data[offset]
        sig_len = data[offset + 1]
        sig = data[offset + 2 : offset + 2 + sig_len].decode()
        offset += 3 + sig_len
        if sig in ("s", "o"):
            offset += -offset % 4
            (length,) = struct.unpack("<I", data[offset : offset + 4])
            value: Any = data[offset + 4 : offset + 4 + length].decode("utf-8", errors="replace")
            offset += 5 + length
        elif sig == "g":
            length = data[offset]
            value = data[offset + 1 : offset + 1 + length].decode()
            offset += 2 + length
        elif sig == "u":
            offset += -offset % 4
            (value,) = struct.unpack("<I", data[offset : offset + 4])
            offset += 4
        else:
            raise SleepGuardError(f"unexpected header field type {sig}")
        if code == 4:
            out["error"] = value
        elif code == 5:
            out["replySerial"] = value
        elif code == 9:
            out["fdCount"] = value
    out["length"] = (16 + fields_len + (-(16 + fields_len) % 8)) + body_len
    return out


class Bus:
    """Just enough of a D-Bus connection to call one method and receive one descriptor."""

    def __init__(self, path: str = SYSTEM_BUS) -> None:
        if not hasattr(socket, "AF_UNIX") or not hasattr(socket.socket, "recvmsg"):
            raise SleepGuardError("this system has no D-Bus socket support")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.serial = 0
        self.fds: list[int] = []
        self.buffer = b""
        try:
            self.sock.connect(path)
            self._auth()
            self.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "Hello", [])
        except OSError as exc:
            self.close()
            raise SleepGuardError(f"the system bus is not reachable ({exc.strerror or exc})") from exc

    def _auth(self) -> None:
        uid = str(os.getuid()).encode().hex()  # type: ignore[attr-defined, unused-ignore]
        self.sock.sendall(b"\x00AUTH EXTERNAL " + uid.encode() + b"\r\n")
        if not self._line().startswith(b"OK "):
            raise SleepGuardError("the system bus refused this process")
        self.sock.sendall(b"NEGOTIATE_UNIX_FD\r\n")
        if not self._line().startswith(b"AGREE_UNIX_FD"):
            raise SleepGuardError("the system bus cannot pass a lock")
        self.sock.sendall(b"BEGIN\r\n")

    def _line(self) -> bytes:
        while b"\r\n" not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise SleepGuardError("the system bus closed the connection")
            self.buffer += chunk
        line, _, self.buffer = self.buffer.partition(b"\r\n")
        return line

    def _receive(self, size: int) -> None:
        fds = array.array("i")
        space = socket.CMSG_LEN(16 * fds.itemsize)  # type: ignore[attr-defined, unused-ignore]
        data, ancillary, _flags, _addr = self.sock.recvmsg(size, space)  # type: ignore[attr-defined, unused-ignore]
        for level, kind, payload in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:  # type: ignore[attr-defined, unused-ignore]
                fds.frombytes(payload[: len(payload) - (len(payload) % fds.itemsize)])
        self.fds.extend(fds)
        if not data:
            raise SleepGuardError("the system bus closed the connection")
        self.buffer += data

    def call(self, destination: str, path: str, interface: str, member: str, args: list[str]) -> dict[str, Any]:
        self.serial += 1
        serial = self.serial
        self.sock.sendall(method_call(serial, destination, path, interface, member, args))
        while True:
            while len(self.buffer) < 16:
                self._receive(4096)
            (fields_len,) = struct.unpack("<I", self.buffer[12:16])
            while len(self.buffer) < 16 + fields_len:
                self._receive(4096)
            header = parse_header(self.buffer)
            while len(self.buffer) < header["length"]:
                self._receive(65536)
            self.buffer = self.buffer[header["length"] :]
            if header.get("replySerial") != serial:
                for fd in self.fds[: header["fdCount"]]:  # a signal or another reply: not ours
                    os.close(fd)
                del self.fds[: header["fdCount"]]
                continue
            if header["type"] == 3:
                raise SleepGuardError(str(header.get("error") or "the call was refused"))
            received = self.fds[: header["fdCount"]]
            del self.fds[: header["fdCount"]]
            return header | {"fds": received}

    def close(self) -> None:
        for fd in self.fds:
            os.close(fd)
        self.fds = []
        self.sock.close()


class SleepGuard:
    """Hold while transferring. ``acquire`` returns what it could take; ``release`` lets go."""

    def __init__(self, bus_path: str = SYSTEM_BUS, platform: str = sys.platform) -> None:
        self.bus_path = bus_path
        self.platform = platform
        self.fds: list[int] = []
        self.windows = False
        self.problem: str | None = None

    @property
    def held(self) -> bool:
        return bool(self.fds) or self.windows

    def acquire(self, why: str = "Copying a game between your devices") -> bool:
        if self.held:
            return True
        try:
            if self.platform.startswith("win"):
                import ctypes  # Windows only; Decky's frozen Python may not bundle it (ADR-0030)

                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined, unused-ignore]
                if not kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
                    raise SleepGuardError("Windows refused to stay awake")
                self.windows = True
            else:
                bus = Bus(self.bus_path)
                try:
                    for what, mode in (("idle", "block"), ("sleep", "delay")):
                        reply = bus.call(
                            "org.freedesktop.login1",
                            "/org/freedesktop/login1",
                            "org.freedesktop.login1.Manager",
                            "Inhibit",
                            [what, "Keepsake", why, mode],
                        )
                        self.fds.extend(reply["fds"][:1])
                finally:
                    bus.close()
            self.problem = None
        except (SleepGuardError, OSError, ImportError, AttributeError) as exc:
            self.problem = f"the device may sleep during a transfer: {exc}"
        return self.held

    def release(self) -> None:
        for fd in self.fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self.fds = []
        if self.windows:
            try:
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # type: ignore[attr-defined, unused-ignore]
            except (ImportError, AttributeError, OSError):
                pass
            self.windows = False
