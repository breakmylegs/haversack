"""Copying an emulator game to the other device: the plan, the offer and where each part lands (R26 stage 2, ADR-0087).

An emulator offer is its own kind (``"kind": "emulator"``), checked by its own validator, so the
game offer's rules stay as they are. It carries up to four parts, each a share like a game's:

- ``rom``: the game's unit (a file and what it names, or a folder game), always;
- ``app``: the emulator's AppImage or program folder, when the other device lacks it;
- ``config``: the emulator's settings folder, only when the other device has none (never overwritten);
- ``keys``: firmware, BIOS and key files, only after a separate confirmation, never to the cloud.

On the receiving device each part lands in its own place, chosen there and never taken from the
offer: ``rom`` under its ROM folder for the same system, ``app`` in ``~/Applications``, ``config`` in
the emulator's own settings folder, ``keys`` in the emulator's own key or BIOS folder, written
owner-only (0600 files in 0700 folders). The offer names the system, the emulator and relative
paths only: no absolute paths, user names or SD card labels (P10).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from . import emulators as emu

PARTS = ("rom", "app", "config", "keys")
SYSTEM = re.compile(r"^[a-z0-9][a-z0-9_-]{0,23}$")
UNIT = re.compile(r'^[^/\\:*?"<>|\x00-\x1f][^:*?"<>|\x00-\x1f]{0,239}$')
EMULATOR_NAMES = {name for name, _files, _flatpak, _system in emu.EMULATORS}
# Each emulator's settings folder and key folder, relative to the home folder (from the research).
CONFIG = {
    "PCSX2": ".config/PCSX2",
    "RPCS3": ".config/rpcs3",
    "Ryujinx": ".config/Ryujinx",
    "Eden": ".config/eden",
    "Citron": ".config/citron",
    "Cemu": ".config/Cemu",
    "DuckStation": ".local/share/duckstation",
    "Vita3K": ".config/Vita3K",
    "ShadPS4": ".local/share/shadPS4",
    "Azahar": ".config/azahar-emu",
}
KEYS = {
    "Ryujinx": ".config/Ryujinx/system",
    "Eden": ".local/share/eden/keys",
    "Citron": ".local/share/citron/keys",
    "Azahar": ".local/share/azahar-emu/sysdata",
    "ShadPS4": ".local/share/shadPS4/sys_modules",
}


class EmuPlanError(ValueError):
    pass


@dataclass
class EmuPlan:
    system: str
    unit: str  # the game's name on screen
    rom_root: str  # this device's ROM folder for the system
    rom_files: list[str]  # the unit's paths, relative to rom_root
    emulator: str | None = None
    roots: dict[str, str] = field(default_factory=dict)  # part to this device's folder or file


def plan(
    home: str,
    roms: str,
    game: emu.Game,
    emulator: dict[str, Any] | None,
    target: dict[str, Any],
    with_keys: bool,
) -> EmuPlan:
    """What sending ``game`` would carry, given what the other device already has (``target`` is its
    summary: emulators by name, settings folders present, systems with a ROM folder)."""
    if not SYSTEM.match(game.system):
        raise EmuPlanError("that system's folder name cannot be sent")
    if game.system not in set(target.get("systems") or []):
        raise EmuPlanError(f"the other device has no ROM folder for {game.system}: set up its emulators first")
    out = EmuPlan(game.system, game.name, os.path.join(roms, game.system), list(game.files))
    out.roots["rom"] = out.rom_root
    if emulator:
        name = str(emulator.get("name"))
        out.emulator = name
        have = set(target.get("emulators") or [])
        if name not in have:
            if emulator.get("type") == "flatpak":
                raise EmuPlanError(f"{name} is a Flatpak: install it on the other device first")
            path = os.path.join(home, str(emulator.get("path") or ""))
            out.roots["app"] = os.path.dirname(path) if emulator.get("type") == "binary" else path
        config = CONFIG.get(name)
        if config and name not in set(target.get("configs") or []) and os.path.isdir(os.path.join(home, config)):
            out.roots["config"] = os.path.join(home, config)
        keys = KEYS.get(name)
        if with_keys and keys and os.path.exists(os.path.join(home, keys)):
            out.roots["keys"] = os.path.join(home, keys)
    return out


def destination(part: str, offer: dict[str, Any], home: str, roms: str) -> str:
    """Where a part lands on this (receiving) device. Built here, never taken from the offer."""
    if part == "rom":
        return os.path.join(roms, offer["system"])
    emulator = offer.get("emulator")
    if part == "app":
        return os.path.join(home, "Applications")
    if part == "config" and emulator in CONFIG:
        return os.path.join(home, CONFIG[emulator])
    if part == "keys" and emulator in KEYS:
        return os.path.join(home, KEYS[emulator])
    raise EmuPlanError("that part cannot be placed here")


def validate(offer: Any) -> dict[str, Any]:
    """An emulator offer from the other device, field by field. Unknown fields are dropped."""
    if not isinstance(offer, dict) or offer.get("kind") != "emulator":
        raise EmuPlanError("the offer is not an emulator offer")
    system = str(offer.get("system", ""))
    unit = " ".join(str(offer.get("unit", "")).split())
    emulator = offer.get("emulator")
    if not SYSTEM.match(system) or not UNIT.match(unit):
        raise EmuPlanError("the offer is not valid")
    if emulator is not None and emulator not in EMULATOR_NAMES:
        raise EmuPlanError("the offer names an unknown emulator")
    shares = offer.get("shares")
    if not isinstance(shares, dict) or "rom" not in shares or set(shares) - set(PARTS):
        raise EmuPlanError("the offer is not valid")
    clean_shares = {}
    for part, share in shares.items():
        if not (
            isinstance(share, dict)
            and re.fullmatch(r"[0-9a-f]{32}", str(share.get("share", "")))
            and re.fullmatch(r"[0-9a-f]{64}", str(share.get("root", "")))
            and isinstance(share.get("bytes"), int)
            and share["bytes"] >= 0
        ):
            raise EmuPlanError("the offer is not valid")
        clean_shares[part] = {"share": share["share"], "root": share["root"], "bytes": share["bytes"]}
    if {"app", "config", "keys"} & set(clean_shares) and emulator is None:
        raise EmuPlanError("an emulator part needs the emulator's name")
    if ("config" in clean_shares and emulator not in CONFIG) or ("keys" in clean_shares and emulator not in KEYS):
        raise EmuPlanError("that emulator's settings or keys cannot be placed")
    return {
        "kind": "emulator",
        "id": str(offer.get("id", ""))[:16],
        "system": system,
        "unit": unit,
        "emulator": emulator,
        "shares": clean_shares,
        "keys": "keys" in clean_shares,
    }


def summary(home: str) -> dict[str, Any]:
    """What this device tells its paired device before a copy: systems with a ROM folder, emulators by
    name, and which emulators already have settings. No paths, contents or key details."""
    scan = emu.scan(home)
    setups = [p for p in (emu.emudeck(home), emu.retrodeck(home)) if p]
    systems: set[str] = set()
    for paths in setups:
        roms = paths["romsPath"]
        if os.path.isdir(roms):
            systems |= {d for d in os.listdir(roms) if os.path.isdir(os.path.join(roms, d)) and SYSTEM.match(d)}
    configs = [name for name, rel in CONFIG.items() if os.path.isdir(os.path.join(home, rel))]
    return {
        "systems": sorted(systems),
        "emulators": sorted(e["name"] for e in scan["emulators"]),
        "configs": sorted(configs),
        "games": [[g["system"], g["name"]] for g in scan["games"]][: emu.MAX_GAMES],
    }


def owner_only(path: str) -> None:
    """Keys and firmware on the receiving device: 0700 folders, 0600 files."""
    if os.path.isfile(path):
        os.chmod(path, 0o600)
        return
    os.chmod(path, 0o700)
    for folder, dirs, files in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(folder, d), 0o700)
        for f in files:
            os.chmod(os.path.join(folder, f), 0o600)
