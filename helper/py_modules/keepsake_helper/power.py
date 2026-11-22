"""Separate power limits: SPL, SPPT and FPPT through the kernel's firmware attributes (ADR-0084).

Only these three attributes of the Lenovo WMI driver, at
``/sys/class/firmware-attributes/lenovo-wmi-other-*/attributes/<name>/current_value``:

- each value must be an integer within the attribute's own ``min_value`` and ``max_value`` and on
  its ``scalar_increment``;
- SPL <= SPPT <= FPPT, as the firmware expects;
- the platform profile must already be ``custom`` (Keepsake switches it through steamos-manager);
  in any other mode the firmware refuses (EBUSY) and overrides the limits anyway;
- the writes are ordered so the three never cross on the way, and every value is read back.
"""

from __future__ import annotations

import glob
import os
from typing import Any

ROOT = "/sys/class/firmware-attributes"
NAMES = ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt")
KEYS = {"spl": "ppt_pl1_spl", "sppt": "ppt_pl2_sppt", "fppt": "ppt_pl3_fppt"}
PROFILE_GLOB = "/sys/class/platform-profile/platform-profile-*"


class PowerError(Exception):
    pass


def _text(path: str) -> str:
    with open(path, encoding="ascii", errors="replace") as handle:
        return handle.read(64).strip()


def attributes_dir(root: str = ROOT) -> str:
    for folder in sorted(glob.glob(os.path.join(root, "lenovo-wmi-other-*", "attributes"))):
        if all(os.path.isdir(os.path.join(folder, name)) for name in NAMES):
            return folder
    raise PowerError("this device's firmware does not offer separate power limits")


def read(root: str = ROOT) -> dict[str, dict[str, int]]:
    folder = attributes_dir(root)
    out = {}
    for key, name in KEYS.items():
        base = os.path.join(folder, name)
        step = (
            _text(os.path.join(base, "scalar_increment"))
            if os.path.exists(os.path.join(base, "scalar_increment"))
            else "1"
        )
        out[key] = {
            "current": int(_text(os.path.join(base, "current_value"))),
            "min": int(_text(os.path.join(base, "min_value"))),
            "max": int(_text(os.path.join(base, "max_value"))),
            "step": max(1, int(step or 1)),
        }
    return out


def profile(profile_glob: str = PROFILE_GLOB) -> str | None:
    for folder in sorted(glob.glob(profile_glob)):
        try:
            if _text(os.path.join(folder, "name")).startswith("lenovo"):
                return _text(os.path.join(folder, "profile"))
        except OSError:
            continue
    return None


def validate(values: Any, ranges: dict[str, dict[str, int]]) -> dict[str, int]:
    if not isinstance(values, dict) or set(values) != set(KEYS):
        raise PowerError("give SPL, SPPT and FPPT")
    out = {}
    for key in KEYS:
        value = values[key]
        r = ranges[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise PowerError(f"{key.upper()} must be a whole number of watts")
        if not r["min"] <= value <= r["max"] or (value - r["min"]) % r["step"]:
            raise PowerError(f"{key.upper()} must be {r['min']} to {r['max']} W")
        out[key] = value
    if not out["spl"] <= out["sppt"] <= out["fppt"]:
        raise PowerError("the limits must rise: SPL, then SPPT, then FPPT")
    return out


def order(current: dict[str, int], wanted: dict[str, int]) -> list[str]:
    """Write order that keeps SPL <= SPPT <= FPPT after every single write."""
    state = dict(current)
    left = [k for k in KEYS if wanted[k] != current[k]]
    done: list[str] = []
    while left:
        for key in list(left):
            trial = {**state, key: wanted[key]}
            if trial["spl"] <= trial["sppt"] <= trial["fppt"]:
                state = trial
                done.append(key)
                left.remove(key)
                break
        else:
            done += left  # cannot happen for valid input; write the rest in order
            break
    return done


def apply(values: Any, root: str = ROOT, profile_glob: str = PROFILE_GLOB) -> dict[str, int]:
    if profile(profile_glob) != "custom":
        raise PowerError("switch the performance mode to Custom first")
    ranges = read(root)
    wanted = validate(values, ranges)
    folder = attributes_dir(root)
    for key in order({k: r["current"] for k, r in ranges.items()}, wanted):
        path = os.path.join(folder, KEYS[key], "current_value")
        with open(path, "w", encoding="ascii") as handle:
            handle.write(str(wanted[key]))
    after = {k: r["current"] for k, r in read(root).items()}
    if after != wanted:
        raise PowerError("the firmware did not keep the limits")
    return after
