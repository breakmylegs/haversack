"""Cable pairing providers for controller reconnect help (R22 reads, R23 writes; ADR-0082).

A controller family with a USB pairing protocol is a provider. A provider is picked from the USB
device's vendor and product, then the identity it reads over USB must match the Bluetooth device
the user chose, or nothing more happens. Clones copy vendor and product IDs, so a match only
says which protocol to try, never which device this is.

This release reads only (the stored host, "Read stored host over USB"). Writing a pairing also
needs BlueZ's key file changed and bluetoothd restarted, which is root work for the helper
(R23); the write steps are here so the helper and the tests share one definition.

Providers:
- DualShock 4 (Sony 054C, DS4 product IDs): feature reports 0x12, 0x13 and 0x14, BlueZ key type 4.
- DualShock 3 and DualSense: candidates, not built until their formats are verified.
"""

from __future__ import annotations

import glob
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .reconnect import normal_mac

BUS_USB, BUS_BLUETOOTH = 0x0003, 0x0005
_HID_ID = re.compile(r"^HID_ID=([0-9A-F]{4}):([0-9A-F]{8}):([0-9A-F]{8})$", re.IGNORECASE | re.MULTILINE)
_HID_UNIQ = re.compile(r"^HID_UNIQ=(.*)$", re.MULTILINE)
NOT_SUPPORTED = "Cable pairing is not supported for this controller."


class CableError(Exception):
    pass


@dataclass(frozen=True)
class HidNode:
    node: str
    bus: str  # "usb", "bluetooth" or "other"
    vendor: str
    product: str
    address: str | None  # HID_UNIQ: the Bluetooth address, where the kernel shows one


def hid_nodes(sys_root: str = "/sys", dev_root: str = "/dev") -> list[HidNode]:
    """Every hidraw node with its bus, vendor, product and address, from sysfs."""
    found = []
    for folder in sorted(glob.glob(os.path.join(sys_root, "class", "hidraw", "hidraw*"))):
        try:
            with open(os.path.join(folder, "device", "uevent"), encoding="utf-8", errors="replace") as handle:
                text = handle.read(4096)
        except OSError:
            continue
        ids = _HID_ID.search(text)
        if not ids:
            continue
        bus = int(ids.group(1), 16)
        uniq = _HID_UNIQ.search(text)
        found.append(
            HidNode(
                node=f"{dev_root.rstrip('/')}/{os.path.basename(folder)}",  # a device path, always POSIX
                bus="usb" if bus == BUS_USB else "bluetooth" if bus == BUS_BLUETOOTH else "other",
                vendor=ids.group(2)[-4:].upper(),
                product=ids.group(3)[-4:].upper(),
                address=normal_mac(uniq.group(1)) if uniq else None,
            )
        )
    return found


# Feature report I/O. fcntl is imported where it is used (ADR-0030).
Get = Callable[[str, int, int], bytes]
Set = Callable[[str, bytes], None]


def _ioc(nr: int, length: int) -> int:
    # _IOC(_IOC_WRITE | _IOC_READ, 'H', nr, len): HIDIOCSFEATURE is nr 0x06, HIDIOCGFEATURE nr 0x07.
    return (3 << 30) | (length << 16) | (ord("H") << 8) | nr


def get_feature(path: str, report_id: int, length: int) -> bytes:
    import fcntl

    buffer = bytearray(length)
    buffer[0] = report_id
    fd = os.open(path, os.O_RDWR | getattr(os, "O_NONBLOCK", 0))
    try:
        fcntl.ioctl(fd, _ioc(0x07, length), buffer, True)  # type: ignore[attr-defined, unused-ignore]
    finally:
        os.close(fd)
    return bytes(buffer)


def set_feature(path: str, data: bytes) -> None:
    import fcntl

    buffer = bytearray(data)
    fd = os.open(path, os.O_RDWR | getattr(os, "O_NONBLOCK", 0))
    try:
        fcntl.ioctl(fd, _ioc(0x06, len(buffer)), buffer, True)  # type: ignore[attr-defined, unused-ignore]
    finally:
        os.close(fd)


def _le(raw: bytes) -> str:
    return ":".join(f"{b:02X}" for b in reversed(raw))


def _le_bytes(mac: str) -> bytes:
    return bytes(reversed(bytes.fromhex(mac.replace(":", ""))))


class Provider:
    """One controller family's USB pairing protocol."""

    family = ""
    key_type = 0

    def matches(self, node: HidNode) -> bool:
        raise NotImplementedError

    def read_identity(self, node: HidNode, get: Get = get_feature) -> dict[str, str | None]:
        """``{"controller": its own address, "host": the host it will call, or None}``."""
        raise NotImplementedError

    def write_pairing(self, node: HidNode, host: str, key: bytes, put: Set = set_feature) -> None:
        raise NotImplementedError

    def commit(self, node: HidNode, put: Set = set_feature) -> None:
        raise NotImplementedError

    def verify(self, node: HidNode, host: str, get: Get = get_feature) -> bool:
        return self.read_identity(node, get).get("host") == normal_mac(host)

    def full_report(self, node: HidNode, get: Get = get_feature) -> None:
        """Ask for full input reports over Bluetooth, where the family needs it. Most do not."""


class DualShock4(Provider):
    family = "DualShock 4"
    key_type = 4  # BlueZ's [LinkKey] Type for this family's cable pairing (BlueZ issue 2678)
    VENDOR = "054C"
    PRODUCTS = frozenset({"05C4", "09CC"})  # DS4 and DS4 slim; clones copy them
    PAIRING, PAIRING_LEN = 0x12, 16  # [1..6] controller, [10..15] stored host, little-endian
    SET_PAIRING, SET_LEN = 0x13, 23  # [1..6] host, [7..22] link key
    COMMIT, COMMIT_LEN = 0x14, 17  # [1] = 0x02
    FULL, FULL_LEN = 0x02, 37  # read over Bluetooth: clones switch to the full input report

    def matches(self, node: HidNode) -> bool:
        return node.vendor == self.VENDOR and node.product in self.PRODUCTS

    def read_identity(self, node: HidNode, get: Get = get_feature) -> dict[str, str | None]:
        report = get(node.node, self.PAIRING, self.PAIRING_LEN)
        if len(report) < self.PAIRING_LEN or report[0] != self.PAIRING:
            raise CableError("the controller's pairing report has the wrong layout")
        controller = normal_mac(_le(report[1:7]))
        if controller is None:
            raise CableError("the controller reported no address of its own")
        return {"controller": controller, "host": normal_mac(_le(report[10:16]))}

    def write_pairing(self, node: HidNode, host: str, key: bytes, put: Set = set_feature) -> None:
        address = normal_mac(host)
        if address is None or len(key) != 16:
            raise CableError("a pairing needs the host's address and a 16-byte key")
        put(node.node, bytes([self.SET_PAIRING]) + _le_bytes(address) + key)

    def commit(self, node: HidNode, put: Set = set_feature) -> None:
        put(node.node, bytes([self.COMMIT, 0x02]) + bytes(self.COMMIT_LEN - 2))

    def full_report(self, node: HidNode, get: Get = get_feature) -> None:
        get(node.node, self.FULL, self.FULL_LEN)


PROVIDERS: list[Provider] = [DualShock4()]


def provider_for(node: HidNode) -> Provider | None:
    return next((p for p in PROVIDERS if p.matches(node)), None)


def read_stored_host(selected: str, nodes: list[HidNode], get: Get = get_feature) -> dict[str, Any]:
    """ "Read stored host over USB" for the device the user chose.

    Every USB controller with a provider is read; only one whose own address matches ``selected``
    counts. A provider match with a different address is reported as a mismatch, and nothing is
    done with it.
    """
    mac = normal_mac(selected)
    usb = [(n, provider_for(n)) for n in nodes if n.bus == "usb"]
    candidates = [(n, p) for n, p in usb if p is not None]
    if not usb:
        return {"ok": False, "state": "no-usb", "message": "Connect the controller with a USB data cable first."}
    if not candidates:
        return {"ok": False, "state": "unsupported", "message": NOT_SUPPORTED}
    problems = []
    for node, provider in candidates:
        try:
            identity = provider.read_identity(node, get)
        except PermissionError:
            problems.append("permission")
            continue
        except (OSError, CableError):
            problems.append("unreadable")
            continue
        if identity["controller"] == mac:
            return {"ok": True, "state": "read", "family": provider.family, **identity}
        problems.append("mismatch")
    if "mismatch" in problems:
        return {
            "ok": False,
            "state": "mismatch",
            "message": "The controller on the cable is a different one from the device you chose. Nothing was changed.",
        }
    if "permission" in problems:
        return {
            "ok": False,
            "state": "permission",
            "message": "Haversack may not read this controller over USB without root. The root helper "
            "(next release) can.",
        }
    return {"ok": False, "state": "unreadable", "message": "The controller did not answer over USB."}


def full_report(selected: str, enabled: bool, nodes: list[HidNode], get: Get = get_feature) -> bool:
    """Ask a helped device on Bluetooth for full reports, where its provider needs it. Returns
    whether a read happened. ``enabled`` is the user's rule: nothing happens without it."""
    mac = normal_mac(selected)
    if not enabled or mac is None:
        return False
    for node in nodes:
        provider = provider_for(node)
        if node.bus == "bluetooth" and node.address == mac and provider is not None:
            try:
                provider.full_report(node, get)
                return True
            except OSError:
                return False
    return False
