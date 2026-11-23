"""R29 stage 2 (ADR-0093): artwork for any non-Steam game, only the kinds it lacks, and Advisor's ProtonDB
line on the library badge, read only. Synthetic (P12)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from keepsake.advisor.service import Advisor
from keepsake.app import KeepsakeApp
from keepsake.installer.service import InstallerError
from test_app_ux import Device
from test_installer import KEY, FakeGrid, env  # noqa: F401 - the fixture

SHORTCUT = 3_900_000_001
STEAM_GAME = 4000123


def test_only_the_missing_kinds_of_artwork_are_queued(env: Any, monkeypatch: Any) -> None:  # noqa: F811
    from keepsake.installer import artwork

    installer, ops, *_ = env
    monkeypatch.setattr(artwork, "IMAGE_HOST_APPROVED", True)
    grid = FakeGrid()
    installer.art = artwork.SteamGridDB(lambda: KEY, grid.fetch, grid.fetch_to_file)
    offered = {item["assetType"] for item in installer.art.choose(77)}
    assert len(offered) >= 2
    wanted = min(offered)
    assert installer.queue_game_art(SHORTCUT, 77, {wanted}) == 1
    queued = ops.claim()
    assert queued["kind"] == "set-artwork" and queued["payload"]["assetType"] == wanted
    assert queued["payload"]["appid"] == SHORTCUT and queued["payload"]["file"].startswith(f"game{SHORTCUT}-")
    assert ops.claim() is None  # nothing else: the kinds the game has are left alone
    with pytest.raises(InstallerError, match="already has all"):
        installer.queue_game_art(SHORTCUT, 77, set())
    with pytest.raises(InstallerError, match="only non-Steam"):
        installer.queue_game_art(STEAM_GAME, 77, {wanted})


def test_the_missing_kinds_come_from_steams_grid_files() -> None:
    game = {
        "appid": SHORTCUT,
        "artwork": [f"{SHORTCUT}p.png", f"{SHORTCUT}_hero.jpg", f"{SHORTCUT}_icon.png", "other.png"],
    }
    assert KeepsakeApp._missing_art(game) == [3, 2]  # the wide cover and the logo
    assert KeepsakeApp._missing_art({"appid": SHORTCUT, "artwork": []}) == [0, 3, 1, 2]
    full = [f"{SHORTCUT}{s}.png" for s in ("p", "", "_hero", "_logo")]
    assert KeepsakeApp._missing_art({"appid": SHORTCUT, "artwork": full}) == []


def advisor(on: bool = True, header: Any = None, entry: Any = None) -> Any:
    lookups: list[int] = []

    def lookup(appid: int) -> Any:
        lookups.append(appid)
        return entry

    fake = SimpleNamespace(
        settings=lambda: {"sourceProtonDb": on},
        protondb=SimpleNamespace(header=lambda: header, lookup=lookup),
        _badge_cache={},
        lookups=lookups,
    )
    return fake


def test_the_protondb_line_is_read_only_and_looked_up_once() -> None:
    entry = {"n": 120, "works": 104, "handheld": 30}
    fake = advisor(header={"dump": "2026-11"}, entry=entry)
    assert Advisor.protondb_line(fake, 4000123) == "ProtonDB: 87% of 120 reports say it works"
    assert Advisor.protondb_line(fake, 4000123) == "ProtonDB: 87% of 120 reports say it works"
    assert fake.lookups == [4000123]  # cached
    one = advisor(header={"dump": "x"}, entry={"n": 1, "works": 1})
    assert Advisor.protondb_line(one, 5) == "ProtonDB: 100% of 1 report say it works"
    assert Advisor.protondb_line(advisor(on=False, header={"dump": "x"}, entry=entry), 4000123) is None
    no_index = advisor(header=None, entry=entry)
    assert Advisor.protondb_line(no_index, 4000123) is None and no_index.lookups == []  # never downloads
    assert Advisor.protondb_line(advisor(header={"dump": "x"}, entry=None), 4000123) is None
    assert Advisor.protondb_line(advisor(header={"dump": "x"}, entry={"n": 0, "works": 0}), 4000123) is None


def test_the_cache_is_bounded() -> None:
    fake = advisor(header={"dump": "x"}, entry={"n": 2, "works": 1})
    for appid in range(501):
        Advisor.protondb_line(fake, appid)
    assert len(fake._badge_cache) <= 500


@pytest.fixture
def device(tmp_path: Any) -> Any:
    from keepsake.store import LocalFolderStore

    return Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))


def test_the_badge_carries_the_protondb_line(device: Any) -> None:
    app = device.app
    app.advisor = SimpleNamespace(protondb_line=lambda appid: f"ProtonDB: line for {appid}")

    async def go() -> Any:
        return (
            await app.library_badge(4171510507),
            await app.library_badge(12345),
            await app.library_badge(SHORTCUT),
        )

    saves, only_pdb, shortcut = asyncio.run(go())
    assert saves == {"state": "off", "label": "Saves: not synced by Haversack"}  # a non-Steam game: no ProtonDB
    assert only_pdb == {"state": "info", "label": "ProtonDB: line for 12345"}
    assert shortcut is None

    async def steam_badge(appid: int) -> Any:
        return {"state": "synced", "label": "Saves: in step"}

    app._library_badge = steam_badge
    assert asyncio.run(app.library_badge(STEAM_GAME)) == {
        "state": "synced",
        "label": "Saves: in step",
        "detail": f"ProtonDB: line for {STEAM_GAME}",
    }
    app.advisor = None  # Advisor off: the badge is just the saves line
    assert asyncio.run(app.library_badge(STEAM_GAME)) == {"state": "synced", "label": "Saves: in step"}


def test_artwork_status_and_apply_for_a_game(device: Any) -> None:
    app = device.app

    async def go() -> Any:
        return await app.game_art_status(device.key)

    status = asyncio.run(go())
    assert status["nonSteam"] is True and status["available"] is (app.installer is not None)
    assert status["missing"] == ["cover", "wide cover", "background", "logo"]  # the synthetic game has no artwork
    with pytest.raises(ValueError, match="unknown game"):
        asyncio.run(app.game_art_status("nope"))
