"""R5, storage (ADR-0052): disk use, clearing a shader cache, and "reset prefix, keep saves".
Synthetic games, prefixes and saves only."""

import asyncio
import os
import time

import pytest

from helpers import write_fake_proc
from keepsake import storage
from test_app_snapshots import APPID, KEY, app_and_save  # noqa: F401 - the fixture
from test_app_ux import run

UID = os.getuid() if hasattr(os, "getuid") else -1


def write(path, data=b"x"):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


# Sizes and the rules for what may be touched


def test_folder_size_counts_files_and_stops_at_the_deadline(tmp_path):
    write(tmp_path / "a" / "one.bin", b"12345")
    write(tmp_path / "a" / "deep" / "two.bin", b"123")
    assert storage.folder_size(str(tmp_path / "a")) == {"bytes": 8, "files": 2, "partial": False, "present": True}
    assert storage.folder_size(str(tmp_path / "a"), deadline=time.monotonic() - 1)["partial"] is True
    assert storage.folder_size(str(tmp_path / "missing"))["present"] is False


@pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt", reason="symlinks need POSIX")
def test_folder_size_never_follows_symlinks(tmp_path):
    write(tmp_path / "elsewhere" / "big.bin", b"x" * 1000)
    os.makedirs(tmp_path / "a")
    os.symlink(tmp_path / "elsewhere", tmp_path / "a" / "link")
    assert storage.folder_size(str(tmp_path / "a"))["bytes"] == 0


def test_only_a_steam_compatdata_prefix_and_a_real_shader_cache_qualify(tmp_path):
    root = tmp_path / "steam"
    prefix = root / "steamapps" / "compatdata" / "1999999101"
    os.makedirs(prefix / "pfx")
    os.makedirs(root / "steamapps" / "shadercache" / "1999999101")
    game = {
        "key": "steam:1999999101",
        "kind": "steam",
        "appid": 1999999101,
        "prefix": str(prefix),
        "steam_root": str(root),
    }
    assert storage.compat_prefix(game) == str(prefix)
    assert storage.shader_cache_dir(game).endswith(os.path.join("shadercache", "1999999101"))
    assert storage.compat_prefix({**game, "kind": "heroic"}) is None  # another launcher's prefix: not ours
    assert storage.compat_prefix({**game, "prefix": str(tmp_path / "custom-prefix")}) is None
    assert storage.shader_cache_dir({**game, "appid": 0}) is None
    usage = storage.usage({**game, "name": "Example", "exe_inside_prefix": True}, 0)
    assert usage["canResetPrefix"] is False and usage["install"]["insidePrefix"] is True


def test_delete_old_prefix_only_removes_a_folder_keepsake_moved_aside(tmp_path):
    prefix = tmp_path / "compatdata" / "1999999101"
    os.makedirs(prefix)
    with pytest.raises(storage.StorageError, match="not a prefix"):
        storage.delete_old_prefix(str(tmp_path / "compatdata"), str(prefix))
    old = storage.move_prefix_aside(str(prefix))
    assert not prefix.exists() and storage.delete_old_prefix(old, str(prefix)) == 0 and not os.path.exists(old)


# The app


def steam_game(app):
    return next(g for g in run(app.discover_games())["games"] if g["key"] == KEY)


def shader_cache(app):
    folder = os.path.join(steam_game(app)["steam_root"], "steamapps", "shadercache", str(APPID))
    write(os.path.join(folder, "cache.bin"), b"c" * 2048)
    return folder


def prefix_of(app):
    from pathlib import Path

    return Path(steam_game(app)["prefix"])


def test_disk_use_lists_each_part_and_the_shader_cache_can_be_cleared(app_and_save):  # noqa: F811
    app, saves, _tmp_path = app_and_save
    cache = shader_cache(app)

    async def go():
        before = (await app.storage_usage(KEY))["games"][0]
        cleared = await app.clear_shader_cache(KEY)
        after = (await app.storage_usage(KEY))["games"][0]
        return before, cleared, after

    before, cleared, after = run(go())
    assert before["shaderCache"]["bytes"] == 2048 and before["saves"]["bytes"] == len(b"chapter 1")
    assert before["prefix"]["present"] and before["canResetPrefix"] and before["canClearShaderCache"]
    assert before["install"]["present"] is False and before["partial"] is False  # "/" is never counted
    assert cleared == {"ok": True, "freed": 2048} and not os.path.exists(cache)
    assert after["canClearShaderCache"] is False
    assert saves.joinpath("slot1.sav").read_bytes() == b"chapter 1"  # saves untouched


def test_nothing_changes_while_the_game_runs(app_and_save):  # noqa: F811
    app, _saves, tmp_path = app_and_save
    shader_cache(app)
    write_fake_proc(str(tmp_path / "proc"), 900, 1, "game.exe", uid=UID, env={"SteamAppId": str(APPID)})
    for call in (app.clear_shader_cache, app.reset_prefix):
        with pytest.raises(ValueError, match="quit the game"):
            run(call(KEY))
    assert prefix_of(app).exists()


def test_a_prefix_reset_keeps_the_saves_and_puts_them_back_after_the_first_launch(app_and_save):  # noqa: F811
    app, saves, _tmp_path = app_and_save
    prefix = prefix_of(app)
    (saves / "slot2.sav").write_bytes(b"second slot")

    async def go():
        await app.update_game_config(KEY, {"enabled": True})
        reset = await app.reset_prefix(KEY)
        moved = not prefix.exists()
        record = storage.resets(app.paths.runtime_dir)[KEY]
        moved = moved and os.path.isdir(record["old"]) and os.path.isfile(record["blob"])
        # Steam would not launch a waiting game through the gate: the start event is skipped.
        await app.on_game_event("start", APPID)
        launching = KEY in app._launching
        early = await app._finish_prefix_reset(KEY)  # no fresh prefix yet: keep waiting
        # The first launch: Proton builds a fresh prefix, and the game writes a new empty save.
        fresh = prefix / "pfx" / "drive_c" / "users" / "steamuser" / "AppData" / "Local" / "ExampleQuest" / "Saves"
        os.makedirs(fresh)
        (fresh / "slot1.sav").write_bytes(b"new game")
        await app.on_game_event("exit", APPID)
        await asyncio.gather(*app._background)
        done = storage.resets(app.paths.runtime_dir)[KEY]
        listing = await app.list_snapshots(KEY)
        deleted = await app.delete_old_prefix(KEY)
        return reset, moved, record, launching, early, fresh, done, listing, deleted

    reset, moved, record, launching, early, fresh, done, listing, deleted = run(go())
    assert reset == {"ok": True, "stage": "waiting"} and moved
    assert record["meta"]["flags"] == ["before-prefix-reset"]
    assert launching is False and early == {"status": "waiting"}
    assert (fresh / "slot1.sav").read_bytes() == b"chapter 1" and (fresh / "slot2.sav").read_bytes() == b"second slot"
    assert done["stage"] == "restored"
    assert listing["prerestore"]  # the fresh files were kept too, so the restore can be undone
    assert deleted["ok"] and not os.path.exists(record["old"]) and not os.path.exists(record["blob"])
    assert KEY not in storage.resets(app.paths.runtime_dir)


def test_a_reset_can_be_undone_before_the_saves_go_back(app_and_save):  # noqa: F811
    app, saves, _tmp_path = app_and_save
    prefix = prefix_of(app)

    async def go():
        await app.reset_prefix(KEY)
        os.makedirs(prefix / "pfx" / "drive_c")  # a fresh prefix appeared meanwhile
        await app.cancel_prefix_reset(KEY)

    run(go())
    assert saves.joinpath("slot1.sav").read_bytes() == b"chapter 1"  # the original prefix is back in place
    assert KEY not in storage.resets(app.paths.runtime_dir)
    assert any(name.startswith(f"{APPID}{storage.RESET_SUFFIX}fresh-") for name in os.listdir(prefix.parent))


def test_resets_refuse_what_they_cannot_do_safely(app_and_save):  # noqa: F811
    app, _saves, _tmp_path = app_and_save
    with pytest.raises(ValueError, match="no waiting reset"):
        run(app.cancel_prefix_reset(KEY))
    with pytest.raises(ValueError, match="not finished"):
        run(app.delete_old_prefix(KEY))
    run(app.reset_prefix(KEY))
    with pytest.raises(ValueError, match="already waiting"):
        run(app.reset_prefix(KEY))


def test_a_game_installed_inside_its_prefix_is_never_reset(app_and_save, monkeypatch):  # noqa: F811
    app, _saves, _tmp_path = app_and_save
    prefix = prefix_of(app)

    async def go():
        games = (await app.discover_games())["games"]
        for game in games:
            game["exe_inside_prefix"] = True
        with pytest.raises(ValueError, match="installed inside its prefix"):
            await app.reset_prefix(KEY)

    run(go())
    assert prefix.exists()


def test_a_numbered_folder_outside_compatdata_is_not_a_steam_prefix(tmp_path):
    other = tmp_path / "elsewhere" / "1999999101"
    os.makedirs(other / "pfx")
    assert storage.compat_prefix({"kind": "steam", "prefix": str(other)}) is None


def test_the_old_prefix_cannot_be_deleted_while_the_reset_waits(app_and_save):  # noqa: F811
    app, _saves, _tmp_path = app_and_save
    run(app.reset_prefix(KEY))
    with pytest.raises(ValueError, match="not finished"):
        run(app.delete_old_prefix(KEY))
    assert os.path.isdir(storage.resets(app.paths.runtime_dir)[KEY]["old"])


def test_a_kept_copy_that_fails_verification_stops_the_reset_before_anything_moves(app_and_save, monkeypatch):  # noqa: F811
    from keepsake import engine

    app, _saves, _tmp_path = app_and_save
    prefix = prefix_of(app)
    real_pack = engine.pack

    def damaged_pack(entries, roots, dest):
        real_pack(entries, roots, dest)
        return "0" * 64  # the zip does not match what the metadata will say

    monkeypatch.setattr(engine, "pack", damaged_pack)
    with pytest.raises(Exception, match=r"(?i)hash|match"):
        run(app.reset_prefix(KEY))
    assert prefix.exists() and KEY not in storage.resets(app.paths.runtime_dir)
    assert not os.listdir(os.path.join(app.paths.runtime_dir, "prefix-resets"))  # no copy left behind


def test_a_game_with_no_saves_is_not_reset(app_and_save):  # noqa: F811
    app, saves, _tmp_path = app_and_save
    prefix = prefix_of(app)
    (saves / "slot1.sav").unlink()
    with pytest.raises(Exception, match="no save files"):
        run(app.reset_prefix(KEY))
    assert prefix.exists()
