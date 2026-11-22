"""This device's live readings, for Device, Status (R21 stage 1, ADR-0074). Core, read-only.

Temperatures and fan speeds from every hwmon chip, power from the battery and the GPU, the
BIOS version and date, the firmware performance mode (ACPI ``platform_profile``), and the CPU's
boost, SMT and online cores. Everything here is a world-readable sysfs file: nothing needs
root, nothing is written, and a file that is missing is simply left out. Serial numbers and
UUIDs are never read.
"""

from __future__ import annotations

import glob
import os
import re
from typing import Any

MAX_CHIPS = 16
MAX_SENSORS = 12  # per chip
# Lenovo's firmware modes as the kernel names them, in the words Legion Space uses.
PROFILE_WORDS = {
    "low-power": "Quiet",
    "quiet": "Quiet",
    "cool": "Quiet",
    "balanced": "Balanced",
    "balanced-performance": "Balanced",
    "performance": "Performance",
    "custom": "Custom",
}


def _text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(4096).strip()
    except OSError:
        return None


def _int(path: str) -> int | None:
    text = _text(path)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def _sensors(folder: str, kind: str, scale: float) -> list[dict[str, Any]]:
    out = []
    files = sorted(
        glob.glob(os.path.join(folder, f"{kind}*_input")),
        key=lambda p: int(re.sub(r"\D", "", os.path.basename(p)) or 0),
    )
    for path in files[:MAX_SENSORS]:
        value = _int(path)
        if value is None:
            continue
        label = _text(path.replace("_input", "_label"))
        out.append({"label": label or os.path.basename(path).replace("_input", ""), "value": round(value / scale, 1)})
    return out


def chips(sys_root: str = "/sys") -> list[dict[str, Any]]:
    """Each hwmon chip with its temperatures (degrees C), fans (RPM) and power (W)."""
    found = []
    for folder in sorted(glob.glob(os.path.join(sys_root, "class", "hwmon", "hwmon*")))[:MAX_CHIPS]:
        name = _text(os.path.join(folder, "name")) or os.path.basename(folder)
        chip = {
            "name": name,
            "temps": _sensors(folder, "temp", 1000.0),
            "fans": _sensors(folder, "fan", 1.0),
            "power": _sensors(folder, "power", 1_000_000.0),
        }
        if chip["temps"] or chip["fans"] or chip["power"]:
            found.append(chip)
    return found


def _battery(sys_root: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for supply in sorted(glob.glob(os.path.join(sys_root, "class", "power_supply", "*"))):
        kind = _text(os.path.join(supply, "type"))
        if kind == "Mains":
            out["mains"] = _int(os.path.join(supply, "online")) == 1
        elif kind == "Battery" and _text(os.path.join(supply, "scope")) != "Device" and "percent" not in out:
            out["percent"] = _int(os.path.join(supply, "capacity"))
            out["status"] = _text(os.path.join(supply, "status"))
            power = _int(os.path.join(supply, "power_now"))
            if power is None:
                current, voltage = _int(os.path.join(supply, "current_now")), _int(os.path.join(supply, "voltage_now"))
                power = current * voltage // 1_000_000 if current is not None and voltage is not None else None
            out["watts"] = round(abs(power) / 1_000_000, 1) if power is not None else None
            limit = _int(os.path.join(supply, "charge_control_end_threshold"))
            if limit is not None:
                out["chargeLimit"] = limit  # read only here; changing it is stage 4
    return out


def _profile(sys_root: str) -> dict[str, Any] | None:
    # The ACPI platform profile: one per device in /sys/class/platform-profile (kernel 6.14 and
    # later), or the older single file in /sys/firmware/acpi.
    for folder in sorted(glob.glob(os.path.join(sys_root, "class", "platform-profile", "platform-profile-*"))):
        current = _text(os.path.join(folder, "profile"))
        if current:
            choices = (_text(os.path.join(folder, "choices")) or "").split()
            return {"current": current, "choices": choices, "words": PROFILE_WORDS.get(current, current.capitalize())}
    current = _text(os.path.join(sys_root, "firmware", "acpi", "platform_profile"))
    if not current:
        return None
    choices = (_text(os.path.join(sys_root, "firmware", "acpi", "platform_profile_choices")) or "").split()
    return {"current": current, "choices": choices, "words": PROFILE_WORDS.get(current, current.capitalize())}


def _cpu(sys_root: str) -> dict[str, Any]:
    base = os.path.join(sys_root, "devices", "system", "cpu")
    boost = _int(os.path.join(base, "cpufreq", "boost"))
    if boost is None:
        values = [_int(p) for p in glob.glob(os.path.join(base, "cpufreq", "policy*", "boost"))]
        known = [v for v in values if v is not None]
        boost = int(any(known)) if known else None
    online = _text(os.path.join(base, "online")) or ""
    count = 0
    for part in online.split(","):
        if "-" in part:
            low, _, high = part.partition("-")
            if low.isdigit() and high.isdigit():
                count += int(high) - int(low) + 1
        elif part.isdigit():
            count += 1
    return {
        "boost": None if boost is None else bool(boost),
        "smt": _text(os.path.join(base, "smt", "control")),
        "online": count or None,
    }


def read_status(sys_root: str = "/sys") -> dict[str, Any]:
    """One reading of everything above. Cheap: a few dozen small files."""
    dmi = os.path.join(sys_root, "class", "dmi", "id")
    found = chips(sys_root)
    gpu_watts = next((c["power"][0]["value"] for c in found if c["name"] == "amdgpu" and c["power"]), None)
    return {
        "chips": found,
        "battery": _battery(sys_root),
        "gpuWatts": gpu_watts,
        "bios": {"version": _text(os.path.join(dmi, "bios_version")), "date": _text(os.path.join(dmi, "bios_date"))},
        "profile": _profile(sys_root),
        "cpu": _cpu(sys_root),
    }
