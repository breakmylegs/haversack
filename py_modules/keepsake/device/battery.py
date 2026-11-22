"""The battery charge limit (R21 stage 4, ADR-0077), through steamos-manager only (ADR-0075 tier 0).

Lenovo's firmware offers one limit on the Legion Go and Go 2: charging stops at 80 percent
("Long Life"; BIOS v29 and later). The kernel shows it as the battery's ``charge_types``
(``Standard`` or ``Long_Life``, kernel 7.2 and later), which only root can write. steamos-manager's
``BatteryChargeLimit1`` can set it without root where Valve's device file enables it. Where it
does not, Keepsake shows the current state and says where to change it (Steam's own settings or
the desktop's power settings), and writes nothing.
"""

from __future__ import annotations

import glob
import os
from typing import Any

from .steamos import ManagerError, SteamOSManager

LIMIT = 80  # the only limit the Legion firmware offers


def _text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(256).strip()
    except OSError:
        return None


def firmware_state(sys_root: str = "/sys") -> dict[str, Any]:
    """What the kernel says, read-only: the charge type or a threshold, from the system battery."""
    for supply in sorted(glob.glob(os.path.join(sys_root, "class", "power_supply", "*"))):
        if _text(os.path.join(supply, "type")) != "Battery" or _text(os.path.join(supply, "scope")) == "Device":
            continue
        types = _text(os.path.join(supply, "charge_types"))
        threshold = _text(os.path.join(supply, "charge_control_end_threshold"))
        active = None
        if types:
            # The kernel marks the chosen type in brackets: "[Standard] Long_Life".
            chosen = next(
                (w.strip("[]") for w in types.split() if w.startswith("[")), types.split()[0] if types else ""
            )
            active = chosen == "Long_Life"
        elif threshold and threshold.isdigit():
            active = int(threshold) < 100
        return {
            "battery": os.path.basename(supply),
            "chargeTypes": types,
            "threshold": int(threshold) if threshold and threshold.isdigit() else None,
            "limited": active,
        }
    return {"battery": None, "chargeTypes": None, "threshold": None, "limited": None}


def status(manager: SteamOSManager, sys_root: str = "/sys") -> dict[str, Any]:
    firmware = firmware_state(sys_root)
    try:
        offered = manager.read().get("chargeLimit")
        problem = None
    except ManagerError as exc:
        offered, problem = None, str(exc)
    if offered is not None:
        limited = 0 < offered["value"] < 100
        return {"control": "steamos-manager", "limited": limited, "level": offered["value"], "firmware": firmware}
    return {
        "control": None,
        "limited": firmware["limited"],
        "level": firmware["threshold"],
        "firmware": firmware,
        "problem": problem,
        "where": "Change it in Steam's settings, Power, or in Desktop Mode's power settings.",
    }


def set_limit(manager: SteamOSManager, on: bool, sys_root: str = "/sys") -> dict[str, Any]:
    """Turn the 80 percent limit on or off through steamos-manager, read back. Refuses where it is not offered."""
    current = status(manager, sys_root)
    if current["control"] != "steamos-manager":
        raise ManagerError("this device's steamos-manager does not offer the charge limit; " + current["where"])
    manager.set_charge_limit(LIMIT if on else -1)
    return status(manager, sys_root)
