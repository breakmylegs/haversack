"""Whether this device has a system battery (ADR-0049, R2).

Living-room machines such as a Steam Machine or a desktop PC run on mains power:
battery rules do not apply to them, and Advisor leaves out battery estimates and,
without a device profile, TDP advice.

- Linux: ``/sys/class/power_supply/*/type`` is ``Battery`` for a system battery. A
  battery with ``scope`` ``Device`` belongs to a peripheral, such as a controller, and
  does not count.
- Windows: ``GetSystemPowerStatus``. ``BatteryFlag`` 128 means no system battery, 255 unknown.

Returns True, False, or None when it cannot tell (fail closed: callers treat None as
"may have a battery").
"""

from __future__ import annotations

import glob
import os
import sys
from collections.abc import Callable


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def linux_battery(root: str = "/") -> bool | None:
    base = os.path.join(root, "sys", "class", "power_supply")
    if not os.path.isdir(base):
        return None
    for supply in sorted(glob.glob(os.path.join(base, "*"))):
        if _read(os.path.join(supply, "type")) == "Battery" and _read(os.path.join(supply, "scope")) != "Device":
            return True
    return False


def windows_battery_flag() -> int | None:
    import ctypes  # Windows only

    class SystemPowerStatus(ctypes.Structure):
        _fields_ = [  # noqa: RUF012 - the ctypes structure layout, read by ctypes itself
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    status = SystemPowerStatus()
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined, unused-ignore]
    if not kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return None
    return int(status.BatteryFlag)


def from_battery_flag(flag: int | None) -> bool | None:
    if flag is None or flag == 255:
        return None
    return flag != 128


def battery_present(
    root: str = "/", platform: str = sys.platform, flag_reader: Callable[[], int | None] | None = None
) -> bool | None:
    if platform.startswith("win"):
        try:
            return from_battery_flag((flag_reader or windows_battery_flag)())
        except (OSError, AttributeError):
            return None
    return linux_battery(root)
