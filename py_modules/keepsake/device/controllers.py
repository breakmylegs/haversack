"""The Legion controllers, read-only (R21 stage 5, ADR-0078; ADR-0075 tier 0).

What the kernel shows to any user:
- each controller's battery: power-supply entries with scope ``Device``;
- the controllers' own settings: the ``hid-lenovo-go`` driver (kernel 7.1 and later) for USB
  17EF:61EB to 61EE, with its mode, rumble, auto-sleep, gyro and touchpad attributes;
- the stick rings' RGB: the LED class ``go:rgb:joystick_rings``.

Changing any of these needs root (the attributes are 0644 root), which is ADR-0075 tier 1 and
waits for the owner's decision. Remapping, dead zones and gyro are Steam Input's job already.
Nothing here writes.
"""

from __future__ import annotations

import glob
import os
import re
from typing import Any

CONTROLLER_IDS = re.compile(r":17EF:61E[B-E]\.", re.IGNORECASE)
TOP = ("mode", "os_mode", "rumble_intensity", "fps_mode_dpi", "firmware_version", "hardware_version")
HANDLE = ("imu_enabled", "auto_sleep_time", "rumble_mode")
TOUCHPAD = ("enabled", "vibration_enabled", "vibration_intensity")
LED = ("brightness", "max_brightness", "effect", "mode", "profile", "speed", "enabled", "multi_intensity")
TOOLS = {"inputplumber": "InputPlumber", "hhd": "Handheld Daemon"}


def _text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(256).strip()
    except OSError:
        return None


def _read(folder: str, names: tuple[str, ...]) -> dict[str, str]:
    out = {}
    for name in names:
        value = _text(os.path.join(folder, name))
        if value is not None:
            out[name] = value[:80]
    return out


def batteries(sys_root: str = "/sys") -> list[dict[str, Any]]:
    """Each controller's battery: power supplies with scope Device (never the system battery)."""
    found = []
    for supply in sorted(glob.glob(os.path.join(sys_root, "class", "power_supply", "*"))):
        if _text(os.path.join(supply, "type")) != "Battery" or _text(os.path.join(supply, "scope")) != "Device":
            continue
        capacity = _text(os.path.join(supply, "capacity"))
        found.append(
            {
                "name": (_text(os.path.join(supply, "model_name")) or os.path.basename(supply))[:60],
                "percent": int(capacity) if capacity and capacity.isdigit() else None,
                "level": _text(os.path.join(supply, "capacity_level")),
                "status": _text(os.path.join(supply, "status")),
            }
        )
    return found


def controllers(sys_root: str = "/sys") -> list[dict[str, Any]]:
    """The hid-lenovo-go devices and their settings, as the driver shows them."""
    found = []
    for device in sorted(glob.glob(os.path.join(sys_root, "bus", "hid", "devices", "*"))):
        if not CONTROLLER_IDS.search(os.path.basename(device)) or not os.path.exists(os.path.join(device, "mode")):
            continue
        found.append(
            {
                "id": os.path.basename(device).split(".")[0],
                "settings": _read(device, TOP),
                "left": _read(os.path.join(device, "left_handle"), HANDLE),
                "right": _read(os.path.join(device, "right_handle"), HANDLE),
                "touchpad": _read(os.path.join(device, "touchpad"), TOUCHPAD),
            }
        )
    return found


def rings(sys_root: str = "/sys") -> dict[str, str] | None:
    # Joined by hand: on Windows (tests), os.path.join would read "*:" as a drive and drop the folder.
    for led in sorted(glob.glob(os.path.join(sys_root, "class", "leds") + os.sep + "*:rgb:joystick_rings")):
        return {"name": os.path.basename(led), **_read(led, LED)}
    return None


def tools(proc_root: str = "/proc") -> list[str]:
    found = []
    for comm in glob.glob(os.path.join(proc_root, "[0-9]*", "comm")):
        label = TOOLS.get(_text(comm) or "")
        if label and label not in found:
            found.append(label)
    return sorted(found)


def status(sys_root: str = "/sys", proc_root: str = "/proc") -> dict[str, Any]:
    return {
        "batteries": batteries(sys_root),
        "controllers": controllers(sys_root),
        "rings": rings(sys_root),
        "tools": tools(proc_root),
    }
