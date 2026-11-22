"""The Legion controllers' own settings and stick lights, through the kernel's hid-lenovo-go driver (ADR-0086).

Only the attributes in ``ALLOWED``, each with the values the driver accepts (from its source; its
ABI document has typos). Not offered: the resets (destructive, and ``right_handle/reset`` resets
the left controller), calibration, and ``right_handle/imu_enabled`` (it switches IMU bypass, a
driver bug).

The driver reports success even when the controller does not answer, and reads may briefly return
the old value, so every write is read back for up to 250 ms. For the stick lights, the profile is
read first (until it is known, the driver sends colour writes to the profile command) and the
speed is written last (the driver's remembered speed can invert after a read).
"""

from __future__ import annotations

import glob
import os
import re
import time
from collections.abc import Callable
from typing import Any

LED_NAME = "go:rgb:joystick_rings"
ON_OFF = ("true", "false")
LEVELS = ("off", "low", "medium", "high")
RUMBLE_MODES = ("fps", "racing", "standard", "spg", "rpg")
ALLOWED: dict[str, Any] = {
    "mode": ("xinput", "dinput"),
    "os_mode": ("windows", "linux"),
    "rumble_intensity": LEVELS,
    "fps_mode_dpi": ("500", "800", "1200", "1800"),
    "left_handle/auto_sleep_time": range(0, 256),
    "right_handle/auto_sleep_time": range(0, 256),
    "left_handle/imu_enabled": ON_OFF,
    "left_handle/rumble_mode": RUMBLE_MODES,
    "right_handle/rumble_mode": RUMBLE_MODES,
    "touchpad/enabled": ON_OFF,
    "touchpad/vibration_enabled": ON_OFF,
    "touchpad/vibration_intensity": LEVELS,
    "led/enabled": ON_OFF,
    "led/mode": ("custom",),  # "dynamic" is a Windows sync mode that does nothing on Linux
    "led/effect": ("monocolor", "breathe", "chroma", "rainbow"),
    "led/profile": range(1, 4),
    "led/speed": range(0, 101),
    "led/brightness": range(0, 101),
    "led/multi_intensity": "rgb",
}
# Write order: the profile before anything else on the light, the speed after everything.
ORDER = ["led/profile", "led/enabled", "led/mode", "led/effect", "led/brightness", "led/multi_intensity"]
LAST = ["led/speed"]
_RGB = re.compile(r"^(\d{1,3}) (\d{1,3}) (\d{1,3})$")
_HID = re.compile(r"[:_]17EF[:_]61E[B-E]\.[0-9A-F]{4}$", re.IGNORECASE)  # "_" only for tests on Windows


class ControllerError(Exception):
    pass


def device_dir(sys_root: str = "/sys") -> str | None:
    """The HID device that carries the settings: from the light's symlink, else the first 61EB to 61EE
    device with a ``mode`` file."""
    led = os.path.join(sys_root, "class", "leds", LED_NAME)
    if os.path.exists(led):
        real = os.path.realpath(led)
        parent = os.path.dirname(os.path.dirname(real))  # <hid>/leds/<name>
        if os.path.exists(os.path.join(parent, "mode")):
            return parent
    for folder in sorted(glob.glob(os.path.join(sys_root, "bus", "hid", "devices", "*"))):
        if _HID.search(os.path.basename(folder)) and os.path.exists(os.path.join(folder, "mode")):
            return os.path.realpath(folder)
    return None


def path_for(base: str, sys_root: str, key: str) -> str:
    if key.startswith("led/"):
        return os.path.join(sys_root, "class", "leds", LED_NAME, key[4:])
    return os.path.join(base, *key.split("/"))


def normal(key: str, value: Any) -> str:
    """The value as the driver wants it, or ControllerError."""
    allowed = ALLOWED.get(key)
    if allowed is None:
        raise ControllerError("that setting may not be changed")
    if allowed == "rgb":
        parts = value if isinstance(value, (list, tuple)) else str(value).split()
        if len(parts) != 3 or not all(str(p).isdigit() and 0 <= int(p) <= 100 for p in parts):
            raise ControllerError("a colour is three numbers from 0 to 100")
        return " ".join(str(int(p)) for p in parts)
    if isinstance(allowed, range):
        if isinstance(value, bool) or not str(value).isdigit() or int(value) not in allowed:
            raise ControllerError(f"{key} must be {allowed.start} to {allowed.stop - 1}")
        return str(int(value))
    text = str(value).lower() if isinstance(value, bool) else str(value)
    if text not in allowed:
        raise ControllerError(f"{key} must be one of {', '.join(allowed)}")
    return text


def _read(path: str) -> str:
    with open(path, encoding="ascii", errors="replace") as handle:
        return handle.read(128).strip()


def read(sys_root: str = "/sys") -> dict[str, Any]:
    base = device_dir(sys_root)
    if base is None:
        raise ControllerError("no Legion controller with the hid-lenovo-go driver (kernel 7.1 and later)")
    out: dict[str, str] = {}
    for key in ALLOWED:
        path = path_for(base, sys_root, key)
        try:
            out[key] = _read(path)
        except OSError:
            continue
    return {"settings": out}


def _same(key: str, got: str, wanted: str) -> bool:
    if ALLOWED[key] == "rgb":
        found = _RGB.match(got)
        return found is not None and " ".join(found.groups()) == wanted
    return got == wanted


def apply(
    values: Any,
    sys_root: str = "/sys",
    sleep: Callable[[float], None] = time.sleep,
    tries: int = 6,
) -> dict[str, Any]:
    """Write ``values`` in the driver's safe order and read each back. All are checked before any write."""
    if not isinstance(values, dict) or not values:
        raise ControllerError("give the settings to change")
    base = device_dir(sys_root)
    if base is None:
        raise ControllerError("no Legion controller with the hid-lenovo-go driver (kernel 7.1 and later)")
    wanted = {key: normal(key, value) for key, value in values.items()}
    if any(k.startswith("led/") for k in wanted) and "led/profile" not in wanted:
        try:  # the driver must learn the profile before any other write to the light
            _read(path_for(base, sys_root, "led/profile"))
        except OSError as exc:
            raise ControllerError("the stick lights' profile could not be read") from exc
    keys = (
        [k for k in ORDER if k in wanted]
        + [k for k in wanted if k not in ORDER + LAST]
        + [k for k in LAST if k in wanted]
    )
    done: dict[str, str] = {}
    for key in keys:
        path = path_for(base, sys_root, key)
        with open(path, "w", encoding="ascii") as handle:
            handle.write(wanted[key])
        for attempt in range(tries):
            got = _read(path)
            if _same(key, got, wanted[key]):
                break
            if attempt == tries - 1:
                raise ControllerError(f"the controller did not keep {key} (it reads {got!r})")
            sleep(0.05)
        done[key] = wanted[key]
    return {"settings": done}
