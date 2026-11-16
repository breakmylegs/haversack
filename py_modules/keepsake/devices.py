"""Core device profiles (v2 spec section 9, slice 14, ADR-0028).

Detects the handheld from DMI strings, the CPU name and the GPU vendor, and
picks the most specific profile from ``data/devices.json``, with a generic
fallback. Read-only: serial numbers and UUIDs are never read. Shared by
Advisor now and by Replication preflight and Desktop later. Ported from
Peter's Tuning Advisor under the signed-off audit (ADR-0013).
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "devices.json")
DMI_FIELDS = ("sys_vendor", "product_name", "product_version", "product_family", "board_name", "board_vendor")
GPU_VENDORS = {"0x1002": "amd", "0x8086": "intel", "0x10de": "nvidia"}
GENERIC_TDP = {"min": 5, "max": 25}
BAND_FRACTIONS = {"light": 0.25, "medium": 0.50, "heavy": 0.70, "max": 0.90}


def derived_bands(tdp_min: float, tdp_max: float) -> dict[str, Any]:
    span = tdp_max - tdp_min
    bands: dict[str, Any] = {k: int(tdp_min + span * f + 0.5) for k, f in BAND_FRACTIONS.items()}
    bands["derived"] = True
    return bands


def load_profiles(path: str = DATA_FILE) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return list(json.load(handle)["devices"])


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def read_facts(root: str = "/") -> dict[str, Any]:
    """DMI model strings, the CPU model name and the GPU vendor. ``root`` lets tests use a captured dump."""
    dmi_dir = os.path.join(root, "sys", "class", "dmi", "id")
    facts: dict[str, Any] = {f: _read(os.path.join(dmi_dir, f)) for f in DMI_FIELDS}
    cpu = ""
    for line in _read(os.path.join(root, "proc", "cpuinfo")).splitlines():
        if line.startswith("model name"):
            cpu = line.split(":", 1)[1].strip()
            break
    facts["cpu_model"] = cpu
    vendors = []
    for vendor_file in sorted(glob.glob(os.path.join(root, "sys", "class", "drm", "card[0-9]", "device", "vendor"))):
        vendor = GPU_VENDORS.get(_read(vendor_file).lower())
        if vendor and vendor not in vendors:
            vendors.append(vendor)
    facts["gpu_vendor"] = vendors[0] if vendors else ""
    return facts


def match_score(entry: dict[str, Any], facts: dict[str, Any]) -> int:
    """0 when the entry does not match, else the number of conditions met (the most specific wins)."""
    score = 0
    for field, wanted in (entry.get("match") or {}).items():
        if not wanted:
            continue
        actual = str(facts.get(field, "")).strip().casefold()
        if not any(actual == str(w).strip().casefold() for w in wanted):
            return 0
        score += 1
    if score == 0:
        return 0
    cpu = str(facts.get("cpu_model", "")).casefold()
    for needle in entry.get("cpu_contains") or []:
        if needle.casefold() not in cpu:
            return 0
        score += 1
    for needle in entry.get("cpu_excludes") or []:
        if needle.casefold() in cpu:
            return 0
    return score


def generic_profile(facts: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "generic",
        "vendor": facts.get("sys_vendor") or "Unknown",
        "model": facts.get("product_version") or facts.get("product_name") or "Unknown device",
        "family": "generic",
        "apu": facts.get("cpu_model") or "Unknown",
        "gpu": {"vendor": facts.get("gpu_vendor") or "unknown", "name": "", "arch": "", "cu": None},
        "display": {"width": None, "height": None, "refresh_hz_max": None, "vrr": False, "vrr_range_hz": None},
        "tdp_w": dict(GENERIC_TDP),
        "tdp_bands_w": derived_bands(GENERIC_TDP["min"], GENERIC_TDP["max"]),
        "steam_native_tdp": None,
        "usb4_ports": None,
        "wifi": None,
        "report_aliases": [],
        "generic": True,
        "verified": False,
    }


def resolve(profiles: list[dict[str, Any]], facts: dict[str, Any], override: str = "") -> tuple[dict[str, Any], str]:
    """``(profile, how)`` where ``how`` is ``override``, ``detected`` or ``generic``."""
    if override:
        chosen = next((p for p in profiles if p["id"] == override), None)
        if chosen:
            return chosen, "override"
    best, best_score = None, 0
    for entry in profiles:
        score = match_score(entry, facts)
        if score > best_score:
            best, best_score = entry, score
    if best:
        return best, "detected"
    return generic_profile(facts), "generic"


def public_facts(facts: dict[str, Any]) -> dict[str, str]:
    """Facts shown in the UI: DMI model strings and the CPU name only."""
    return {
        k: str(facts.get(k, "")) for k in ("sys_vendor", "product_name", "product_version", "board_name", "cpu_model")
    }
