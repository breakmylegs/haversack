"""A small D-Bus client and object server for the tray, in pure Python (ADR-0068).

Just what a StatusNotifierItem and its menu need on the session bus: the wire format for every
basic and container type (little-endian), SASL EXTERNAL sign-in, method calls with replies,
incoming method calls answered with returns or errors, and signals. No binary and no library
(P9). Values: a variant is ``(signature, value)``, a struct a tuple, an array a list, a dict a dict.
"""

from __future__ import annotations

import os
import socket
import struct
from collections.abc import Callable
from typing import Any

MAX_MESSAGE = 1 << 20
CALL, RETURN, ERROR, SIGNAL = 1, 2, 3, 4
NO_REPLY = 0x1
_FIXED = {"y": ("B", 1), "b": ("I", 4), "n": ("h", 2), "q": ("H", 2), "i": ("i", 4), "u": ("I", 4)}
_FIXED |= {"x": ("q", 8), "t": ("Q", 8), "d": ("d", 8), "h": ("I", 4)}
_ALIGN = {**{k: v[1] for k, v in _FIXED.items()}, "s": 4, "o": 4, "g": 1, "a": 4, "(": 8, "{": 8, "v": 1}
FIELDS = {1: "o", 2: "s", 3: "s", 4: "s", 5: "u", 6: "s", 7: "s", 8: "g", 9: "u"}
FIELD_NAMES = {1: "path", 2: "interface", 3: "member", 4: "error", 5: "replySerial", 6: "destination", 7: "sender"}
FIELD_NAMES[8] = "signature"


class DBusError(Exception):
    pass


def split(signature: str) -> list[str]:
    """Complete types in a signature: ``"sa{sv}(ii)"`` gives ``["s", "a{sv}", "(ii)"]``."""
    out, at = [], 0
    while at < len(signature):
        end = _one(signature, at)
        out.append(signature[at:end])
        at = end
    return out


def _one(signature: str, at: int) -> int:
    if at >= len(signature):
        raise DBusError("incomplete signature")
    code = signature[at]
    if code == "a":
        return _one(signature, at + 1)
    if code in "({":
        close, depth, i = ")" if code == "(" else "}", 0, at
        while i < len(signature):
            if signature[i] in "({":
                depth += 1
            elif signature[i] in ")}":
                depth -= 1
                if depth == 0:
                    if signature[i] != close:
                        raise DBusError("mismatched brackets")
                    return i + 1
            i += 1
        raise DBusError("unclosed bracket")
    if code in _ALIGN:
        return at + 1
    raise DBusError(f"unknown type {code!r}")


class Writer:
    def __init__(self) -> None:
        self.data = bytearray()

    def pad(self, boundary: int) -> None:
        self.data.extend(b"\x00" * (-len(self.data) % boundary))

    def write(self, kind: str, value: Any) -> None:
        code = kind[0]
        if code in _FIXED:
            fmt, size = _FIXED[code]
            self.pad(size)
            self.data.extend(struct.pack("<" + fmt, int(bool(value)) if code == "b" else value))
        elif code in "so":
            raw = str(value).encode("utf-8")
            self.pad(4)
            self.data.extend(struct.pack("<I", len(raw)) + raw + b"\x00")
        elif code == "g":
            raw = str(value).encode()
            self.data.extend(bytes([len(raw)]) + raw + b"\x00")
        elif code == "v":
            inner, item = value
            self.write("g", inner)
            self.write(inner, item)
        elif code == "a":
            item_kind = kind[1:]
            self.pad(4)
            at = len(self.data)
            self.data.extend(b"\x00\x00\x00\x00")
            self.pad(_ALIGN[item_kind[0]])
            start = len(self.data)
            items = value.items() if item_kind[0] == "{" else value
            for item in items:
                self.write(item_kind, item)
            struct.pack_into("<I", self.data, at, len(self.data) - start)
        elif code in "({":
            self.pad(8)
            for part, item in zip(split(kind[1:-1]), value, strict=True):
                self.write(part, item)
        else:
            raise DBusError(f"cannot write {kind}")


class Reader:
    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data, self.at = data, offset

    def align(self, boundary: int) -> None:
        self.at += -self.at % boundary

    def take(self, size: int) -> bytes:
        if self.at + size > len(self.data):
            raise DBusError("truncated message")
        chunk = self.data[self.at : self.at + size]
        self.at += size
        return chunk

    def read(self, kind: str, depth: int = 0) -> Any:
        if depth > 32:
            raise DBusError("too deeply nested")
        code = kind[0]
        if code in _FIXED:
            fmt, size = _FIXED[code]
            self.align(size)
            (value,) = struct.unpack("<" + fmt, self.take(size))
            return bool(value) if code == "b" else value
        if code in "so":
            self.align(4)
            (length,) = struct.unpack("<I", self.take(4))
            raw = self.take(length + 1)
            return raw[:-1].decode("utf-8", "replace")
        if code == "g":
            length = self.take(1)[0]
            return self.take(length + 1)[:-1].decode()
        if code == "v":
            inner = self.read("g")
            if len(split(inner)) != 1:
                raise DBusError("a variant holds one type")
            return (inner, self.read(inner, depth + 1))
        if code == "a":
            item_kind = kind[1:]
            self.align(4)
            (length,) = struct.unpack("<I", self.take(4))
            if length > MAX_MESSAGE:
                raise DBusError("array too long")
            self.align(_ALIGN[item_kind[0]])
            end = self.at + length
            items = []
            while self.at < end:
                items.append(self.read(item_kind, depth + 1))
            return dict(items) if item_kind[0] == "{" else items
        if code in "({":
            self.align(8)
            return tuple(self.read(part, depth + 1) for part in split(kind[1:-1]))
        raise DBusError(f"cannot read {kind}")


def marshal(signature: str, values: list[Any]) -> bytes:
    writer = Writer()
    for kind, value in zip(split(signature), values, strict=True):
        writer.write(kind, value)
    return bytes(writer.data)


def unmarshal(signature: str, data: bytes) -> list[Any]:
    reader = Reader(data)
    return [reader.read(kind) for kind in split(signature)]


def message(
    kind: int, serial: int, fields: dict[int, Any], signature: str = "", body: list[Any] | None = None, flags: int = 0
) -> bytes:
    payload = marshal(signature, body or []) if signature else b""
    if signature:
        fields = {**fields, 8: signature}
    header = Writer()
    header.data.extend(b"l" + bytes([kind, flags, 1]) + struct.pack("<II", len(payload), serial))
    header.write("a(yv)", [(code, (FIELDS[code], value)) for code, value in sorted(fields.items())])
    header.pad(8)
    return bytes(header.data) + payload


def parse(data: bytes) -> tuple[dict[str, Any], int] | None:
    """One message from the start of ``data``: ``(message, length)``, or None if more bytes are needed."""
    if len(data) < 16:
        return None
    if data[0:1] != b"l":
        raise DBusError("only little-endian messages are read")
    body_len, serial, fields_len = struct.unpack("<III", data[4:16])
    if body_len > MAX_MESSAGE or fields_len > MAX_MESSAGE:
        raise DBusError("message too large")
    header_end = 16 + fields_len + (-(16 + fields_len) % 8)
    total = header_end + body_len
    if len(data) < total:
        return None
    reader = Reader(data[: 16 + fields_len], 12)
    fields = reader.read("a(yv)")
    out: dict[str, Any] = {"type": data[1], "flags": data[2], "serial": serial}
    for code, (_sig, value) in fields:
        if code in FIELD_NAMES:
            out[FIELD_NAMES[code]] = value
    signature = out.get("signature", "")
    out["body"] = unmarshal(signature, data[header_end:total]) if signature else []
    return out, total


Handler = Callable[[dict[str, Any]], tuple[str, list[Any]] | None]


class Connection:
    """A session bus connection: calls, replies, signals, and incoming calls handed to ``handler``."""

    def __init__(self, address: str | None = None, timeout: float = 5.0) -> None:
        path = session_socket(address)
        if path is None:
            raise DBusError("no session bus: Haversack's tray needs a desktop session")
        if not hasattr(socket, "AF_UNIX"):
            raise DBusError("this system has no D-Bus socket support")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined, unused-ignore]
        self.sock.settimeout(timeout)
        if path.startswith("\0"):
            self.sock.connect(path)
        else:
            self.sock.connect(path)
        self.serial = 0
        self.buffer = b""
        self.pending: list[dict[str, Any]] = []
        self._auth()
        self.name = self.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "Hello")[0]

    def _auth(self) -> None:
        uid = str(os.getuid()).encode().hex()  # type: ignore[attr-defined, unused-ignore]
        self.sock.sendall(b"\x00AUTH EXTERNAL " + uid.encode() + b"\r\n")
        line = b""
        while not line.endswith(b"\r\n"):
            chunk = self.sock.recv(256)
            if not chunk:
                raise DBusError("the session bus closed the connection")
            line += chunk
        if not line.startswith(b"OK "):
            raise DBusError("the session bus refused this process")
        self.sock.sendall(b"BEGIN\r\n")

    def send(self, data: bytes) -> None:
        self.sock.sendall(data)

    def next_serial(self) -> int:
        self.serial += 1
        return self.serial

    def receive(self) -> dict[str, Any]:
        while True:
            parsed = parse(self.buffer)
            if parsed is not None:
                found, length = parsed
                self.buffer = self.buffer[length:]
                return found
            chunk = self.sock.recv(65536)
            if not chunk:
                raise DBusError("the session bus closed the connection")
            self.buffer += chunk

    def call(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str = "",
        body: list[Any] | None = None,
    ) -> list[Any]:
        serial = self.next_serial()
        fields = {1: path, 2: interface, 3: member, 6: destination}
        self.send(message(CALL, serial, fields, signature, body))
        while True:
            found = self.receive()
            if found.get("replySerial") == serial and found["type"] in (RETURN, ERROR):
                if found["type"] == ERROR:
                    raise DBusError(f"{found.get('error')}: {found['body'][0] if found['body'] else ''}")
                return list(found["body"])
            self.pending.append(found)  # an incoming call or signal while waiting: kept for the loop

    def signal(
        self, path: str, interface: str, member: str, signature: str = "", body: list[Any] | None = None
    ) -> None:
        self.send(message(SIGNAL, self.next_serial(), {1: path, 2: interface, 3: member}, signature, body))

    def answer(self, call: dict[str, Any], result: tuple[str, list[Any]] | None, error: str | None = None) -> None:
        if call.get("flags", 0) & NO_REPLY:
            return
        fields: dict[int, Any] = {5: call["serial"]}
        if call.get("sender"):
            fields[6] = call["sender"]
        if error is not None:
            self.send(message(ERROR, self.next_serial(), {**fields, 4: error}, "s", [error]))
        else:
            signature, body = result or ("", [])
            self.send(message(RETURN, self.next_serial(), fields, signature, body))

    def close(self) -> None:
        self.sock.close()


def session_socket(address: str | None = None) -> str | None:
    """The session bus socket path from ``DBUS_SESSION_BUS_ADDRESS``, else ``$XDG_RUNTIME_DIR/bus``."""
    address = address if address is not None else os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    for part in address.split(";"):
        if part.startswith("unix:"):
            options = dict(kv.split("=", 1) for kv in part[5:].split(",") if "=" in kv)
            if "path" in options:
                return options["path"]
            if "abstract" in options:
                return "\0" + options["abstract"]
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    candidate = os.path.join(runtime, "bus") if runtime else ""
    return candidate if candidate and os.path.exists(candidate) else None
