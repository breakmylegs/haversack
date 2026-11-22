"""Fan control: profiles and the loop that follows them (R24, ADR-0085).

The Keepsake Helper does the root part: the Go 2's EC override under a lease, the Go 1's full fan
speed, the self-test and the 101 °C failsafe. Keepsake chooses the speed:

- **profiles** are named curves; one is the default, and one can be chosen per performance mode
  and per game (a game's choice wins, then the mode's, then the default);
- **the loop** reads the temperature every 2 seconds (world-readable sensors), runs the curve
  through the hysteresis controller and sends the speed to the helper only when it changes, with a
  lease of 10 seconds renewed every tick, so the fan goes back to the firmware within seconds if
  Keepsake stops;
- **after sleep** (the wall clock jumps against the monotonic one) the speed is sent again, as the
  firmware may have dropped it;
- **never fight**: when another fan tool is installed or running, Keepsake only shows the readings.

Settings live in ``fan-profiles.json`` on this device only.
"""

from __future__ import annotations

import glob
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from ..fsutil import atomic_write_json, read_json
from . import fancurve
from .helper import HelperClient, HelperError

INTERVAL = 2.0
LEASE = 10.0
MAX_PROFILES = 12
FAN_PLUGINS = {
    "LeGo2-Fan-Control": "LeGo2 Fan Control",
    "Legion-Go-1-Fan-Control": "Legion Go 1 Fan Control",
    "LegionGoRemapper": "LegionGoRemapper",
    "legion-center": "Legion Center",
    "legion-decky": "Legion Decky",
    "LeGo-decky-toolbox": "Legion Go Toolbox",
    "lgo-toolbox": "Legion Go Toolbox",
    "LegionGo2Companion": "LegionGo2Companion",
    "PowerControl": "PowerControl",
}
MODES = ("low-power", "balanced", "performance", "custom")
DEVICE_KEYS = (
    "model",
    "rpm",
    "override",
    "firmware",
    "validated",
    "conflicts",
    "acpiCall",
    "fullSpeedAttribute",
    "problem",
    "controlling",
    "temperature",
)


class FanSettingsError(ValueError):
    pass


def fan_tools(home: str, proc_root: str = "/proc") -> list[str]:
    found = []
    for folder in sorted(glob.glob(os.path.join(home, "homebrew", "plugins", "*"))):
        label = FAN_PLUGINS.get(os.path.basename(folder))
        if label and label not in found:
            found.append(label)
    for comm in glob.glob(os.path.join(proc_root, "[0-9]*", "comm")):
        try:
            with open(comm, encoding="utf-8", errors="replace") as handle:
                if handle.read(64).strip() == "hhd" and "Handheld Daemon" not in found:
                    found.append("Handheld Daemon")
        except OSError:
            continue
    return found


def temperature(sys_root: str = "/sys") -> float | None:
    best = None
    for folder in glob.glob(os.path.join(sys_root, "class", "hwmon", "hwmon*")):
        try:
            with open(os.path.join(folder, "name"), encoding="utf-8") as handle:
                name = handle.read(32).strip()
            if name not in ("k10temp", "amdgpu"):
                continue
            with open(os.path.join(folder, "temp1_input"), encoding="utf-8") as handle:
                value = int(handle.read(16).strip()) / 1000
        except (OSError, ValueError):
            continue
        best = value if best is None else max(best, value)
    return best


def platform_mode(sys_root: str = "/sys") -> str | None:
    for folder in sorted(glob.glob(os.path.join(sys_root, "class", "platform-profile", "platform-profile-*"))):
        try:
            with open(os.path.join(folder, "profile"), encoding="utf-8") as handle:
                return handle.read(32).strip()
        except OSError:
            continue
    return None


class FanStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        with self.lock:
            data = read_json(self.path, default={})
        data = data if isinstance(data, dict) else {}
        unlocked = bool(data.get("unlocked"))
        profiles: dict[str, list[tuple[int, int]]] = {}
        for name, points in dict(data.get("profiles") or {}).items():
            try:
                profiles[str(name)[:32]] = fancurve.clean([tuple(p) for p in points], unlocked)
            except (fancurve.CurveError, TypeError):
                continue
        if not profiles:
            profiles = {"Balanced": list(fancurve.DEFAULT), "Quiet": list(fancurve.QUIET), "Cool": list(fancurve.COOL)}
        default = data.get("default") if data.get("default") in profiles else next(iter(profiles))
        return {
            "enabled": bool(data.get("enabled")),
            "fullSpeed": bool(data.get("fullSpeed")),  # the Legion Go's full fan speed
            "unlocked": unlocked,
            "smooth": data.get("smooth", True) is not False,
            "profiles": profiles,
            "default": default,
            "modes": {m: n for m, n in dict(data.get("modes") or {}).items() if m in MODES and n in profiles},
            "games": {
                str(int(a)): n for a, n in dict(data.get("games") or {}).items() if str(a).isdigit() and n in profiles
            },
        }

    def save(self, data: dict[str, Any]) -> None:
        serial = {**data, "profiles": {k: [list(p) for p in v] for k, v in data["profiles"].items()}}
        with self.lock:
            atomic_write_json(self.path, serial)


class Fans:
    """The loop runs in its own thread; every method here is safe to call from a worker thread."""

    def __init__(
        self,
        store: FanStore,
        helper: HelperClient,
        tools: Callable[[], list[str]],
        sys_root: str = "/sys",
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.store, self.helper, self.tools, self.sys_root = store, helper, tools, sys_root
        self.clock, self.wall = clock, wall
        self.game: int | None = None
        self.controller: fancurve.Controller | None = None
        self.profile_name: str | None = None
        self.sent: int | None = None
        self.last: tuple[float, float] | None = None  # (monotonic, wall) at the last tick
        self.problem: str | None = None
        self.model: str | None = None  # from the helper, once
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    # Settings

    def settings(self) -> dict[str, Any]:
        return self.store.load()

    def _update(self, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        data = self.store.load()
        change(data)
        self.store.save(data)
        self.controller = None  # pick up the new curve on the next tick
        return data

    def save_profile(self, name: str, points: Any, make_default: bool = False) -> dict[str, Any]:
        label = str(name or "").strip()[:32]
        if not label:
            raise FanSettingsError("give the profile a name")

        def change(data: dict[str, Any]) -> None:
            curve = fancurve.clean([tuple(p) for p in points] if isinstance(points, list) else points, data["unlocked"])
            if label not in data["profiles"] and len(data["profiles"]) >= MAX_PROFILES:
                raise FanSettingsError(f"at most {MAX_PROFILES} profiles")
            data["profiles"][label] = curve
            if make_default:
                data["default"] = label

        try:
            return self._update(change)
        except fancurve.CurveError as exc:
            raise FanSettingsError(str(exc)) from exc

    def delete_profile(self, name: str) -> dict[str, Any]:
        def change(data: dict[str, Any]) -> None:
            if name not in data["profiles"] or len(data["profiles"]) == 1:
                raise FanSettingsError("that profile cannot be removed")
            del data["profiles"][name]
            data["modes"] = {m: n for m, n in data["modes"].items() if n != name}
            data["games"] = {g: n for g, n in data["games"].items() if n != name}
            if data["default"] == name:
                data["default"] = next(iter(data["profiles"]))

        return self._update(change)

    def assign(self, kind: str, key: str, name: str | None) -> dict[str, Any]:
        def change(data: dict[str, Any]) -> None:
            if name is not None and name not in data["profiles"]:
                raise FanSettingsError("there is no profile with that name")
            table = {"mode": "modes", "game": "games"}.get(kind)
            slot = str(int(key)) if kind == "game" and str(key).isdigit() else str(key)
            if kind == "default" and name:
                data["default"] = name
            elif table and (slot in MODES if kind == "mode" else slot.isdigit()):
                if name is None:
                    data[table].pop(slot, None)
                else:
                    data[table][slot] = name
            else:
                raise FanSettingsError("assign to the default, a mode or a game")

        return self._update(change)

    def set_options(
        self,
        smooth: bool | None = None,
        unlocked: bool | None = None,
        enabled: bool | None = None,
        full_speed: bool | None = None,
    ) -> dict[str, Any]:
        def change(data: dict[str, Any]) -> None:
            if enabled is not None:
                data["enabled"] = bool(enabled)
            if full_speed is not None:
                data["fullSpeed"] = bool(full_speed)
            if smooth is not None:
                data["smooth"] = bool(smooth)
            if unlocked is not None:
                data["unlocked"] = bool(unlocked)
                if not unlocked:  # back inside the safe limits: curves beyond them return to the presets' shape
                    for key, curve in list(data["profiles"].items()):
                        try:
                            fancurve.clean(curve, False)
                        except fancurve.CurveError:
                            data["profiles"][key] = [(t, min(r, fancurve.MAX_RPM)) for t, r in curve]

        return self._update(change)

    # The loop

    def choose(self, data: dict[str, Any]) -> str:
        if self.game is not None and str(self.game) in data["games"]:
            return str(data["games"][str(self.game)])
        mode = platform_mode(self.sys_root)
        if mode in data["modes"]:
            return str(data["modes"][mode])
        return str(data["default"])

    def _model(self) -> str | None:
        if self.model is None:
            try:
                self.model = self.helper.call("fan.status", timeout=5.0).get("model")
            except HelperError as exc:
                self.problem = str(exc)
        return self.model

    def _go1(self, data: dict[str, Any]) -> int | None:
        """The Legion Go: only full fan speed, held by a renewed lease."""
        try:
            if data["fullSpeed"]:
                if self.sent is None:
                    self.helper.call("fan.full", on=True, lease=LEASE)
                    self.sent = -1  # full speed
                else:
                    self.helper.call("fan.renew", lease=LEASE)
            elif self.sent is not None:
                self.release()
            self.problem = None
        except HelperError as exc:
            self.problem, self.sent = str(exc), None
        return self.sent

    def tick(self) -> int | None:
        """One step: returns the speed sent (or None). Raises nothing: problems are kept for the screen."""
        data = self.store.load()
        if not data["enabled"] and not data["fullSpeed"]:
            if self.sent is not None:
                self.release()  # switched off: back to the firmware now
            return None
        tools = self.tools()
        if tools:
            self.problem = f"{', '.join(tools)} controls the fan here; Keepsake only shows it"
            return None
        if self._model() == "go1":
            return self._go1(data)
        if not data["enabled"]:
            return None
        temp = temperature(self.sys_root)
        if temp is None:
            self.problem = "no temperature sensor was found"
            return None
        name = self.choose(data)
        if self.controller is None or name != self.profile_name:
            self.controller = fancurve.Controller(data["profiles"][name], smooth=data["smooth"])
            self.profile_name, self.sent = name, None
        now, wall = self.clock(), self.wall()
        resumed = self.last is not None and (wall - self.last[1]) - (now - self.last[0]) > 5.0
        self.last = (now, wall)
        rpm = self.controller.update(temp, now)
        try:
            if rpm != self.sent or resumed:
                self.helper.call("fan.set", rpm=rpm, lease=LEASE)
                self.sent = rpm
            else:
                self.helper.call("fan.renew", lease=LEASE)
            self.problem = None
        except HelperError as exc:
            self.problem = str(exc)
            self.sent = None
            return None
        return rpm

    def release(self) -> None:
        self.sent, self.controller = None, None
        try:
            self.helper.call("fan.release")
        except HelperError as exc:
            self.problem = str(exc)

    def start(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, name="keepsake-fans", daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3.0)
        self.thread = None
        if self.sent is not None:
            self.release()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            was = self.sent
            self.tick()
            data = self.store.load()
            if was is not None and self.sent is not None and not (data["enabled"] or data["fullSpeed"]):
                self.release()
            self.stop_event.wait(INTERVAL)

    def status(self) -> dict[str, Any]:
        data = self.store.load()
        helper = self.helper.status()
        found: dict[str, Any] = {}
        if helper.get("ready"):
            try:
                found = self.helper.call("fan.status", timeout=5.0)
            except HelperError as exc:
                found = {"problem": str(exc)}
        return {
            "helper": {k: helper.get(k) for k in ("installed", "ready", "problem")},
            "temperature": temperature(self.sys_root),
            "mode": platform_mode(self.sys_root),
            "device": {k: found.get(k) for k in DEVICE_KEYS},
            "tools": self.tools(),
            "settings": {**data, "profiles": {k: [list(p) for p in v] for k, v in data["profiles"].items()}},
            "active": self.profile_name if data["enabled"] else None,
            "target": self.sent,
            "problem": self.problem,
            "limits": {
                "min": fancurve.MIN_RPM,
                "max": fancurve.UNLOCKED_MAX if data["unlocked"] else fancurve.MAX_RPM,
                "failsafe": fancurve.FAILSAFE_C,
            },
        }
