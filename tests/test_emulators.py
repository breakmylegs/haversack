"""Emulator setups and games (R26 stage 1, ADR-0087): detection, grouping and counting, on synthetic trees."""

from __future__ import annotations

import builtins
import os
from typing import Any

from keepsake.replication import emulators as emu


def write(path: Any, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def emudeck_home(tmp_path: Any) -> Any:
    home = tmp_path / "home"
    write(
        home / ".config" / "EmuDeck" / "settings.sh",
        f'emulationPath="{home}/Emulation"\nromsPath="{home}/Emulation/roms"\nbiosPath="{home}/Emulation/bios"\n',
    )
    roms = home / "Emulation" / "roms"
    write(roms / "psx" / "Game A (Disc 1).cue", 'FILE "Game A (Disc 1).bin" BINARY\n')
    write(roms / "psx" / "Game A (Disc 1).bin", "a" * 100)
    write(roms / "psx" / "Game A (Disc 2).cue", 'FILE "Game A (Disc 2).bin" BINARY\n')
    write(roms / "psx" / "Game A (Disc 2).bin", "b" * 100)
    write(roms / "psx" / "Game A.m3u", "Game A (Disc 1).cue\nGame A (Disc 2).cue\n")
    write(roms / "psx" / "Single.chd", "c" * 50)
    write(roms / "psx" / "systeminfo.txt", "about psx")
    write(roms / "dreamcast" / "Disc.gdi", '2\n1 0 4 2352 "track01.bin" 0\n2 600 0 2352 track02.raw 0\n')
    write(roms / "dreamcast" / "track01.bin", "t1")
    write(roms / "dreamcast" / "track02.raw", "t2")
    write(roms / "ps3" / "Big Game" / "PS3_GAME" / "PARAM.SFO", "sfo")
    write(roms / "ps3" / "Big Game" / "PS3_GAME" / "USRDIR" / "EBOOT.BIN", "e" * 10)
    write(roms / "wiiu" / "Some Title" / "code" / "app.rpx", "r")
    (roms / "wiiu" / "Some Title" / "content").mkdir(parents=True)
    (roms / "wiiu" / "Some Title" / "meta").mkdir(parents=True)
    write(roms / "switch" / "Title [0100ABCD00000000].nsp", "n")
    write(home / "Emulation" / "bios" / "scph5501.bin", "secret bios")
    write(home / ".config" / "Ryujinx" / "system" / "prod.keys", "secret keys")
    write(home / ".config" / "Ryujinx" / "system" / "title.keys", "secret keys")
    write(home / "Applications" / "rpcs3.AppImage", "elf")
    (home / ".var" / "app" / "org.DolphinEmu.dolphin-emu").mkdir(parents=True)
    return home


def test_emudeck_paths_from_settings_and_defaults(tmp_path: Any) -> None:
    home = emudeck_home(tmp_path)
    paths = emu.emudeck(str(home))
    assert paths and os.path.normpath(paths["romsPath"]).endswith(os.path.join("Emulation", "roms"))
    bare = tmp_path / "bare"
    (bare / "Emulation" / "roms").mkdir(parents=True)
    assert emu.emudeck(str(bare))["biosPath"].endswith("bios")  # type: ignore[index]
    assert emu.emudeck(str(tmp_path / "nothing")) is None


def test_retrodeck_from_its_json_or_folder(tmp_path: Any) -> None:
    home = tmp_path / "home"
    write(
        home / ".var" / "app" / "net.retrodeck.retrodeck" / "config" / "retrodeck" / "retrodeck.json",
        '{"paths": {"roms_path": "/data/rd/roms", "bios_path": "/data/rd/bios"}}',
    )
    assert emu.retrodeck(str(home)) == {"romsPath": "/data/rd/roms", "biosPath": "/data/rd/bios"}
    plain = tmp_path / "plain"
    (plain / "retrodeck" / "roms").mkdir(parents=True)
    assert emu.retrodeck(str(plain))["romsPath"].endswith(os.path.join("retrodeck", "roms"))  # type: ignore[index]
    assert emu.retrodeck(str(tmp_path / "none")) is None


def test_games_are_grouped_one_unit_each(tmp_path: Any) -> None:
    home = emudeck_home(tmp_path)
    found = {(g.system, g.name): g for g in emu.games(str(home / "Emulation" / "roms"))}
    psx = found[("psx", "Game A")]
    assert sorted(psx.files) == sorted(
        ["Game A.m3u", "Game A (Disc 1).cue", "Game A (Disc 1).bin", "Game A (Disc 2).cue", "Game A (Disc 2).bin"]
    )
    assert ("psx", "Game A (Disc 1)") not in found  # claimed by the playlist
    assert ("psx", "Single") in found and ("psx", "systeminfo") not in found
    assert sorted(found[("dreamcast", "Disc")].files) == ["Disc.gdi", "track01.bin", "track02.raw"]
    assert found[("ps3", "Big Game")].files == ["Big Game"] and found[("ps3", "Big Game")].size > 0
    assert found[("wiiu", "Some Title")].files == ["Some Title"]
    assert ("switch", "Title [0100ABCD00000000]") in found


def test_a_cue_cannot_reach_outside_the_rom_folder(tmp_path: Any) -> None:
    roms = tmp_path / "roms"
    write(roms / "psx" / "Evil.cue", 'FILE "../../outside.bin" BINARY\n')
    write(tmp_path / "outside.bin", "o")
    (game,) = emu.games(str(roms))
    assert game.files == ["Evil.cue"]


def test_emulators_detected_by_appimage_or_flatpak(tmp_path: Any) -> None:
    home = emudeck_home(tmp_path)
    found = {e["name"]: e for e in emu.emulators(str(home))}
    assert found["RPCS3"]["type"] == "appimage" and found["Dolphin"]["type"] == "flatpak"
    assert "Cemu" not in found


def test_keys_and_firmware_are_counted_never_opened(tmp_path: Any, monkeypatch: Any) -> None:
    home = emudeck_home(tmp_path)
    real_open = builtins.open

    def guarded(path: Any, *args: Any, **kwargs: Any) -> Any:
        text = str(path)
        assert "prod.keys" not in text and "title.keys" not in text and "scph5501" not in text, f"opened {text}"
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded)
    found = emu.scan(str(home))
    assert found["secrets"] == {"switch": 2, "bios": 1}
    assert found["setups"] == ["emudeck"]
    assert found["perSystem"]["psx"] == 2 and found["perSystem"]["ps3"] == 1


def test_scan_of_an_empty_home(tmp_path: Any) -> None:
    found = emu.scan(str(tmp_path))
    assert found == {"setups": [], "emulators": [], "games": [], "perSystem": {}, "secrets": {}}


def test_device_check_carries_counts_only(tmp_path: Any) -> None:
    import asyncio

    from keepsake import devicechecks

    home = emudeck_home(tmp_path)
    found = emu.scan(str(home))

    async def probe() -> dict[str, Any]:
        return {
            "setups": found["setups"],
            "emulators": [{"name": e["name"], "type": e["type"]} for e in found["emulators"]],
            "perSystem": found["perSystem"],
            "secrets": found["secrets"],
        }

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"emulator-setup": probe})
    outcome = asyncio.run(devicechecks.run("emulator-setup", ctx))
    assert outcome["status"] == "pass" and "6 games across 5 systems" in outcome["found"]
    text = repr(outcome)
    assert "Game A" not in text and "Big Game" not in text and "prod.keys" not in text
