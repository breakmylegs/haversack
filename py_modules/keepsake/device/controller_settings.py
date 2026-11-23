"""The Legion controllers' own settings and stick lights (R24, ADR-0086).

The kernel's hid-lenovo-go attributes are world-readable, so Keepsake reads them itself; writing
needs root and goes through the Keepsake Helper, which checks every value, writes the stick lights
in the driver's safe order and reads everything back.

Settings the user chooses to keep are applied again when the controller comes back (a reconnect,
a resume, a reboot), because the controller may not keep them. Never fight another tool:
- with Handheld Daemon running, everything is read-only (it drives the same controller interface);
- InputPlumber rewrites ``os_mode``, the gyro bypass and touchpad vibration on every reconnect, so
  those are left to it where it is installed.
"""

from __future__ import annotations

import glob
import os
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from ..fsutil import atomic_write_json, read_json
from .helper import HelperClient, HelperError

LED = "go:rgb:joystick_rings"
KEYS = (
    "mode",
    "os_mode",
    "rumble_intensity",
    "fps_mode_dpi",
    "left_handle/auto_sleep_time",
    "right_handle/auto_sleep_time",
    "left_handle/imu_enabled",
    "left_handle/rumble_mode",
    "right_handle/rumble_mode",
    "touchpad/enabled",
    "touchpad/vibration_enabled",
    "touchpad/vibration_intensity",
    "led/enabled",
    "led/mode",
    "led/effect",
    "led/profile",
    "led/speed",
    "led/brightness",
    "led/multi_intensity",
)
INPUTPLUMBER_KEYS = ("os_mode", "touchpad/vibration_enabled")  # it rewrites these on every bind
WATCH_SECONDS = 10.0
_HID = re.compile(r"[:_]17EF[:_]61E[B-E]\.[0-9A-F]{4}$", re.IGNORECASE)  # "_" only for tests on Windows


class SettingsError(ValueError):
    pass


def device_dir(sys_root: str = "/sys") -> str | None:
    led = os.path.join(sys_root, "class", "leds", LED)
    if os.path.exists(led):
        parent = os.path.dirname(os.path.dirname(os.path.realpath(led)))
        if os.path.exists(os.path.join(parent, "mode")):
            return parent
    for folder in sorted(glob.glob(os.path.join(sys_root, "bus", "hid", "devices", "*"))):
        if _HID.search(os.path.basename(folder)) and os.path.exists(os.path.join(folder, "mode")):
            return os.path.realpath(folder)
    return None


def read(sys_root: str = "/sys") -> dict[str, str] | None:
    base = device_dir(sys_root)
    if base is None:
        return None
    out = {}
    for key in KEYS:
        path = (
            os.path.join(sys_root, "class", "leds", LED, key[4:])
            if key.startswith("led/")
            else os.path.join(base, *key.split("/"))
        )
        try:
            with open(path, encoding="ascii", errors="replace") as handle:
                out[key] = handle.read(128).strip()
        except OSError:
            continue
    return out


def others(
    home: str, proc_root: str = "/proc", rules_roots: tuple[str, ...] = ("/usr/lib/udev/rules.d", "/etc/udev/rules.d")
) -> dict[str, bool]:
    """Which other controller tools are here: Handheld Daemon running, InputPlumber installed."""
    hhd = inputplumber = False
    for comm in glob.glob(os.path.join(proc_root, "[0-9]*", "comm")):
        try:
            with open(comm, encoding="utf-8", errors="replace") as handle:
                name = handle.read(64).strip()
        except OSError:
            continue
        hhd = hhd or name == "hhd"
        inputplumber = inputplumber or name == "inputplumber"
    for root in rules_roots:
        inputplumber = inputplumber or os.path.exists(os.path.join(root, "99-inputplumber-device-setup.rules"))
    return {"hhd": hhd, "inputplumber": inputplumber}


class ControllerSettings:
    def __init__(
        self,
        store_path: str,
        helper: HelperClient,
        tools: Callable[[], dict[str, bool]],
        sys_root: str = "/sys",
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.store_path, self.helper, self.tools, self.sys_root = store_path, helper, tools, sys_root
        self.clock, self.wall = clock, wall
        self.present = False
        self.last: tuple[float, float] | None = None
        self.problem: str | None = None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def kept(self) -> dict[str, Any]:
        data = read_json(self.store_path, default={})
        values = data.get("kept") if isinstance(data, dict) else None
        return {k: v for k, v in dict(values or {}).items() if k in KEYS}

    def allowed(self) -> list[str]:
        found = self.tools()
        if found.get("hhd"):
            return []
        return [k for k in KEYS if not (found.get("inputplumber") and k in INPUTPLUMBER_KEYS)]

    def status(self) -> dict[str, Any]:
        found = self.tools()
        return {
            "present": device_dir(self.sys_root) is not None,
            "current": read(self.sys_root),
            "kept": self.kept(),
            "allowed": self.allowed(),
            "tools": found,
            "helper": {k: self.helper.status().get(k) for k in ("installed", "ready", "problem")},
            "problem": self.problem,
        }

    def set(self, values: Any, keep: bool) -> dict[str, Any]:
        if not isinstance(values, dict) or not values:
            raise SettingsError("give the settings to change")
        allowed = set(self.allowed())
        refused = [k for k in values if k not in allowed]
        if refused:
            raise SettingsError(
                "Handheld Daemon manages the controller here; Haversack only shows it"
                if not allowed
                else f"another tool manages {', '.join(refused)}"
            )
        try:
            done = self.helper.call("ctrl.set", values=values)
        except HelperError as exc:
            raise SettingsError(str(exc)) from exc
        if keep:
            kept = {**self.kept(), **dict(done.get("settings") or {})}
            atomic_write_json(self.store_path, {"kept": kept})
        return dict(done.get("settings") or {})

    def forget(self) -> None:
        atomic_write_json(self.store_path, {"kept": {}})

    def tick(self) -> bool:
        """Re-apply the kept settings when the controller appears again or the device has slept."""
        now, wall = self.clock(), self.wall()
        slept = self.last is not None and (wall - self.last[1]) - (now - self.last[0]) > 5.0
        self.last = (now, wall)
        present = device_dir(self.sys_root) is not None
        came_back = present and (not self.present or slept)
        self.present = present
        kept = {k: v for k, v in self.kept().items() if k in set(self.allowed())}
        if not came_back or not kept:
            return False
        try:
            self.helper.call("ctrl.set", values=kept)
            self.problem = None
            return True
        except HelperError as exc:
            self.problem = str(exc)
            return False

    def start(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, name="keepsake-controller", daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3.0)
        self.thread = None

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.tick()
            self.stop_event.wait(WATCH_SECONDS)
