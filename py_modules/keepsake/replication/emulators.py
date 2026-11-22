"""Emulator setups and their games on this device (R26 stage 1, ADR-0087). Read-only.

Finds:
- **EmuDeck**, from ``~/.config/EmuDeck/settings.sh`` (``romsPath``, ``biosPath``, ``storagePath``,
  ``emulationPath``), or its default ``~/Emulation`` folders;
- **RetroDECK**, from its ``retrodeck.json`` (``paths.roms_path`` and friends), or ``~/retrodeck``;
- **standalone emulators**, by their AppImage, binary or Flatpak folder.

Games are grouped so that one game is one unit: a ``.cue`` with its ``.bin`` files, a ``.gdi`` with
its tracks, an ``.m3u`` with its discs (and theirs), a folder game (PS3 ``PS3_GAME``, Wii U
``code``/``content``/``meta``) as one unit, and any other file on its own.

Firmware, BIOS files and keys are counted by name and place only. Their contents are never read,
hashed, logged or sent: only how many there are, and for which system.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

MAX_GAMES = 5000
MAX_DEPTH = 3
SKIP_EXT = {".txt", ".nfo", ".jpg", ".jpeg", ".png", ".xml", ".sav", ".srm", ".state", ".dat", ".db", ".ini", ".cfg"}
SKIP_NAMES = {"systeminfo.txt", "metadata.txt", "media", "downloaded_media", "gamelists"}
# Standalone emulators: label, AppImage or binary paths under the home folder, Flatpak ID, system.
EMULATORS: list[tuple[str, tuple[str, ...], str | None, str]] = [
    ("Dolphin", (), "org.DolphinEmu.dolphin-emu", "gc"),
    ("PCSX2", ("Applications/pcsx2-Qt.AppImage",), "net.pcsx2.PCSX2", "ps2"),
    ("RPCS3", ("Applications/rpcs3.AppImage",), "net.rpcs3.RPCS3", "ps3"),
    (
        "Ryujinx",
        ("Applications/publish/Ryujinx", "Applications/publish/Ryujinx.sh"),
        "io.github.ryubing.Ryujinx",
        "switch",
    ),
    ("Eden", ("Applications/Eden.AppImage",), "dev.eden_emu.eden", "switch"),
    ("Citron", ("Applications/citron.AppImage",), None, "switch"),
    ("Cemu", ("Applications/Cemu.AppImage",), "info.cemu.Cemu", "wiiu"),
    (
        "DuckStation",
        ("Applications/DuckStation.AppImage", "Applications/DuckStation-x64.AppImage"),
        "org.duckstation.DuckStation",
        "psx",
    ),
    ("PPSSPP", (), "org.ppsspp.PPSSPP", "psp"),
    ("RetroArch", (), "org.libretro.RetroArch", "multi"),
    ("xemu", (), "app.xemu.xemu", "xbox"),
    ("Vita3K", ("Applications/Vita3K/Vita3K",), None, "psvita"),
    ("ShadPS4", ("Applications/Shadps4-qt.AppImage", "Applications/shadPS4.AppImage"), "net.shadps4.shadPS4", "ps4"),
    ("Azahar", ("Applications/azahar.AppImage",), "org.azahar_emu.Azahar", "n3ds"),
]
# Keys and firmware, by place (relative to the home folder) and system: counted, never read.
SECRETS: list[tuple[str, str]] = [
    (".config/Ryujinx/system", "switch"),
    (".local/share/eden/keys", "switch"),
    (".local/share/citron/keys", "switch"),
    (".config/Cemu/keys.txt", "wiiu"),
    (".local/share/azahar-emu/sysdata", "n3ds"),
    (".local/share/shadPS4/sys_modules", "ps4"),
]
_CUE_FILE = re.compile(r'^\s*FILE\s+"([^"]+)"', re.IGNORECASE | re.MULTILINE)


@dataclass
class Game:
    system: str
    name: str
    files: list[str] = field(default_factory=list)  # relative to the ROM root
    size: int = 0


def _read_small(path: str, limit: int = 65536) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def emudeck(home: str) -> dict[str, str] | None:
    """EmuDeck's paths from its settings file, or its defaults if only the folders exist."""
    text = _read_small(os.path.join(home, ".config", "EmuDeck", "settings.sh")) or _read_small(
        os.path.join(home, "emudeck", "settings.sh")
    )
    paths: dict[str, str] = {}
    for key in ("emulationPath", "romsPath", "biosPath", "storagePath", "savesPath"):
        found = re.search(rf'^\s*{key}=["\']?([^"\'\n]+)["\']?\s*$', text, re.MULTILINE)
        if found:
            paths[key] = found.group(1).replace("$HOME", home).replace("~", home, 1)
    if not paths and os.path.isdir(os.path.join(home, "Emulation", "roms")):
        base = os.path.join(home, "Emulation")
        paths = {"emulationPath": base, "romsPath": os.path.join(base, "roms"), "biosPath": os.path.join(base, "bios")}
    if not paths:
        return None
    base = paths.get("emulationPath", "")
    paths.setdefault("romsPath", os.path.join(base, "roms"))
    paths.setdefault("biosPath", os.path.join(base, "bios"))
    return paths


def retrodeck(home: str) -> dict[str, str] | None:
    config = os.path.join(home, ".var", "app", "net.retrodeck.retrodeck", "config", "retrodeck", "retrodeck.json")
    try:
        data = json.loads(_read_small(config, 1 << 20) or "{}")
    except ValueError:
        data = {}
    paths = dict(data.get("paths") or {}) if isinstance(data, dict) else {}
    root = str(paths.get("rd_home_path") or os.path.join(home, "retrodeck"))
    if not paths and not os.path.isdir(os.path.join(root, "roms")):
        return None
    return {
        "romsPath": str(paths.get("roms_path") or os.path.join(root, "roms")),
        "biosPath": str(paths.get("bios_path") or os.path.join(root, "bios")),
    }


def emulators(home: str) -> list[dict[str, Any]]:
    out = []
    for label, files, flatpak, system in EMULATORS:
        found = next((f for f in files if os.path.exists(os.path.join(home, f))), None)
        if found:
            out.append(
                {
                    "name": label,
                    "system": system,
                    "type": "appimage" if found.endswith(".AppImage") else "binary",
                    "path": found,
                }
            )
            continue
        if flatpak and os.path.isdir(os.path.join(home, ".var", "app", flatpak)):
            out.append({"name": label, "system": system, "type": "flatpak", "id": flatpak})
    return out


def _referenced(folder: str, name: str) -> list[str]:
    """Files a playlist or cue sheet names, relative to its folder (only those that exist)."""
    path = os.path.join(folder, name)
    lower = name.lower()
    text = _read_small(path)
    if lower.endswith(".cue"):
        names = _CUE_FILE.findall(text)
    elif lower.endswith(".gdi"):
        names = [line.split()[4].strip('"') for line in text.splitlines()[1:] if len(line.split()) >= 5]
    elif lower.endswith(".m3u"):
        names = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    else:
        return []
    out = []
    for item in names:
        candidate = os.path.normpath(os.path.join(os.path.dirname(name), item))
        if not candidate.startswith("..") and os.path.exists(os.path.join(folder, candidate)):
            out.append(candidate.replace(os.sep, "/"))
            out += [
                os.path.normpath(os.path.join(os.path.dirname(candidate), r)).replace(os.sep, "/")
                for r in _referenced(folder, candidate)
            ]
    return out


def _folder_game(path: str) -> bool:
    return os.path.isdir(os.path.join(path, "PS3_GAME")) or all(
        os.path.isdir(os.path.join(path, d)) for d in ("code", "content", "meta")
    )


def _size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for folder, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(folder, name))
            except OSError:
                continue
    return total


def games(roms: str, limit: int = MAX_GAMES) -> list[Game]:
    """Every game under ``roms/<system>/``, one unit per game."""
    out: list[Game] = []
    if not os.path.isdir(roms):
        return out
    for system in sorted(os.listdir(roms)):
        base = os.path.join(roms, system)
        if not os.path.isdir(base) or system.startswith(".") or system in SKIP_NAMES:
            continue
        claimed: set[str] = set()
        entries: list[str] = []
        for folder, dirs, files in os.walk(base):
            depth = os.path.relpath(folder, base).count(os.sep)
            dirs[:] = sorted(d for d in dirs if d not in SKIP_NAMES and not d.startswith("."))
            for d in list(dirs):
                if _folder_game(os.path.join(folder, d)):
                    entries.append(os.path.relpath(os.path.join(folder, d), base))
                    dirs.remove(d)
            if depth >= MAX_DEPTH:
                dirs[:] = []
            entries += [os.path.relpath(os.path.join(folder, f), base) for f in sorted(files)]
        # Playlists and cue sheets first, so the files they name are claimed by them.
        entries.sort(
            key=lambda e: (0 if e.lower().endswith(".m3u") else 1 if e.lower().endswith((".cue", ".gdi")) else 2, e)
        )
        for entry in entries:
            rel = entry.replace(os.sep, "/")
            if rel in claimed or os.path.splitext(rel)[1].lower() in SKIP_EXT:
                continue
            members = [rel, *_referenced(base, rel)]
            claimed.update(members)
            name = os.path.splitext(os.path.basename(rel))[0]
            out.append(Game(system, name, members, sum(_size(os.path.join(base, m)) for m in members)))
            if len(out) >= limit:
                return out
    return out


def secrets_present(home: str, bios: str | None) -> dict[str, int]:
    """How many key and firmware files there are, per system. Counts only: nothing is opened."""
    counts: dict[str, int] = {}
    for rel, system in SECRETS:
        path = os.path.join(home, rel)
        n = (
            1
            if os.path.isfile(path)
            else sum(len(files) for _d, _s, files in os.walk(path))
            if os.path.isdir(path)
            else 0
        )
        if n:
            counts[system] = counts.get(system, 0) + n
    if bios and os.path.isdir(bios):
        n = sum(len(files) for _d, _s, files in os.walk(bios))
        if n:
            counts["bios"] = counts.get("bios", 0) + n
    return counts


def scan(home: str) -> dict[str, Any]:
    """This device's emulator setup: which tools, how many games per system, and counts of keys and firmware."""
    setups = {k: v for k, v in (("emudeck", emudeck(home)), ("retrodeck", retrodeck(home))) if v}
    found: list[Game] = []
    for paths in setups.values():
        found += games(paths["romsPath"])
    per_system: dict[str, int] = {}
    for game in found:
        per_system[game.system] = per_system.get(game.system, 0) + 1
    bios = next((p.get("biosPath") for p in setups.values()), None)
    return {
        "setups": sorted(setups),
        "emulators": emulators(home),
        "games": [{"system": g.system, "name": g.name, "files": len(g.files), "size": g.size} for g in found],
        "perSystem": per_system,
        "secrets": secrets_present(home, bios),
    }
