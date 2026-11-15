"""Sync through the app on one device, against the local test store."""

import asyncio

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths

APPID = 4171510507
KEY = f"shortcut:7:{APPID}"


@pytest.fixture
def setup(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    root = make_fake_steam(
        home, users={"7": [shortcut_entry(-123456789, "Example Quest", "/g.exe")]}, prefixes=[(None, APPID)]
    )
    saves = root / "steamapps/compatdata" / str(APPID) / "pfx/drive_c/users/steamuser/AppData/Local/ExampleQuest"
    saves.mkdir(parents=True)
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    events = []

    async def emit(event, *args):
        events.append((event, args))

    app = KeepsakeApp(
        paths, emit=emit, proc_root=str(tmp_path / "proc"), version="0.7.0", home=str(home), auto_refresh_manifest=False
    )
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        '---\nExample Quest:\n  files:\n    "<winLocalAppData>/ExampleQuest":\n      tags:\n        - save\n'
    )
    app.manifest.import_file(str(manifest_file))
    return app, saves, events


def test_pull_push_status_and_idle(setup):
    app, saves, events = setup

    async def run():
        first = await app.sync_pull(KEY)
        (saves / "slot.sav").write_bytes(b"progress")
        pushed = await app.sync_push(KEY)
        status = await app.sync_status(KEY)
        idle_disabled = await app.idle_pass()
        await app.update_game_config(KEY, {"enabled": True})
        await app.sync_pull(KEY)  # opens a session...
        (saves / "slot.sav").write_bytes(b"more progress")
        idle = await app.idle_pass()  # ...which the idle pass recovers, since the game is not running
        return first, pushed, status, idle_disabled, idle

    first, pushed, status, idle_disabled, idle = asyncio.run(run())
    assert first["reason"] == "no-cloud-snapshots"
    assert pushed["status"] == "published"
    assert status["available"] is True and status["base"] == pushed["snapId"] and status["sessionOpen"] is None
    assert idle_disabled == []  # games are opt-in
    assert idle[0]["key"] == KEY
    assert ("keepsake_toast", ("Recovered missed exit backup for Example Quest",)) in events


def test_status_explains_unmatched_game(setup):
    app, _, _ = setup
    app.manifest._cache = {"schema": 1, "games": {}, "titles": {}, "steam": {}, "steamNoData": []}
    status = asyncio.run(app.sync_status(KEY))
    assert status["available"] is False and "match" in status["reason"]
