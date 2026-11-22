"""Feature reports to a controller on USB, for cable pairing only (ADR-0083).

Only hidraw nodes on USB whose vendor and product are in a cable pairing provider's list, and only
that provider's reports: for the DualShock 4, GET 0x12 (16 bytes), SET 0x13 (23 bytes) and SET
0x14 02 (17 bytes). The node is checked in sysfs each time, so a caller cannot point it elsewhere.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

PROVIDERS = {("054C", "05C4"), ("054C", "09CC")}  # DualShock 4 and its slim; clones copy them
GETS = {0x12: 16}
SETS = {0x13: 23, 0x14: 17}
_NODE = re.compile(r"^/dev/(hidraw\d{1,3})$")
_HID_ID = re.compile(r"^HID_ID=([0-9A-F]{4}):([0-9A-F]{8}):([0-9A-F]{8})$", re.IGNORECASE | re.MULTILINE)


class HidError(Exception):
    pass


def check_node(node: Any, sys_root: str = "/sys") -> str:
    """The node, if it is a USB controller with a cable pairing provider."""
    found = _NODE.match(str(node or ""))
    if not found:
        raise HidError("not a hidraw node")
    try:
        with open(
            os.path.join(sys_root, "class", "hidraw", found.group(1), "device", "uevent"), encoding="utf-8"
        ) as handle:
            ids = _HID_ID.search(handle.read(4096))
    except OSError as exc:
        raise HidError("the controller is not connected") from exc
    if (
        not ids
        or int(ids.group(1), 16) != 0x0003
        or (ids.group(2)[-4:].upper(), ids.group(3)[-4:].upper()) not in PROVIDERS
    ):
        raise HidError("cable pairing is not supported for this device")
    return str(node)


def _ioc(nr: int, length: int) -> int:
    return (3 << 30) | (length << 16) | (ord("H") << 8) | nr


def _ioctl(node: str, request: int, buffer: bytearray) -> None:
    import fcntl

    fd = os.open(node, os.O_RDWR | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        fcntl.ioctl(fd, request, buffer, True)  # type: ignore[attr-defined, unused-ignore]
    finally:
        os.close(fd)


Ioctl = Callable[[str, int, bytearray], None]


def get_feature(node: Any, report: Any, sys_root: str = "/sys", ioctl: Ioctl = _ioctl) -> bytes:
    path = check_node(node, sys_root)
    if not isinstance(report, int) or report not in GETS:
        raise HidError("that report is not allowed")
    buffer = bytearray(GETS[report])
    buffer[0] = report
    ioctl(path, _ioc(0x07, len(buffer)), buffer)
    return bytes(buffer)


def set_feature(node: Any, data: bytes, sys_root: str = "/sys", ioctl: Ioctl = _ioctl) -> None:
    path = check_node(node, sys_root)
    if not data or data[0] not in SETS or len(data) != SETS[data[0]] or (data[0] == 0x14 and data[1] != 0x02):
        raise HidError("that report is not allowed")
    ioctl(path, _ioc(0x06, len(data)), bytearray(data))
