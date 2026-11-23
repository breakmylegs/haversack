"""Per-game performance profiles (R21 stage 2, ADR-0076), through steamos-manager only (ADR-0075 tier 0).

A profile is a performance mode, a TDP limit and CPU boost, each optional. Starting a game
applies its profile; quitting it puts back what was there before, but only values that still
hold what Keepsake set (never undoing a later change by Steam or the user). After resume the
profile is applied again, because the firmware resets Custom on a mode change.

Never fight another tool: when another TDP tool is installed or running, or something changes a
value Keepsake set, Keepsake stops applying until the next game start and says which tool it was.
"""

from __future__ import annotations

import glob
import os
import threading
from collections.abc import Callable
from typing import Any

from ..fsutil import atomic_write_json, read_json
from .powerlimits import LimitsError, PowerLimits
from .powerlimits import clean as clean_limits
from .steamos import ManagerError, SteamOSManager

MAX_GAMES = 500
# Other tools that write TDP or the performance mode themselves, by Decky plugin folder.
TDP_PLUGINS = {
    "SimpleDeckyTDP": "SimpleDeckyTDP",
    "PowerControl": "PowerControl",
    "LegionGo2Companion": "LegionGo2Companion",
    "LeGoTDP": "LeGoTDP",
    "LeGo-decky-toolbox": "Legion Go Toolbox",
    "lgo-toolbox": "Legion Go Toolbox",
    "legion-center": "Legion Center",
    "LegionGoRemapper": None,  # remaps controllers and sets fans; it does not set TDP
}


class ProfileError(ValueError):
    pass


def clean_profile(value: Any) -> dict[str, Any]:
    """A profile from the page or the file: unknown fields dropped, types checked."""
    if not isinstance(value, dict):
        raise ProfileError("that is not a profile")
    out: dict[str, Any] = {}
    mode = value.get("mode")
    if mode is not None:
        if not isinstance(mode, str) or not mode.replace("-", "").isalpha() or len(mode) > 32:
            raise ProfileError("that performance mode is not valid")
        out["mode"] = mode
    tdp = value.get("tdp")
    if tdp is not None:
        if not isinstance(tdp, int) or isinstance(tdp, bool) or not 1 <= tdp <= 120:
            raise ProfileError("that TDP is not valid")
        out["tdp"] = tdp
    boost = value.get("boost")
    if boost is not None:
        if not isinstance(boost, bool):
            raise ProfileError("CPU boost is on or off")
        out["boost"] = boost
    limits = value.get("limits")
    if limits is not None:
        try:
            out["limits"] = clean_limits(limits)
        except LimitsError as exc:
            raise ProfileError(str(exc)) from exc
    return out


class ProfileStore:
    """Per-game profiles on this device only, by Steam app ID (never sent anywhere)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            data = read_json(self.path, default={})
        games = data.get("games") if isinstance(data, dict) else None
        out = {}
        for key, value in (games or {}).items() if isinstance(games, dict) else []:
            try:
                out[str(int(key))] = clean_profile(value)
            except (ProfileError, ValueError):
                continue
        return out

    def get(self, appid: int) -> dict[str, Any] | None:
        return self._load().get(str(int(appid)))

    def all(self) -> dict[str, dict[str, Any]]:
        return self._load()

    def set(self, appid: int, profile: dict[str, Any] | None) -> None:
        games = self._load()
        if profile:
            if str(int(appid)) not in games and len(games) >= MAX_GAMES:
                raise ProfileError(f"Haversack keeps up to {MAX_GAMES} game profiles; forget one first")
            games[str(int(appid))] = clean_profile(profile)
        else:
            games.pop(str(int(appid)), None)
        with self._lock:
            atomic_write_json(self.path, {"version": 1, "games": games})


def other_tools(home: str, proc_root: str = "/proc") -> list[str]:
    """Tools that set TDP or the mode themselves, so Keepsake must not: installed plugins, running hhd."""
    found = []
    plugins = os.path.join(home, "homebrew", "plugins")
    for folder in sorted(glob.glob(os.path.join(plugins, "*"))):
        label = TDP_PLUGINS.get(os.path.basename(folder))
        if label and os.path.isdir(folder) and label not in found:
            found.append(label)
    for comm in glob.glob(os.path.join(proc_root, "[0-9]*", "comm")):
        try:
            with open(comm, encoding="utf-8", errors="replace") as handle:
                name = handle.read(64).strip()
        except OSError:
            continue
        if name == "hhd" and "Handheld Daemon" not in found:
            found.append("Handheld Daemon")
    return found


class Performance:
    """Applies and restores profiles. Every method blocks briefly (D-Bus): call it from a worker thread."""

    def __init__(
        self,
        store: ProfileStore,
        manager: SteamOSManager,
        tools: Callable[[], list[str]],
        limits: Callable[[], dict[str, int]],
        power: PowerLimits | None = None,
    ) -> None:
        self.power = power  # separate SPL, SPPT and FPPT through the Keepsake Helper (ADR-0084)
        self.store = store
        self.manager = manager
        self.tools = tools
        self.limits = limits  # the device profile's TDP range, a second clamp next to steamos-manager's
        self.game: int | None = None
        self.before: dict[str, Any] = {}  # what was there before Keepsake set anything this game
        self.applied: dict[str, Any] = {}  # what Keepsake set
        self.stopped: str | None = None  # why Keepsake stopped applying until the next game

    def status(self) -> dict[str, Any]:
        tools = self.tools()
        try:
            current = self.manager.read()
            problem = None
        except ManagerError as exc:
            current, problem = None, str(exc)
        return {
            "available": current is not None,
            "problem": problem,
            "current": current,
            "tools": tools,
            "game": self.game,
            "profile": self.store.get(self.game) if self.game else None,
            "applied": dict(self.applied),
            "stopped": self.stopped,
            "limits": self.limits(),
            "powerLimits": self._power_status(),
        }

    def _power_status(self) -> dict[str, Any]:
        ranges = self.power.read() if self.power else None
        return {
            "available": ranges is not None,
            "ready": bool(ranges is not None and self.power and self.power.helper.status().get("ready")),
            "ranges": ranges,
        }

    def _clamp(self, tdp: int, current: dict[str, Any]) -> int:
        low, high = int(current["tdp"]["min"]), int(current["tdp"]["max"])
        limits = self.limits()
        if limits.get("min"):
            low = max(low, int(limits["min"]))
        if limits.get("max"):
            high = min(high, int(limits["max"]))
        return max(low, min(high, int(tdp)))

    def apply(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Set each part of ``profile`` that this device supports, in order: mode, TDP, boost.

        A TDP needs the Custom mode (the firmware ignores power limits in any other), so asking
        for a TDP switches to Custom first when the device offers it.
        """
        tools = self.tools()
        if tools:
            raise ProfileError(f"{', '.join(tools)} manages performance on this device; Haversack only shows it")
        profile = clean_profile(profile)
        current = self.manager.read()
        mode = profile.get("mode")
        wants_custom = profile.get("tdp") is not None or profile.get("limits") is not None
        if wants_custom and current.get("profile") and "custom" in current["profile"]["available"]:
            mode = "custom"
        if mode is not None:
            if not current.get("profile") or mode not in current["profile"]["available"]:
                raise ProfileError("this device does not offer that performance mode")
            self.before.setdefault("mode", current["profile"]["current"])
            self.applied["mode"] = self.manager.set_profile(mode)
        if profile.get("tdp") is not None:
            if not current.get("tdp"):
                raise ProfileError("this device does not offer a TDP limit through steamos-manager")
            self.before.setdefault("tdp", current["tdp"]["value"])
            self.applied["tdp"] = self.manager.set_tdp(self._clamp(profile["tdp"], current))
        if profile.get("boost") is not None:
            if current.get("boost") is None:
                raise ProfileError("this device does not offer CPU boost control")
            self.before.setdefault("boost", current["boost"])
            self.applied["boost"] = self.manager.set_boost(profile["boost"])
        if profile.get("limits") is not None:
            # After the TDP: steamos-manager's TDP writes one value to all three.
            if self.power is None or self.power.read() is None:
                raise ProfileError("this device does not offer separate power limits")
            self.before.setdefault("limits", self.power.current())
            try:
                self.applied["limits"] = self.power.set(profile["limits"])
            except LimitsError as exc:
                raise ProfileError(str(exc)) from exc
        return dict(self.applied)

    def game_started(self, appid: int) -> dict[str, Any] | None:
        self.game, self.before, self.applied, self.stopped = int(appid), {}, {}, None
        profile = self.store.get(int(appid))
        if not profile:
            return None
        try:
            return self.apply(profile)
        except (ProfileError, ManagerError, LimitsError) as exc:
            self.stopped = str(exc)
            return None

    def watch(self) -> str | None:
        """After applying: if something else changed a value Keepsake set, stop and say so."""
        if not self.applied or self.stopped:
            return None
        try:
            current = self.manager.read()
        except ManagerError:
            return None
        now = {
            "mode": (current.get("profile") or {}).get("current"),
            "tdp": (current.get("tdp") or {}).get("value"),
            "boost": current.get("boost"),
            "limits": self.power.current() if self.power and "limits" in self.applied else None,
        }
        changed = [k for k, v in self.applied.items() if now.get(k) != v]
        if changed:
            self.stopped = (
                "another app (probably Steam's own performance settings) changed it; Haversack leaves it alone"
            )
            self.applied = {k: v for k, v in self.applied.items() if k not in changed}
            self.before = {k: v for k, v in self.before.items() if k not in changed}
        return self.stopped

    def restore(self) -> list[str]:
        """Put back what was there before, for each value that still holds what Keepsake set."""
        restored: list[str] = []
        if not self.applied:
            return restored
        try:
            current = self.manager.read()
        except ManagerError:
            return restored
        now = {
            "mode": (current.get("profile") or {}).get("current"),
            "tdp": (current.get("tdp") or {}).get("value"),
            "boost": current.get("boost"),
            "limits": self.power.current() if self.power and "limits" in self.applied else None,
        }
        setters: dict[str, Callable[[Any], Any]] = {
            "limits": lambda v: self.power.set(v) if self.power else None,
            "tdp": self.manager.set_tdp,
            "boost": self.manager.set_boost,
            "mode": self.manager.set_profile,
        }
        for key in ("limits", "tdp", "boost", "mode"):  # the mode last: putting it back resets the firmware's limits
            if key in self.applied and key in self.before and now.get(key) == self.applied[key]:
                try:
                    setters[key](self.before[key])
                    restored.append(key)
                except (ManagerError, LimitsError):
                    continue
        self.applied, self.before = {}, {}
        return restored

    def game_exited(self) -> list[str]:
        restored = self.restore()
        self.game, self.stopped = None, None
        return restored

    def resumed(self) -> dict[str, Any] | None:
        """After sleep: the firmware may have reset Custom, so apply the running game's profile again."""
        if self.game is None or self.stopped:
            return None
        profile = self.store.get(self.game)
        if not profile:
            return None
        try:
            return self.apply(profile)
        except (ProfileError, ManagerError) as exc:
            self.stopped = str(exc)
            return None
