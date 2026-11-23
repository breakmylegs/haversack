"""R18 (ADR-0081): Keepsake's badge in Steam's library, and artwork for streaming tiles. Synthetic (P12)."""

import asyncio

import pytest

from keepsake.installer.service import InstallerError
from test_app_ux import Device
from test_installer import KEY, FakeGrid, env  # noqa: F401 - the fixture

STREAMED = 3_900_000_001  # a non-Steam game installed on another device (a shortcut-style app ID)
STEAM_GAME = 4000123


@pytest.fixture
def device(tmp_path):
    from keepsake.store import LocalFolderStore

    return Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))


def report(app):
    return app.remote_copies.save_report(
        [
            {"appid": STREAMED, "name": "Far Game", "steam": "remote", "clients": ["Legion Go 2"]},
            {"appid": STEAM_GAME, "name": "A Steam Game", "steam": "remote", "clients": ["PC"]},
            {"appid": 4171510507, "name": "Example Quest", "steam": "local"},
        ]
    )


def test_badges_show_the_saves_or_where_a_tile_streams_from(device):
    a = device

    async def go():
        report(a.app)
        off = await a.app.library_badge(4171510507)
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"progress")
        await a.app.sync_push(a.key)
        synced = await a.app.library_badge(4171510507)
        streaming = await a.app.library_badge(STREAMED)
        unknown = await a.app.library_badge(12345)
        a.app.settings.set("libraryBadges", False)
        hidden = await a.app.library_badge(4171510507)
        return off, synced, streaming, unknown, hidden

    off, synced, streaming, unknown, hidden = asyncio.run(go())
    assert off == {"state": "off", "label": "Saves: not synced by Haversack"}
    assert synced == {"state": "synced", "label": "Saves: in step"}
    assert streaming == {"state": "streaming", "label": "Streams from Legion Go 2"}
    assert unknown is None and hidden is None


def test_a_conflict_shows_on_the_badge(device):
    a = device

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        state = a.app._sync().state
        gk = (await a.app._matched())[0][2]
        state.update(gk, conflict={"kind": "fork", "heads": [], "localFiles": 1, "raised": 1.0})
        return await a.app.library_badge(4171510507)

    assert asyncio.run(go()) == {"state": "conflict", "label": "Saves: conflict, open Haversack"}


def test_only_non_steam_streaming_tiles_are_offered_artwork(device):
    a = device
    report(a.app)
    tiles = asyncio.run(a.app.installer_stream_tiles())
    assert tiles == [{"appid": STREAMED, "name": "Far Game", "devices": ["Legion Go 2"]}]


def test_stream_art_is_queued_for_steam(env, monkeypatch):  # noqa: F811
    from keepsake.installer import artwork

    installer, ops, _tmp_path, _prefix, _library = env
    monkeypatch.setattr(artwork, "IMAGE_HOST_APPROVED", True)
    grid = FakeGrid()
    installer.art = artwork.SteamGridDB(lambda: KEY, grid.fetch, grid.fetch_to_file)
    assert installer.search_titles("Example Quest")[0]["id"] == 77
    assert installer.queue_stream_art(STREAMED, 77) == 3
    queued = [ops.claim() for _ in range(3)]
    assert {o["payload"]["appid"] for o in queued} == {STREAMED}
    assert [o["kind"] for o in queued] == ["set-artwork"] * 3
    claimed = {**queued[0], "module": "installer", "state": "claimed"}
    assert installer.staged_file(claimed).endswith(queued[0]["payload"]["file"])  # the image Steam is handed
    with pytest.raises(InstallerError, match="only a non-Steam game"):
        installer.queue_stream_art(STEAM_GAME, 77)


def test_the_app_refuses_an_app_that_is_not_a_streaming_tile(device):
    a = device
    report(a.app)
    with pytest.raises(ValueError, match="not a streaming tile"):
        asyncio.run(a.app.installer_stream_art_apply(4171510507, 77))


def test_the_badge_setting_is_checked():
    from keepsake.settings import SettingsError, _validate

    assert _validate("libraryBadges", False) is False
    with pytest.raises(SettingsError):
        _validate("libraryBadges", "yes")


def test_a_newer_save_elsewhere_shows_on_the_badge(device):
    a = device

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        gk = (await a.app._matched())[0][2]
        a.app._sync().state.update(gk, base="old", newer={"snapId": "new", "device": "Legion Go 2", "created": "x"})
        return await a.app.library_badge(4171510507)

    assert asyncio.run(go()) == {"state": "newer", "label": "Saves: newer on Legion Go 2"}
