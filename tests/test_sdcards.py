"""Which games are on which SD card, including cards not inserted (R29 stage 4, ADR-0096). Synthetic (P12)."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from keepsake import sdcards


def write(path: Any, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def manifest(library: Any, appid: int, name: str) -> None:
    write(
        library / "steamapps" / f"appmanifest_{appid}.acf",
        f'"AppState"\n{{\n "appid" "{appid}"\n "name" "{name}"\n "installdir" "{name}"\n}}\n',
    )


def setup(tmp_path: Any) -> tuple[Any, Any]:
    steam = tmp_path / "steam"
    card = tmp_path / "media" / "Card A"
    folders = f'''"libraryfolders"
{{
 "0" {{ "path" "{steam.as_posix()}" "label" "" "contentid" "111" "apps" {{ "4000001" "10" }} }}
 "1" {{ "path" "{card.as_posix()}" "label" "Card A" "contentid" "222"
   "apps" {{ "4000002" "20" "4000003" "30" "228980" "1" }} }}
 "2" {{ "path" "{(tmp_path / "media" / "Card B").as_posix()}" "label" "Card B" "contentid" "333"
   "apps" {{ "4000004" "40" }} }}
}}
'''
    write(steam / "steamapps" / "libraryfolders.vdf", folders)
    manifest(steam, 4000001, "Internal Game")
    manifest(card, 4000002, "Example Quest")
    manifest(card, 4000003, "another adventure")
    manifest(card, 228980, "Steamworks Common Redistributables")
    write(card / "Games" / "Indie" / "game.exe", "x")
    return steam, card


def test_cards_list_their_games_and_leave_out_the_internal_library_and_tools(tmp_path: Any) -> None:
    steam, card = setup(tmp_path)
    shortcuts = [
        {"name": "Indie Game", "exe": str(card / "Games" / "Indie" / "game.exe")},
        {"name": "Elsewhere", "exe": str(tmp_path / "home" / "game.exe")},
        {"name": "No program", "exe": None},
    ]
    cards = sdcards.SdCards(str(tmp_path / "runtime"), clock=lambda: 1_800_000_000).scan([str(steam)], shortcuts)
    assert [c["label"] for c in cards] == ["Card A", "Card B"]  # inserted first; never the internal one
    a, b = cards
    assert a["inserted"] is True and a["lastSeen"] == 1_800_000_000
    assert a["games"] == ["another adventure", "Example Quest"]  # names from the card, tools left out
    assert a["shortcuts"] == ["Indie Game"]
    assert b == {"label": "Card B", "inserted": False, "lastSeen": None, "games": ["App 4000004"], "shortcuts": []}


def test_a_card_that_is_out_keeps_its_names(tmp_path: Any) -> None:
    steam, card = setup(tmp_path)
    cards = sdcards.SdCards(str(tmp_path / "runtime"), clock=lambda: 1_800_000_000)
    cards.scan([str(steam)], [{"name": "Indie Game", "exe": str(card / "Games" / "Indie" / "game.exe")}])
    shutil.rmtree(card)  # the card is taken out; Steam keeps its entry
    later = sdcards.SdCards(str(tmp_path / "runtime"), clock=lambda: 1_900_000_000).scan([str(steam)], [])
    a = next(c for c in later if c["label"] == "Card A")
    assert a["inserted"] is False and a["lastSeen"] == 1_800_000_000
    assert a["games"] == ["another adventure", "Example Quest"] and a["shortcuts"] == ["Indie Game"]


def test_nothing_on_the_card_or_in_steam_is_changed(tmp_path: Any) -> None:
    steam, _card = setup(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    sdcards.SdCards(str(tmp_path / "runtime")).scan([str(steam)], [])
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and "runtime" not in p.parts}
    assert after == before
    assert json.loads((tmp_path / "runtime" / sdcards.RECORD).read_text())["222"]["label"] == "Card A"


def test_missing_or_broken_files_give_an_empty_list(tmp_path: Any) -> None:
    assert sdcards.SdCards(str(tmp_path / "runtime")).scan([str(tmp_path / "none")], []) == []
    write(tmp_path / "steam" / "steamapps" / "libraryfolders.vdf", "{ not vdf")
    assert sdcards.SdCards(str(tmp_path / "runtime")).scan([str(tmp_path / "steam")], []) == []
    write(tmp_path / "runtime" / sdcards.RECORD, "[1, 2]")  # a broken record is ignored, not fatal
    steam, _card = setup(tmp_path)
    assert len(sdcards.SdCards(str(tmp_path / "runtime")).scan([str(steam)], [])) == 2


def test_a_card_seen_through_two_steam_roots_is_listed_once(tmp_path: Any) -> None:
    steam, _card = setup(tmp_path)
    other = tmp_path / "steam2"
    os.makedirs(other / "steamapps")
    shutil.copy(steam / "steamapps" / "libraryfolders.vdf", other / "steamapps" / "libraryfolders.vdf")
    labels = [c["label"] for c in sdcards.SdCards(str(tmp_path / "runtime")).scan([str(steam), str(other)], [])]
    assert labels.count("Card A") == 1


def test_inserted_cards_come_first(tmp_path: Any) -> None:
    steam, card = setup(tmp_path)
    shutil.rmtree(card)
    manifest(tmp_path / "media" / "Card B", 4000004, "Bee Game")
    assert [(c["label"], c["inserted"]) for c in sdcards.SdCards(str(tmp_path / "runtime")).scan([str(steam)], [])] == [
        ("Card B", True),
        ("Card A", False),
    ]
