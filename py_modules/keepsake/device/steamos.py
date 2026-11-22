"""steamos-manager over the session bus: TDP, performance mode and CPU boost without root (ADR-0075 tier 0).

Valve's user daemon (``com.steampowered.SteamOSManager1`` on the session bus) offers these as
properties; its root daemon writes the firmware files. Each interface is optional: a missing
one means the device does not support that feature, and it is shown as unavailable. Every set
is read back. One short connection per operation, through Keepsake's own pure-Python D-Bus
client, so no binary and no library is needed.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from ..desktop import dbus

BUS = "com.steampowered.SteamOSManager1"
PATH = "/com/steampowered/SteamOSManager1"
PROPS = "org.freedesktop.DBus.Properties"
TDP = f"{BUS}.TdpLimit1"
PROFILE = f"{BUS}.PerformanceProfile1"
BOOST = f"{BUS}.CpuBoost1"
CHARGE = f"{BUS}.BatteryChargeLimit1"
TIMEOUT = 3.0


class ManagerError(Exception):
    pass


def default_connect() -> dbus.Connection:
    """The user's session bus: from the environment, else ``/run/user/<uid>/bus`` (Decky's plugin
    processes may not inherit the session variables)."""
    address = os.environ.get("DBUS_SESSION_BUS_ADDRESS") or ""
    if not address and hasattr(os, "getuid"):
        address = f"unix:path=/run/user/{os.getuid()}/bus"
    return dbus.Connection(address or None, timeout=TIMEOUT)


def _plain(value: Any) -> Any:
    return value[1] if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str) else value


class SteamOSManager:
    def __init__(self, connect: Callable[[], Any] = default_connect) -> None:
        self.connect = connect

    def _with(self, work: Callable[[Any], Any]) -> Any:
        try:
            conn = self.connect()
        except (dbus.DBusError, OSError) as exc:
            raise ManagerError(f"the session bus could not be reached ({type(exc).__name__})") from exc
        try:
            return work(conn)
        except (dbus.DBusError, OSError) as exc:
            raise ManagerError(str(exc)[:200]) from exc
        finally:
            conn.close()

    def _all(self, conn: Any, interface: str) -> dict[str, Any] | None:
        try:
            (found,) = conn.call(BUS, PATH, PROPS, "GetAll", "s", [interface])
        except dbus.DBusError:
            return None  # this device's steamos-manager does not offer the interface
        values = {str(k): _plain(v) for k, v in dict(found).items()}
        return values or None

    def read(self) -> dict[str, Any]:
        """What steamos-manager offers here, and the current values. Raises ManagerError if it is absent."""

        def work(conn: Any) -> dict[str, Any]:
            tdp = self._all(conn, TDP)
            profile = self._all(conn, PROFILE)
            boost = self._all(conn, BOOST)
            charge = self._all(conn, CHARGE)
            if tdp is None and profile is None and boost is None and charge is None:
                raise ManagerError("steamos-manager is not running on this system")
            return {
                "tdp": None
                if tdp is None
                else {
                    "value": int(tdp.get("TdpLimit", 0)),
                    "min": int(tdp.get("TdpLimitMin", 0)),
                    "max": int(tdp.get("TdpLimitMax", 0)),
                },
                "profile": None
                if profile is None
                else {
                    "current": str(profile.get("PerformanceProfile", "")),
                    "available": [str(p) for p in profile.get("AvailablePerformanceProfiles", [])],
                    "suggested": str(profile.get("SuggestedDefaultPerformanceProfile", "")),
                },
                "boost": None if boost is None else bool(int(boost.get("CpuBoostState", 0))),
                "chargeLimit": None
                if charge is None
                else {
                    "value": int(charge.get("MaxChargeLevel", -1)),
                    "minimum": int(charge.get("SuggestedMinimumLimit", 0)),
                },
            }

        result: dict[str, Any] = self._with(work)
        return result

    def _set(self, interface: str, prop: str, signature: str, value: Any) -> Any:
        def work(conn: Any) -> Any:
            conn.call(BUS, PATH, PROPS, "Set", "ssv", [interface, prop, (signature, value)])
            (back,) = conn.call(BUS, PATH, PROPS, "Get", "ss", [interface, prop])
            return _plain(back)

        return self._with(work)

    def set_profile(self, name: str) -> str:
        back = str(self._set(PROFILE, "PerformanceProfile", "s", name))
        if back != name:
            raise ManagerError(f"the mode reads back as {back}, not {name}")
        return back

    def set_tdp(self, watts: int) -> int:
        back = int(self._set(TDP, "TdpLimit", "u", int(watts)))
        if back != int(watts):
            raise ManagerError(f"the TDP reads back as {back} W, not {watts} W")
        return back

    def set_charge_limit(self, level: int) -> int:
        """``MaxChargeLevel``: a percentage, or -1 for no limit (R21 stage 4)."""
        back = int(self._set(CHARGE, "MaxChargeLevel", "i", int(level)))
        if back != int(level):
            raise ManagerError(f"the charge limit reads back as {back}, not {level}")
        return back

    def set_boost(self, on: bool) -> bool:
        back = bool(int(self._set(BOOST, "CpuBoostState", "u", 1 if on else 0)))
        if back != on:
            raise ManagerError("CPU boost did not change")
        return back
