"""Receiving an emulator game (R26 stage 2, ADR-0087): staging, putting parts in place without replacing
anything, and the shortcut from this device's own Steam ROM Manager parser."""

from __future__ import annotations

import json
import os
import stat
import sys
from typing import Any

import pytest

from keepsake.replication import emuplan
from keepsake.replication import emureceive as rx

SHARE = {"share": "a" * 32, "root": "b" * 64, "bytes": 10}
OFFER_ID = "0123456789abcdef"


def offer(*parts: str) -> dict[str, Any]:
    return emuplan.validate(
        {
            "kind": "emulator",
            "id": OFFER_ID,
            "system": "switch",
            "unit": "Title",
            "emulator": "Eden",
            "shares": {p: SHARE for p in ("rom", *parts)},
        }
    )


def setup(tmp_path: Any) -> tuple[str, str]:
    home, roms = tmp_path / "home", tmp_path / "home" / "Emulation" / "roms"
    (roms / "switch").mkdir(parents=True)
    return str(home), str(roms)


def test_targets_stage_beside_where_parts_belong(tmp_path: Any) -> None:
    home, roms = setup(tmp_path)
    found = rx.targets(offer("app", "config", "keys"), OFFER_ID, home, roms)
    assert found["rom"] == os.path.join(roms, "switch", f".keepsake-emu-rom-{OFFER_ID}")
    assert found["app"] == os.path.join(home, "Applications", f".keepsake-emu-app-{OFFER_ID}")
    assert found["config"] == os.path.join(home, ".config/eden")  # straight in: there are no settings here
    assert os.path.dirname(found["keys"]) == os.path.dirname(os.path.join(home, ".local/share/eden/keys"))


def test_targets_never_replace_settings_and_need_the_rom_folder(tmp_path: Any) -> None:
    home, roms = setup(tmp_path)
    os.makedirs(os.path.join(home, ".config", "eden"))
    assert "config" not in rx.targets(offer("config"), OFFER_ID, home, roms)
    with pytest.raises(rx.EmuReceiveError, match="no ROM folder"):
        rx.targets(offer(), OFFER_ID, home, str(tmp_path / "elsewhere"))


def stage(path: str, files: dict[str, str]) -> None:
    for name, text in files.items():
        full = os.path.join(path, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)


def test_finish_places_missing_names_and_leaves_existing_ones(tmp_path: Any) -> None:
    home, roms = setup(tmp_path)
    o = offer("app", "keys")
    staged = rx.targets(o, OFFER_ID, home, roms)
    stage(staged["rom"], {"Title.nsp": "new", "Other.nsp": "theirs"})
    stage(os.path.join(roms, "switch"), {"Other.nsp": "mine"})
    stage(staged["app"], {"Eden.AppImage": "elf"})
    stage(staged["keys"], {"prod.keys": "k", "title.keys": "t"})
    stage(os.path.join(home, ".local/share/eden/keys"), {"prod.keys": "mine"})
    done = rx.finish(o, staged, home, roms)
    assert done["placed"]["rom"] == ["Title.nsp"] and done["skipped"]["rom"] == ["Other.nsp"]
    with open(os.path.join(roms, "switch", "Other.nsp"), encoding="utf-8") as handle:
        assert handle.read() == "mine"  # never replaced
    assert done["placed"]["keys"] == ["title.keys"] and done["skipped"]["keys"] == ["prod.keys"]
    with open(os.path.join(home, ".local/share/eden/keys", "prod.keys"), encoding="utf-8") as handle:
        assert handle.read() == "mine"
    for path in staged.values():
        assert not os.path.exists(path)  # staging cleared


@pytest.mark.skipif(sys.platform == "win32", reason="file modes need POSIX")
@pytest.mark.posix
def test_finish_sets_the_executable_bit_and_owner_only_keys(tmp_path: Any) -> None:
    home, roms = setup(tmp_path)
    o = offer("app", "keys")
    staged = rx.targets(o, OFFER_ID, home, roms)
    stage(staged["rom"], {"Title.nsp": "n"})
    stage(staged["app"], {"Eden.AppImage": "elf"})
    stage(staged["keys"], {"prod.keys": "k"})
    rx.finish(o, staged, home, roms)
    assert os.stat(os.path.join(home, "Applications", "Eden.AppImage")).st_mode & stat.S_IXUSR
    keys = os.path.join(home, ".local/share/eden/keys")
    assert stat.S_IMODE(os.stat(keys).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(os.path.join(keys, "prod.keys")).st_mode) == 0o600


def srm(home: str, parsers: list[dict[str, Any]], env: dict[str, str] | None = None) -> None:
    folder = os.path.join(home, ".config", "steam-rom-manager", "userData")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "userConfigurations.json"), "w", encoding="utf-8") as handle:
        json.dump(parsers, handle)
    with open(os.path.join(folder, "userSettings.json"), "w", encoding="utf-8") as handle:
        json.dump({"environmentVariables": env or {}}, handle)


def test_launch_from_this_devices_parser(tmp_path: Any) -> None:
    home = str(tmp_path / "home")
    srm(
        home,
        [
            {
                "disabled": True,
                "romDirectory": "${romsdirglobal}/switch",
                "executable": {"path": "/old.sh"},
                "executableArgs": "${filePath}",
            },
            {
                "romDirectory": "${romsdirglobal}/psx",
                "executable": {"path": "/tools/duck.sh"},
                "executableArgs": "${filePath}",
            },
            {
                "romDirectory": "${romsdirglobal}/switch",
                "executable": {"path": "/tools/launchers/eden.sh"},
                "executableArgs": '-f -g "${filePath}"',
            },
        ],
        {"romsDirectory": "/home/user/Emulation/roms"},
    )
    found = rx.launch(home, "switch", "/home/user/Emulation/roms/switch/Title.nsp")
    assert found == {
        "exe": "/tools/launchers/eden.sh",
        "args": '-f -g "/home/user/Emulation/roms/switch/Title.nsp"',
        "startDir": "/tools/launchers",
    }


def test_launch_refuses_unknown_templates_and_missing_parsers(tmp_path: Any) -> None:
    home = str(tmp_path / "home")
    assert rx.launch(home, "switch", "/r/Title.nsp") is None  # no SRM here
    srm(
        home,
        [
            {
                "romDirectory": "/r/switch",
                "executable": {"path": "/e.sh"},
                "executableArgs": "${someUnknown} ${filePath}",
            }
        ],
    )
    assert rx.launch(home, "switch", "/r/Title.nsp") is None
    srm(
        home,
        [{"romDirectory": "${romsdirglobal}/switch", "executable": {"path": "/e.sh"}, "executableArgs": "${filePath}"}],
    )
    assert rx.launch(home, "switch", "/r/Title.nsp") is None  # the folder variable is not defined here
