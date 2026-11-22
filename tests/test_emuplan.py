"""Copying an emulator game (R26 stage 2, ADR-0087): the plan, the offer's checks and where parts land."""

from __future__ import annotations

import os
import stat
import sys
from typing import Any

import pytest

from keepsake.replication import emulators as emu
from keepsake.replication import emuplan

SHARE = {"share": "a" * 32, "root": "b" * 64, "bytes": 10}


def write(path: Any, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def home_with(tmp_path: Any) -> Any:
    home = tmp_path / "home"
    write(
        home / ".config" / "EmuDeck" / "settings.sh",
        f'romsPath="{home}/Emulation/roms"\nbiosPath="{home}/Emulation/bios"\n',
    )
    write(home / "Emulation" / "roms" / "switch" / "Title [0100ABCD00000000].nsp", "n" * 10)
    write(home / "Applications" / "Eden.AppImage", "elf")
    write(home / ".config" / "eden" / "qt-config.ini", "[UI]\n")
    write(home / ".local" / "share" / "eden" / "keys" / "prod.keys", "secret")
    (home / ".var" / "app" / "org.DolphinEmu.dolphin-emu").mkdir(parents=True)
    return home


def the_game(home: Any) -> emu.Game:
    (game,) = emu.games(str(home / "Emulation" / "roms"))
    return game


EDEN = {"name": "Eden", "system": "switch", "type": "appimage", "path": "Applications/Eden.AppImage"}


def test_plan_sends_only_what_the_other_device_lacks(tmp_path: Any) -> None:
    home = home_with(tmp_path)
    roms = str(home / "Emulation" / "roms")
    bare = {"systems": ["switch"], "emulators": [], "configs": []}
    p = emuplan.plan(str(home), roms, the_game(home), EDEN, bare, with_keys=False)
    assert set(p.roots) == {"rom", "app", "config"}  # no keys without the separate confirmation
    assert p.roots["app"].endswith("Eden.AppImage")
    assert os.path.normpath(p.roots["config"]).endswith(os.path.join(".config", "eden"))
    ready = {"systems": ["switch"], "emulators": ["Eden"], "configs": ["Eden"]}
    assert set(emuplan.plan(str(home), roms, the_game(home), EDEN, ready, with_keys=False).roots) == {"rom"}
    with_keys = emuplan.plan(str(home), roms, the_game(home), EDEN, ready, with_keys=True)
    assert set(with_keys.roots) == {"rom", "keys"}


def test_plan_refusals(tmp_path: Any) -> None:
    home = home_with(tmp_path)
    roms = str(home / "Emulation" / "roms")
    with pytest.raises(emuplan.EmuPlanError, match="no ROM folder"):
        emuplan.plan(str(home), roms, the_game(home), EDEN, {"systems": ["psx"]}, with_keys=False)
    dolphin = {"name": "Dolphin", "system": "gc", "type": "flatpak", "id": "org.DolphinEmu.dolphin-emu"}
    with pytest.raises(emuplan.EmuPlanError, match="Flatpak"):
        emuplan.plan(str(home), roms, the_game(home), dolphin, {"systems": ["switch"]}, with_keys=False)
    bad = emu.Game("../escape", "x", ["x"])
    with pytest.raises(emuplan.EmuPlanError):
        emuplan.plan(str(home), roms, bad, None, {"systems": ["../escape"]}, with_keys=False)


def offer(**over: Any) -> dict[str, Any]:
    base = {
        "kind": "emulator",
        "id": "0123456789abcdef",
        "system": "switch",
        "unit": "Title",
        "emulator": "Eden",
        "shares": {"rom": SHARE},
    }
    return {**base, **over}


def test_validate_accepts_a_good_offer_and_drops_paths() -> None:
    clean = emuplan.validate(
        offer(shares={"rom": SHARE, "app": SHARE, "keys": SHARE}, path="/home/deck/evil", romsPath="/tmp")
    )
    assert clean["keys"] is True and set(clean["shares"]) == {"rom", "app", "keys"}
    assert "path" not in clean and "romsPath" not in clean


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "game"},
        {"system": "../../etc"},
        {"system": "Switch"},
        {"unit": "a/../../b:c"},
        {"emulator": "EvilEmu"},
        {"shares": {}},
        {"shares": {"app": SHARE}},  # no ROM part
        {"shares": {"rom": SHARE, "shell": SHARE}},
        {"shares": {"rom": {"share": "x", "root": "b" * 64, "bytes": 1}}},
        {"shares": {"rom": SHARE, "app": SHARE}, "emulator": None},
        {"shares": {"rom": SHARE, "keys": SHARE}, "emulator": "PCSX2"},  # no key place for it
    ],
)
def test_validate_refuses(bad: dict[str, Any]) -> None:
    with pytest.raises(emuplan.EmuPlanError):
        emuplan.validate(offer(**bad))


def test_destinations_are_chosen_here(tmp_path: Any) -> None:
    home, roms = str(tmp_path / "h"), str(tmp_path / "r")
    clean = emuplan.validate(offer(shares={"rom": SHARE, "app": SHARE, "config": SHARE, "keys": SHARE}))
    assert emuplan.destination("rom", clean, home, roms) == os.path.join(roms, "switch")
    assert emuplan.destination("app", clean, home, roms) == os.path.join(home, "Applications")
    assert emuplan.destination("config", clean, home, roms) == os.path.join(home, ".config/eden")
    assert emuplan.destination("keys", clean, home, roms) == os.path.join(home, ".local/share/eden/keys")
    with pytest.raises(emuplan.EmuPlanError):
        emuplan.destination("shell", clean, home, roms)


def test_summary_carries_no_paths_or_key_details(tmp_path: Any) -> None:
    home = home_with(tmp_path)
    found = emuplan.summary(str(home))
    assert found["systems"] == ["switch"] and found["emulators"] == ["Dolphin", "Eden"] and found["configs"] == ["Eden"]
    assert set(found) == {"systems", "emulators", "configs", "games"}

    def strings(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [s for v in value.values() for s in strings(v)]
        if isinstance(value, (list, tuple)):
            return [s for v in value for s in strings(v)]
        return []

    for text in strings(found):
        assert str(home) not in text and "prod.keys" not in text and "secret" not in text and os.sep not in text


@pytest.mark.skipif(sys.platform == "win32", reason="file modes need POSIX")
@pytest.mark.posix
def test_keys_are_owner_only(tmp_path: Any) -> None:
    keys = tmp_path / "keys"
    write(keys / "sub" / "prod.keys", "k")
    emuplan.owner_only(str(keys))
    assert stat.S_IMODE(os.stat(keys).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(keys / "sub").st_mode) == 0o700
    assert stat.S_IMODE(os.stat(keys / "sub" / "prod.keys").st_mode) == 0o600
