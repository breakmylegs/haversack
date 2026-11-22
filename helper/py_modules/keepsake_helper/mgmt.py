"""The kernel's Bluetooth management and monitor channels, without btmgmt or btmon (ADR-0083).

- **SSP** (Secure Simple Pairing) on or off: MGMT command Set Secure Simple Pairing (opcode
  0x000B) on ``HCI_CHANNEL_CONTROL``; Read Controller Information (0x0004) for the current
  settings. Needs CAP_NET_ADMIN, which is why this is in the root helper.
- **HCI capture**: ``HCI_CHANNEL_MONITOR`` for a bounded time, written as a btsnoop file
  (datalink 2001, as btmon writes it), so it opens in Wireshark and btmon.

A ``sockaddr_hci`` names a channel. CPython's ``bind`` takes ``(device, channel)`` for HCI
sockets on recent versions; otherwise ctypes calls ``bind`` itself (imported only then, ADR-0030).
"""

from __future__ import annotations

import socket
import struct
import time
from collections.abc import Callable
from typing import Any

AF_BLUETOOTH = 31
BTPROTO_HCI = 1
HCI_DEV_NONE = 0xFFFF
CHANNEL_MONITOR, CHANNEL_CONTROL = 2, 3
OP_READ_INFO, OP_SET_POWERED, OP_SET_SSP = 0x0004, 0x0005, 0x000B
EV_COMPLETE, EV_STATUS = 0x0001, 0x0002
SETTING_POWERED, SETTING_SSP = 0x01, 0x40
STATUS = {0x00: "ok", 0x0A: "busy", 0x0B: "rejected", 0x0C: "not supported", 0x0D: "invalid", 0x11: "invalid index"}
BTSNOOP_EPOCH = 0x00DCDDB30F2F8000  # microseconds from year 0 to 1970, as btsnoop counts
MAX_CAPTURE = 8 * 1024 * 1024
MAX_SECONDS = 60


class MgmtError(Exception):
    pass


def _bind(sock: Any, channel: int) -> None:
    try:
        sock.bind((HCI_DEV_NONE, channel))
        return
    except (TypeError, OSError):
        pass
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    address = struct.pack("<HHH", AF_BLUETOOTH, HCI_DEV_NONE, channel)
    if libc.bind(sock.fileno(), address, len(address)) != 0:
        raise MgmtError(f"the Bluetooth channel could not be opened (errno {ctypes.get_errno()})")


def open_channel(channel: int) -> Any:
    sock = socket.socket(AF_BLUETOOTH, socket.SOCK_RAW | getattr(socket, "SOCK_CLOEXEC", 0), BTPROTO_HCI)
    try:
        _bind(sock, channel)
    except Exception:
        sock.close()
        raise
    return sock


Opener = Callable[[int], Any]


def command(sock: Any, opcode: int, index: int, params: bytes = b"", timeout: float = 3.0) -> bytes:
    """Send one MGMT command and return its Command Complete parameters (after the status)."""
    sock.settimeout(timeout)
    sock.send(struct.pack("<HHH", opcode, index, len(params)) + params)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = sock.recv(1024)
        if len(data) < 6:
            continue
        event, event_index, length = struct.unpack("<HHH", data[:6])
        body = data[6 : 6 + length]
        if event_index != index or event not in (EV_COMPLETE, EV_STATUS) or len(body) < 3:
            continue
        answered, status = struct.unpack("<HB", body[:3])
        if answered != opcode:
            continue
        if status != 0:
            raise MgmtError(STATUS.get(status, f"status 0x{status:02X}"))
        if event == EV_STATUS:
            continue  # a Command Status of success: the Command Complete follows
        return bytes(body[3:])
    raise MgmtError("the controller did not answer")


def settings(index: int, opener: Opener = open_channel) -> int:
    sock = opener(CHANNEL_CONTROL)
    try:
        info = command(sock, OP_READ_INFO, index)
    finally:
        sock.close()
    # address(6) version(1) manufacturer(2) supported(4) current(4)
    return int(struct.unpack("<I", info[13:17])[0])


def set_ssp(index: int, on: bool, opener: Opener = open_channel, power_cycle: bool = False) -> dict[str, Any]:
    """Turn SSP on or off; returns the settings after. With ``power_cycle``, a "rejected" while
    powered is retried with the adapter off (the caller has made sure nothing is connected)."""
    sock = opener(CHANNEL_CONTROL)
    try:
        try:
            reply = command(sock, OP_SET_SSP, index, bytes([1 if on else 0]))
        except MgmtError as exc:
            if str(exc) not in ("rejected", "busy") or not power_cycle:
                return {"ok": False, "problem": str(exc), "needsPowerCycle": str(exc) in ("rejected", "busy")}
            command(sock, OP_SET_POWERED, index, b"\x00")
            try:
                command(sock, OP_SET_SSP, index, bytes([1 if on else 0]))
            finally:
                reply = command(sock, OP_SET_POWERED, index, b"\x01")  # its reply is the settings after
        current = int(struct.unpack("<I", reply[:4])[0]) if len(reply) >= 4 else settings(index, opener)
    finally:
        sock.close()
    return {
        "ok": bool(current & SETTING_SSP) == on,
        "ssp": bool(current & SETTING_SSP),
        "powered": bool(current & SETTING_POWERED),
    }


def capture(seconds: float, opener: Opener = open_channel, clock: Callable[[], float] = time.time) -> bytes:
    """A btsnoop file of every HCI packet for ``seconds`` (at most 60 s and 8 MB)."""
    seconds = max(1.0, min(float(seconds), MAX_SECONDS))
    out = bytearray(b"btsnoop\x00" + struct.pack(">II", 1, 2001))
    sock = opener(CHANNEL_MONITOR)
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and len(out) < MAX_CAPTURE:
            sock.settimeout(max(0.05, min(1.0, deadline - time.monotonic())))
            try:
                data = sock.recv(65536)
            except TimeoutError:
                continue
            if len(data) < 6:
                continue
            opcode, index, length = struct.unpack("<HHH", data[:6])
            payload = data[6 : 6 + length]
            stamp = int(clock() * 1_000_000) + BTSNOOP_EPOCH
            flags = (index << 16) | opcode
            out += struct.pack(">IIIIQ", len(payload), len(payload), flags, 0, stamp) + payload
    finally:
        sock.close()
    return bytes(out[:MAX_CAPTURE])
