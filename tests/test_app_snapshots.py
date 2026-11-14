import asyncio
import os

import pytest

from helpers import make_fake_steam, shortcut_entry, write_fake_proc
from keepsake import discovery
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths
from keepsake.snapshot import SnapshotError

APPID = 4171510507
KEY = f"shortcut:7:{APPID}"
MANIFEST = """---
Example Quest:
  files:
    "<winLocalAppData>/ExampleQuest/Saves":
      tags:
        - save
"""


@pytest.fixture
def app_and_save(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    root = make_fake_steam(
        home, users={"7": [shortcut_entry(-123456789, "Example Quest", "/g.exe")]}, prefixes=[(None, APPID)]
    )
    saves = root / "steamapps/compatdata" / str(APPID) / "pfx/drive_c/users/steamuser/AppData/Local/ExampleQuest/Saves"
    saves.mkdir(parents=True)
    (saves / "slot1.sav").write_bytes(b"chapter 1")
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="0.5.0", home=str(home), auto_refresh_manifest=False
    )
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(MANIFEST)
    app.manifest.import_file(str(manifest_file))
    return app, saves, tmp_path


def test_snapshot_restore_and_undo_through_the_app(app_and_save):
    app, saves, _ = app_and_save

    async def run():
        first = await app.snapshot_game(KEY)
        (saves / "slot1.sav").write_bytes(b"chapter 2")
        (saves / "slot2.sav").write_bytes(b"new slot")
        second = await app.snapshot_game(KEY)
        listing = await app.list_snapshots(KEY)
        restored = await app.restore_snapshot(KEY, first["snapId"])
        after_restore = sorted(os.listdir(saves)), (saves / "slot1.sav").read_bytes()
        undone = await app.undo_restore(KEY, restored["prerestore"])
        return first, second, listing, restored, after_restore, undone

    first, second, listing, restored, after_restore, undone = asyncio.run(run())
    assert first["status"] == "published" and second["status"] == "published"
    assert listing["gameKey"] == "example-quest"
    assert [s["snapId"] for s in listing["snapshots"]] == [second["snapId"], first["snapId"]]
    assert listing["snapshots"][0]["base"] is True
    assert restored["status"] == "restored"
    assert after_restore == (["slot1.sav"], b"chapter 1")
    assert undone["status"] == "restored"
    assert sorted(os.listdir(saves)) == ["slot1.sav", "slot2.sav"]
    assert (saves / "slot1.sav").read_bytes() == b"chapter 2"


def test_restore_refused_while_game_process_runs(app_and_save):
    app, saves, tmp_path = app_and_save
    first = asyncio.run(app.snapshot_game(KEY))
    (saves / "slot1.sav").write_bytes(b"changed")
    uid = os.getuid() if hasattr(os, "getuid") else -1
    write_fake_proc(str(tmp_path / "proc"), 900, 1, "game.exe", uid=uid, env={"SteamAppId": str(APPID)})
    with pytest.raises(SnapshotError, match="running"):
        asyncio.run(app.restore_snapshot(KEY, first["snapId"]))
    assert (saves / "slot1.sav").read_bytes() == b"changed"


def test_snapshots_blocked_after_prefix_mismatch(app_and_save):
    app, _, _ = app_and_save
    discovery.record_cross_check(app.paths.runtime_dir, KEY, {"status": "mismatch", "observed": ["/x"]}, "/y")
    with pytest.raises(ValueError, match="blocked"):
        asyncio.run(app.snapshot_game(KEY))


def test_unmatched_game_cannot_be_snapshotted(app_and_save):
    app, _, _ = app_and_save
    app.manifest._cache = {"schema": 1, "games": {}, "titles": {}, "steam": {}, "steamNoData": []}
    with pytest.raises(ValueError, match="match the game"):
        asyncio.run(app.snapshot_game(KEY))
