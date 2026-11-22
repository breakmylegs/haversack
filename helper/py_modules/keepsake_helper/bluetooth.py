"""BlueZ's stored pairing for one device, and bluetoothd stopped and started around a change (ADR-0083).

The only files written: ``/var/lib/bluetooth/<ADAPTER>/<DEVICE>/info`` and its backups next to it
(``info.keepsake-<time>``). Paths are built from validated addresses, never taken from a caller,
and must resolve inside ``/var/lib/bluetooth`` with no symbolic link on the way. Writes are
atomic, root-owned, mode 0600. bluetoothd is stopped and started through systemd over D-Bus,
and always started again, whatever fails in between.
"""

from __future__ import annotations

import glob
import os
import re
import secrets
import time
from collections.abc import Callable
from typing import Any

from . import keyfile

ROOT = "/var/lib/bluetooth"
UNIT = "bluetooth.service"
SYSTEMD = "org.freedesktop.systemd1"
MAX_BACKUPS = 5
_MAC = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")


class BluetoothError(Exception):
    pass


def mac(value: Any) -> str:
    text = str(value or "").upper()
    if not _MAC.match(text) or text in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
        raise BluetoothError("not a Bluetooth address")
    return text


def folder_name(address: str) -> str:
    """The folder BlueZ names after an address (the tests swap this on Windows, which forbids colons)."""
    return address


def info_path(adapter: str, device: str, root: str = ROOT) -> str:
    base = os.path.realpath(root)
    path = os.path.join(base, folder_name(mac(adapter)), folder_name(mac(device)), "info")
    if os.path.realpath(path) != path:  # a symbolic link somewhere on the way
        raise BluetoothError("the pairing file is not where BlueZ keeps it")
    return path


def state(adapter: str, device: str, root: str = ROOT) -> dict[str, Any]:
    """Whether a record, a key and the service cache exist. The key itself is never returned."""
    path = info_path(adapter, device, root)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read(65536)
    except FileNotFoundError:
        return {"record": False, "linkKey": False, "keyType": None, "trusted": False, "cache": False, "backups": 0}
    link = keyfile.get_values(text, "LinkKey")
    cache = os.path.exists(os.path.join(root, folder_name(mac(adapter)), "cache", folder_name(mac(device))))
    return {
        "record": True,
        "linkKey": bool(link.get("Key")),
        "keyType": int(link["Type"]) if link.get("Type", "").isdigit() else None,
        "trusted": keyfile.get_values(text, "General").get("Trusted") == "true",
        "cache": cache,
        "services": "ServiceRecords" in text or cache,
        "backups": len(backups(adapter, device, root)),
    }


def backups(adapter: str, device: str, root: str = ROOT) -> list[str]:
    return sorted(glob.glob(info_path(adapter, device, root) + ".keepsake-*"))


def _write(path: str, data: bytes) -> None:
    folder = os.path.dirname(path)
    temp = os.path.join(folder, f".info.{secrets.token_hex(6)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(temp, flags, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
        if hasattr(os, "fchown"):
            os.fchown(fd, 0, 0)
    finally:
        os.close(fd)
    os.replace(temp, path)


class Systemd:
    """bluetooth.service through systemd's manager on the system bus."""

    def __init__(self, connect: Callable[[], Any], timeout: float = 15.0) -> None:
        self.connect = connect
        self.timeout = timeout

    def _active(self, conn: Any) -> str:
        (unit,) = conn.call(SYSTEMD, "/org/freedesktop/systemd1", f"{SYSTEMD}.Manager", "LoadUnit", "s", [UNIT])
        (value,) = conn.call(
            SYSTEMD, unit, "org.freedesktop.DBus.Properties", "Get", "ss", [f"{SYSTEMD}.Unit", "ActiveState"]
        )
        return str(value[1] if isinstance(value, tuple) else value)

    def _go(self, verb: str, want: str) -> None:
        conn = self.connect()
        try:
            conn.call(SYSTEMD, "/org/freedesktop/systemd1", f"{SYSTEMD}.Manager", verb, "ss", [UNIT, "replace"])
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                if self._active(conn) == want:
                    return
                time.sleep(0.2)
        finally:
            conn.close()
        raise BluetoothError(f"bluetoothd did not become {want}")

    def stop(self) -> None:
        self._go("StopUnit", "inactive")

    def start(self) -> None:
        self._go("StartUnit", "active")


def _around_restart(systemd: Any, work: Callable[[], Any]) -> Any:
    systemd.stop()
    try:
        return work()
    finally:
        systemd.start()


def install(
    adapter: str,
    device: str,
    key: bytes,
    key_type: int,
    systemd: Any,
    root: str = ROOT,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Back up the info file, install the key and Trusted, keep everything else. Needs the record."""
    path = info_path(adapter, device, root)
    if not os.path.exists(path):
        raise BluetoothError("BlueZ has no record for this device: connect it once in pairing mode first")

    def work() -> dict[str, Any]:
        with open(path, "rb") as handle:
            before = handle.read()
        backup = f"{path}.keepsake-{time.strftime('%Y%m%dT%H%M%S', time.gmtime(clock()))}"
        _write(backup, before)
        for old in backups(adapter, device, root)[:-MAX_BACKUPS]:
            os.remove(old)
        after = keyfile.install_key(before.decode("utf-8"), key, key_type).encode("utf-8")
        _write(path, after)
        return {"backup": os.path.basename(backup)}

    return dict(_around_restart(systemd, work))


def restore(adapter: str, device: str, systemd: Any, root: str = ROOT) -> dict[str, Any]:
    """Put back the newest backup."""
    path = info_path(adapter, device, root)
    found = backups(adapter, device, root)
    if not found:
        raise BluetoothError("there is no backup to restore")

    def work() -> dict[str, Any]:
        with open(found[-1], "rb") as handle:
            _write(path, handle.read())
        return {"restored": os.path.basename(found[-1])}

    return dict(_around_restart(systemd, work))
