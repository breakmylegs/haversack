"""Separate power limits, SPL, SPPT and FPPT (R24, ADR-0084).

The firmware attributes are world-readable, so Keepsake reads the values and ranges itself;
writing needs root, so it goes through the Keepsake Helper, which checks the ranges again, writes
in a safe order and reads back. The firmware takes them only in the Custom mode, which Keepsake
sets through steamos-manager first.
"""

from __future__ import annotations

import glob
import os
from typing import Any

from .helper import HelperClient, HelperError

KEYS = {"spl": "ppt_pl1_spl", "sppt": "ppt_pl2_sppt", "fppt": "ppt_pl3_fppt"}


class LimitsError(ValueError):
    pass


def _int(path: str, default: int | None = None) -> int | None:
    try:
        with open(path, encoding="ascii", errors="replace") as handle:
            return int(handle.read(32).strip())
    except (OSError, ValueError):
        return default


def read(sys_root: str = "/sys") -> dict[str, dict[str, int]] | None:
    """``{"spl": {current, min, max, step}, ...}``, or None when the firmware does not offer them."""
    for folder in sorted(
        glob.glob(os.path.join(sys_root, "class", "firmware-attributes", "lenovo-wmi-other-*", "attributes"))
    ):
        out: dict[str, dict[str, int]] = {}
        for key, name in KEYS.items():
            base = os.path.join(folder, name)
            values = {f: _int(os.path.join(base, f"{f}_value")) for f in ("current", "min", "max")}
            if any(v is None for v in values.values()):
                break
            out[key] = {
                **{k: int(v) for k, v in values.items() if v is not None},
                "step": max(1, _int(os.path.join(base, "scalar_increment"), 1) or 1),
            }
        else:
            return out
    return None


def clean(values: Any) -> dict[str, int]:
    if not isinstance(values, dict) or set(values) != set(KEYS):
        raise LimitsError("give SPL, SPPT and FPPT")
    out = {}
    for key in KEYS:
        value = values[key]
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 120:
            raise LimitsError(f"{key.upper()} must be a whole number of watts")
        out[key] = value
    if not out["spl"] <= out["sppt"] <= out["fppt"]:
        raise LimitsError("the limits must rise: SPL, then SPPT, then FPPT")
    return out


def clamp(values: dict[str, int], ranges: dict[str, dict[str, int]]) -> dict[str, int]:
    """Each value into its firmware range and onto its step, still rising."""
    out = {}
    for key in KEYS:
        r = ranges[key]
        value = max(r["min"], min(r["max"], values[key]))
        out[key] = value - (value - r["min"]) % r["step"]
    out["sppt"] = max(out["sppt"], out["spl"])
    out["fppt"] = max(out["fppt"], out["sppt"])
    return out


class PowerLimits:
    def __init__(self, helper: HelperClient, sys_root: str = "/sys") -> None:
        self.helper = helper
        self.sys_root = sys_root

    def read(self) -> dict[str, dict[str, int]] | None:
        return read(self.sys_root)

    def current(self) -> dict[str, int] | None:
        found = self.read()
        return {k: v["current"] for k, v in found.items()} if found else None

    def ready(self) -> bool:
        return self.read() is not None and bool(self.helper.status().get("ready"))

    def set(self, values: dict[str, int]) -> dict[str, int]:
        ranges = self.read()
        if ranges is None:
            raise LimitsError("this device's firmware does not offer separate power limits")
        try:
            found = self.helper.call("power.set", values=clamp(clean(values), ranges))
        except HelperError as exc:
            raise LimitsError(str(exc)) from exc
        return {k: int(v) for k, v in dict(found.get("limits") or {}).items()}
