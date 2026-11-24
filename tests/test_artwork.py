"""Artwork for any non-Steam game, only the kinds it lacks (ADR-0093), and for streaming tiles (ADR-0081).

Kept through the strip (ADR-0098) from the library extras and badge tests. Synthetic (P12).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from helpers import Device
from keepsake.app import KeepsakeApp
from keepsake.installer.service import InstallerError
from test_installer import KEY, FakeGrid, env  # noqa: F401 - the fixture

SHORTCUT = 3_900_000_001  # a non-Steam game (a shortcut-style app ID)
STEAM_GAME = 4000123


@pytest.fixture
def device(tmp_path: Any) -> Device:
    return Device(tmp_path, "a", 4171510507)


def report(app: KeepsakeApp) -> None:
    app.remote_copies.save_report(
        [
            {"appid": SHORTCUT, "name": "Far Game", "steam": "remote", "clients": ["Legion Go 2"]},
            {"appid": STEAM_GAME, "name": "A Steam Game", "steam": "remote", "clients": ["Other"]},
            {"appid": 4171510507, "name": "Example Quest", "steam": "local"},
        ]
    )


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


def test_artwork_status_for_a_game(device: Device) -> None:
    app = device.app
    status = asyncio.run(app.game_art_status(device.key))
    assert status["nonSteam"] is True and status["available"] is (app.installer is not None)
    assert status["missing"] == ["cover", "wide cover", "background", "logo"]  # the synthetic game has no artwork
    with pytest.raises(ValueError, match="unknown game"):
        asyncio.run(app.game_art_status("nope"))


def test_only_non_steam_streaming_tiles_are_offered_artwork(device: Device) -> None:
    report(device.app)
    tiles = asyncio.run(device.app.installer_stream_tiles())
    assert tiles == [{"appid": SHORTCUT, "name": "Far Game", "devices": ["Legion Go 2"]}]


def test_stream_art_is_queued_for_steam(env: Any, monkeypatch: Any) -> None:  # noqa: F811
    from keepsake.installer import artwork

    installer, ops, _tmp_path, _prefix, _library = env
    monkeypatch.setattr(artwork, "IMAGE_HOST_APPROVED", True)
    grid = FakeGrid()
    installer.art = artwork.SteamGridDB(lambda: KEY, grid.fetch, grid.fetch_to_file)
    assert installer.search_titles("Example Quest")[0]["id"] == 77
    assert installer.queue_stream_art(SHORTCUT, 77) == 3
    queued = [ops.claim() for _ in range(3)]
    assert {o["payload"]["appid"] for o in queued} == {SHORTCUT}
    assert [o["kind"] for o in queued] == ["set-artwork"] * 3
    claimed = {**queued[0], "module": "installer", "state": "claimed"}
    assert installer.staged_file(claimed).endswith(queued[0]["payload"]["file"])  # the image Steam is handed
    with pytest.raises(InstallerError, match="only a non-Steam game"):
        installer.queue_stream_art(STEAM_GAME, 77)


def test_the_app_refuses_an_app_that_is_not_a_streaming_tile(device: Device) -> None:
    report(device.app)
    with pytest.raises(ValueError, match="not a streaming tile"):
        asyncio.run(device.app.installer_stream_art_apply(4171510507, 77))
