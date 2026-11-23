"""Keepsake becomes Haversack (R27, ADR-0089): held while the old plugin is installed, then the settings
and data are copied, checked, never overwriting, with the originals kept."""

from __future__ import annotations

import json
import os
import stat
import sys
from typing import Any

import pytest

from keepsake import rename

PLENTY = lambda path: 1 << 40  # noqa: E731 - free space for tests


def write(path: Any, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def homebrew(tmp_path: Any, old_plugin: bool = False) -> Any:
    home = tmp_path / "homebrew"
    write(home / "settings" / "Keepsake" / "settings.json", '{"deviceName": "Handheld A"}')
    write(home / "settings" / "Keepsake" / "tokens" / "onedrive.json", "secret token")
    write(home / "data" / "Keepsake" / "state.db", "state")
    write(home / "logs" / "Keepsake" / "keepsake.log", "old log")
    if old_plugin:
        write(home / "plugins" / "Keepsake" / "plugin.json", '{"name": "Keepsake"}')
    return home


def test_homebrew_from_the_settings_folder(tmp_path: Any) -> None:
    assert rename.homebrew(str(tmp_path / "homebrew" / "settings" / "Haversack")) == str(tmp_path / "homebrew")


def test_held_and_nothing_copied_while_the_old_plugin_is_installed(tmp_path: Any) -> None:
    home = homebrew(tmp_path, old_plugin=True)
    write(home / "plugins" / "keepsake-helper" / "plugin.json", '{"name": "Keepsake Helper"}')
    found = rename.state(str(home))
    assert found["hold"] is True and found["oldInstalled"] is True and found["oldHelper"] is True
    with pytest.raises(rename.MoveError):
        rename.move(str(home), free=PLENTY)
    assert not (home / "settings" / "Haversack").exists()
    (home / "plugins" / "Keepsake" / "plugin.json").unlink()
    assert rename.state(str(home))["hold"] is False


def test_the_move_copies_checks_and_records(tmp_path: Any) -> None:
    home = homebrew(tmp_path)
    assert rename.needed(str(home))
    report = rename.move(str(home), clock=lambda: 1_800_000_000, free=PLENTY)
    assert report["files"] == 3 and report["kept"] == []
    assert (home / "settings" / "Haversack" / "settings.json").read_text() == '{"deviceName": "Handheld A"}'
    assert (home / "settings" / "Haversack" / "tokens" / "onedrive.json").read_text() == "secret token"
    assert (home / "data" / "Haversack" / "state.db").read_text() == "state"
    assert not (home / "logs" / "Haversack").exists()  # logs are not moved
    marker = json.loads((home / "settings" / "Haversack" / rename.MARKER).read_text())
    assert marker["from"] == "Keepsake" and marker["files"] == 3
    assert rename.state(str(home))["moved"]["from"] == "Keepsake"
    assert not rename.needed(str(home))  # never repeated


def test_the_originals_are_never_changed(tmp_path: Any) -> None:
    home = homebrew(tmp_path)
    before = {p: p.read_text() for p in home.rglob("*") if p.is_file() and "Keepsake" in p.parts}
    rename.move(str(home), free=PLENTY)
    for path, text in before.items():
        assert path.read_text() == text
    assert (home / "settings" / "Keepsake" / rename.NOTE).exists()  # only a note is added beside them


def test_nothing_in_haversack_is_overwritten(tmp_path: Any) -> None:
    home = homebrew(tmp_path)
    write(home / "settings" / "Haversack" / "settings.json", '{"deviceName": "already here"}')
    report = rename.move(str(home), free=PLENTY)
    assert (home / "settings" / "Haversack" / "settings.json").read_text() == '{"deviceName": "already here"}'
    assert [k.replace(os.sep, "/") for k in report["kept"]] == ["settings/settings.json"]


def test_a_bad_copy_stops_the_move_before_it_is_recorded(tmp_path: Any, monkeypatch: Any) -> None:
    home = homebrew(tmp_path)
    (home / "settings" / "Haversack").mkdir(parents=True)  # Decky makes the folder before the plugin starts
    real = rename._digest
    monkeypatch.setattr(rename, "_digest", lambda path: "bad" if "Haversack" in str(path) else real(path))
    with pytest.raises(rename.MoveError):
        rename.move(str(home), free=PLENTY)
    assert not (home / "settings" / "Haversack" / rename.MARKER).exists()
    assert rename.needed(str(home))  # tried again next time


def test_not_enough_room_copies_nothing(tmp_path: Any) -> None:
    home = homebrew(tmp_path)
    with pytest.raises(rename.MoveError, match="free"):
        rename.move(str(home), free=lambda path: rename.SPARE + 44)  # the files need 28 + 12 + 5 bytes
    assert not (home / "settings" / "Haversack").exists() and not (home / "data" / "Haversack").exists()
    rename.move(str(home), free=lambda path: rename.SPARE + 45)  # exactly enough
    assert not rename.needed(str(home))


def test_the_gate_holds_then_moves_then_starts(tmp_path: Any) -> None:
    home = homebrew(tmp_path, old_plugin=True)
    moves: list[str] = []
    gate = rename.Gate(
        str(home / "settings" / "Haversack"), mover=lambda h: moves.append(h) or rename.move(h, free=PLENTY)
    )
    assert gate.ready() is False and moves == []  # held: nothing copied while Keepsake is installed
    assert gate.status(False)["hold"] is True
    (home / "plugins" / "Keepsake" / "plugin.json").unlink()
    assert gate.ready() is True and moves == [str(home)]
    assert gate.ready() is True and len(moves) == 1  # recorded, so never repeated
    found = gate.status(True)
    assert found["started"] is True and found["moved"]["files"] == 3 and found["error"] == ""


def test_the_gate_fails_closed_when_the_copy_fails(tmp_path: Any) -> None:
    home = homebrew(tmp_path)

    def broken(h: str) -> None:
        raise rename.MoveError("needs 9 bytes free to copy, 1 are free")

    gate = rename.Gate(str(home / "settings" / "Haversack"), mover=broken)
    assert gate.ready() is False and "free" in gate.status(False)["error"]
    gate._move = lambda h: rename.move(h, free=PLENTY)
    assert gate.ready() is True and gate.error == ""  # tried again, and the error clears


def test_after_the_way_back_the_newer_keepsake_data_moves_again(tmp_path: Any) -> None:
    home = homebrew(tmp_path)
    rename.move(str(home), free=PLENTY)
    marker = home / "settings" / "Haversack" / rename.MARKER
    write(home / "settings" / "Haversack" / "settings.json", '{"deviceName": "used in Haversack"}')
    for path in home.rglob("*"):
        if path.is_file() and "Keepsake" in path.parts:
            os.utime(path, (1_700_000_000, 1_700_000_000))
    os.utime(marker, (1_750_000_000, 1_750_000_000))
    assert not rename.needed(str(home))  # Keepsake's files are no newer than the move
    write(home / "settings" / "Keepsake" / rename.NOTE, "{}")  # the move's own note does not count
    os.utime(home / "settings" / "Keepsake" / rename.NOTE, (1_780_000_000, 1_780_000_000))
    assert not rename.needed(str(home))
    # The way back: Keepsake is used again, then the user updates to Haversack again.
    write(home / "settings" / "Keepsake" / "settings.json", '{"deviceName": "used in Keepsake again"}')
    os.utime(home / "settings" / "Keepsake" / "settings.json", (1_780_000_000, 1_780_000_000))
    assert rename.needed(str(home))
    report = rename.move(str(home), clock=lambda: 1_800_000_100, free=PLENTY)
    assert (home / "settings" / "Haversack" / "settings.json").read_text() == '{"deviceName": "used in Keepsake again"}'
    aside = home / "settings" / "Haversack.before-20270115T080140Z"
    assert (aside / "settings.json").read_text() == '{"deviceName": "used in Haversack"}'  # set aside, never deleted
    assert (home / "data" / "Haversack.before-20270115T080140Z" / "state.db").exists()
    assert [p.replace(os.sep, "/") for p in report["setAside"]] == [
        "settings/Haversack.before-20270115T080140Z",
        "data/Haversack.before-20270115T080140Z",
    ]
    assert not rename.needed(str(home))  # recorded again
    assert not (home / "settings" / "Haversack" / rename.NOTE).exists()  # Keepsake's note is never copied


def test_not_enough_room_after_the_way_back_sets_nothing_aside(tmp_path: Any) -> None:
    home = homebrew(tmp_path)
    rename.move(str(home), free=PLENTY)
    os.utime(home / "settings" / "Haversack" / rename.MARKER, (1_700_000_000, 1_700_000_000))
    with pytest.raises(rename.MoveError):
        rename.move(str(home), free=lambda path: rename.SPARE + 44)  # all 45 bytes must be copied again
    assert (home / "settings" / "Haversack" / rename.MARKER).exists()
    assert not list((home / "settings").glob("Haversack.before-*"))
    assert not (home / "settings" / "Haversack" / rename.NOTE).exists()  # Keepsake's note is never copied


def test_nothing_to_move_on_a_fresh_install(tmp_path: Any) -> None:
    home = tmp_path / "homebrew"
    (home / "settings" / "Haversack").mkdir(parents=True)
    assert not rename.needed(str(home))
    assert rename.state(str(home)) == {"moved": None, "oldInstalled": False, "oldHelper": False, "hold": False}


@pytest.mark.skipif(sys.platform == "win32", reason="file modes need POSIX")
@pytest.mark.posix
def test_owner_only_files_stay_owner_only(tmp_path: Any) -> None:
    home = homebrew(tmp_path)
    token = home / "settings" / "Keepsake" / "tokens" / "onedrive.json"
    os.chmod(token, 0o600)
    rename.move(str(home), free=PLENTY)
    assert stat.S_IMODE(os.stat(home / "settings" / "Haversack" / "tokens" / "onedrive.json").st_mode) == 0o600
