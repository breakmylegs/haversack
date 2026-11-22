"""Receiving an emulator game (R26 stage 2, ADR-0087): where each part is copied to, and putting it in place.

A transfer replaces its whole target folder, so an emulator game is never copied straight into the
ROM folder (that would mean copying every other game too). Each part lands in its own staging
folder beside where it belongs, on the same disk, and is then moved into place:

- ``rom``: staged in ``<ROM folder>/<system>/.keepsake-emu-<offer>/``, then each file or folder of the
  game is moved into ``<ROM folder>/<system>/`` where nothing of that name exists;
- ``app``: staged in ``~/Applications/.keepsake-emu-<offer>/``, then moved in, the executable bit set;
- ``config``: sent only when this device has none, so it is copied straight to its own folder;
- ``keys``: staged beside the key folder, then only missing files are moved in, owner-only.

Nothing already on this device is ever replaced: a name that exists is left alone and reported.
The Steam shortcut is built from this device's own Steam ROM Manager parser for the system (its
launcher and arguments), never by running Steam ROM Manager (P15).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from typing import Any

from . import emuplan

STAGING = ".keepsake-emu-"


class EmuReceiveError(ValueError):
    pass


def targets(offer: dict[str, Any], offer_id: str, home: str, roms: str) -> dict[str, str]:
    """Where each part of ``offer`` is copied to. Raises when a part cannot be placed."""
    out: dict[str, str] = {}
    for part in offer["shares"]:
        final = emuplan.destination(part, offer, home, roms)
        if part == "config":
            if os.path.lexists(final):
                continue  # settings already here: never replaced (the sender should not have offered them)
            out[part] = final
            continue
        if part == "rom" and not os.path.isdir(final):
            raise EmuReceiveError(f"this device has no ROM folder for {offer['system']}")
        parent = final if part in ("rom", "app") else os.path.dirname(final)
        os.makedirs(parent, exist_ok=True)
        out[part] = os.path.join(parent, f"{STAGING}{part}-{offer_id}")
        if os.path.lexists(out[part]):
            raise EmuReceiveError("an earlier copy of this offer is still in the way")
    return out


def _move_missing(staged: str, final: str) -> tuple[list[str], list[str]]:
    """Move each top-level entry of ``staged`` into ``final`` unless the name exists there."""
    placed, skipped = [], []
    os.makedirs(final, exist_ok=True)
    for name in sorted(os.listdir(staged)):
        source, dest = os.path.join(staged, name), os.path.join(final, name)
        if os.path.lexists(dest):
            skipped.append(name)
            continue
        os.replace(source, dest)
        placed.append(name)
    shutil.rmtree(staged, ignore_errors=True)
    return placed, skipped


def finish(offer: dict[str, Any], staged: dict[str, str], home: str, roms: str) -> dict[str, Any]:
    """Put every copied part in place. Returns what was placed and what was left because it exists."""
    placed: dict[str, list[str]] = {}
    skipped: dict[str, list[str]] = {}
    for part, path in staged.items():
        final = emuplan.destination(part, offer, home, roms)
        if part == "config":
            placed[part] = [os.path.basename(final)] if os.path.isdir(final) else []
            continue
        if not os.path.isdir(path):
            continue
        placed[part], skipped[part] = _move_missing(path, final)
        if part == "app":
            for name in placed[part]:
                entry = os.path.join(final, name)
                if os.path.isfile(entry):
                    os.chmod(entry, os.stat(entry).st_mode | stat.S_IXUSR)
        if part == "keys":
            for name in placed[part]:
                emuplan.owner_only(os.path.join(final, name))
            emuplan.owner_only(final) if os.path.isdir(final) else None
    return {"placed": placed, "skipped": {k: v for k, v in skipped.items() if v}}


def _srm(home: str, name: str) -> Any:
    try:
        with open(os.path.join(home, ".config", "steam-rom-manager", "userData", name), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def launch(home: str, system: str, rom_file: str) -> dict[str, str] | None:
    """The shortcut this device's own Steam ROM Manager parser would make for a ROM: ``{exe, args, startDir}``.

    Reads ``userConfigurations.json`` for an enabled parser whose ROM folder ends in the system's folder,
    resolves the SRM variables ``userSettings.json`` defines, and fills the argument template. None
    when there is no such parser or anything is left unknown: no shortcut rather than a broken one."""
    parsers = _srm(home, "userConfigurations.json")
    settings = _srm(home, "userSettings.json")
    env = (settings or {}).get("environmentVariables") if isinstance(settings, dict) else None
    env = env if isinstance(env, dict) else {}
    known = {
        "${romsdirglobal}": str(env.get("romsDirectory") or ""),
        "${steamdirglobal}": str(env.get("steamDirectory") or ""),
        "${retroarchpath}": str(env.get("retroarchPath") or ""),
    }

    def resolve(text: str) -> str:
        for key, value in known.items():
            if value:
                text = text.replace(key, value)
        return text

    if not isinstance(parsers, list):
        return None
    for parser in parsers:
        if not isinstance(parser, dict) or parser.get("disabled"):
            continue
        folder = resolve(str(parser.get("romDirectory") or "")).rstrip("/")
        exe = parser.get("executable") or {}
        exe_path = resolve(str(exe.get("path") if isinstance(exe, dict) else exe or ""))
        if not folder or not exe_path or "${" in folder or os.path.basename(folder) != system:
            continue
        args = resolve(str(parser.get("executableArgs") or ""))
        for key, value in (
            ("${filePath}", rom_file),
            ("${fileName}", os.path.basename(rom_file)),
            ("${dir}", os.path.dirname(rom_file)),
        ):
            args = args.replace(key, value)
        if "${" in args or "${" in exe_path:
            return None
        return {"exe": exe_path, "args": args, "startDir": os.path.dirname(exe_path)}
    return None
