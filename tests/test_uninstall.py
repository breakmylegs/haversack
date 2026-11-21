"""Uninstall (ADR-0065): the path guards, the plan, deletion, and the app's order of work. Synthetic data only."""

from __future__ import annotations

import asyncio
import os

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake import discovery, uninstall
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths

APPID = 4171510507  # unsigned form of -123456789


def _places(tmp_path, mounts=(), links=(), removable=()):
    home = tmp_path / "home"
    library = home / ".local" / "share" / "Steam"
    sd = tmp_path / "media" / "card"
    for folder in (home, library / "steamapps" / "common", library / "steamapps" / "compatdata", sd / "lib"):
        folder.mkdir(parents=True, exist_ok=True)
    return uninstall.Places(
        home=str(home),
        libraries=[str(library), str(sd / "lib")],
        steam_roots=[str(library)],
        extra_protected=[str(home / "homebrew" / "settings" / "Keepsake")],
        removable=[str(sd), *map(str, removable)],
        is_mount=lambda p: os.path.normcase(os.path.realpath(p)) in {os.path.normcase(str(m)) for m in mounts},
        is_link=lambda p: os.path.normcase(os.path.abspath(p)) in {os.path.normcase(str(x)) for x in links},
    )


def _mk(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


# The prefix guard


def test_prefix_only_as_this_games_compatdata_in_a_library(tmp_path):
    places = _places(tmp_path)
    library = tmp_path / "home" / ".local" / "share" / "Steam"
    prefix = _mk(library / "steamapps" / "compatdata" / str(APPID))
    sd_prefix = _mk(tmp_path / "media" / "card" / "lib" / "steamapps" / "compatdata" / str(APPID))
    assert uninstall.prefix_problem(str(prefix), APPID, places) is None
    assert uninstall.prefix_problem(str(sd_prefix), APPID, places) is None
    assert "not this game's" in uninstall.prefix_problem(str(prefix), APPID + 1, places)
    other = _mk(tmp_path / "home" / "Games" / "compatdata" / str(APPID))
    assert "not this game's" in uninstall.prefix_problem(str(other), APPID, places)
    assert "not this game's" in uninstall.prefix_problem(str(library / "steamapps" / "compatdata"), APPID, places)
    assert uninstall.prefix_problem(None, APPID, places) == "there is no prefix"
    missing = library / "steamapps" / "compatdata" / "12345"
    assert uninstall.prefix_problem(str(missing), 12345, places) == "it is not there"
    assert uninstall.prefix_problem(str(prefix), APPID, _places(tmp_path, links=[prefix])) == "it is a link"
    assert uninstall.prefix_problem(str(prefix), APPID, _places(tmp_path, mounts=[prefix])) == "it is a mount point"


# The install folder guard


def test_a_games_own_folder_may_be_deleted(tmp_path):
    places = _places(tmp_path)
    home = tmp_path / "home"
    assert uninstall.folder_problem(str(_mk(home / "Games" / "Example")), places, []) is None
    assert uninstall.folder_problem(str(_mk(home / "Downloads" / "Example")), places, []) is None
    common = tmp_path / "home" / ".local" / "share" / "Steam" / "steamapps" / "common"
    assert uninstall.folder_problem(str(_mk(common / "Example")), places, []) is None
    assert uninstall.folder_problem(str(_mk(tmp_path / "media" / "card" / "Games" / "X")), places, []) is None


@pytest.mark.parametrize(
    "relative",
    [
        "home",
        "home/Games",
        "home/Desktop",
        "home/Documents",
        "home/Downloads",
        "home/.local",
        "home/.local/share",
        "home/.config",
        "home/homebrew",
        "home/.local/share/Steam",
        "home/.local/share/Steam/steamapps",
        "home/.local/share/Steam/steamapps/common",
        "home/.local/share/Steam/steamapps/compatdata",
        "media/card",
        "media/card/lib",
        "media/card/lib/steamapps",
        "home/homebrew/settings",  # holds Keepsake's own folder
    ],
)
def test_protected_folders_are_never_deleted(tmp_path, relative):
    places = _places(tmp_path)
    folder = _mk(tmp_path / relative)
    assert uninstall.folder_problem(str(folder), places, []) is not None


def test_folders_outside_the_allowed_places_are_refused(tmp_path):
    places = _places(tmp_path)
    elsewhere = _mk(tmp_path / "elsewhere" / "Game")
    assert "not inside your home folder" in uninstall.folder_problem(str(elsewhere), places, [])
    assert "not inside your home folder" in uninstall.folder_problem(str(tmp_path), places, [])


def test_a_folder_another_game_uses_is_refused(tmp_path):
    places = _places(tmp_path)
    launcher = _mk(tmp_path / "home" / "Games" / "Launcher")
    game = _mk(launcher / "GameA")
    other_exe = str(game / "b.exe")
    assert "another game" in uninstall.folder_problem(str(launcher), places, [other_exe])  # contains another's exe
    assert "another game" in uninstall.folder_problem(str(game), places, [str(launcher)])  # inside another's folder
    assert "another game" in uninstall.folder_problem(str(game), places, [str(game)])  # the same folder
    assert uninstall.folder_problem(str(game), places, ["", str(tmp_path / "home" / "Games" / "Other")]) is None


def test_links_mount_points_and_odd_paths_are_refused(tmp_path):
    folder = _mk(tmp_path / "home" / "Games" / "Example")
    assert uninstall.folder_problem(str(folder), _places(tmp_path, links=[folder]), []) == "it is a link"
    assert uninstall.folder_problem(str(folder), _places(tmp_path, mounts=[folder]), []) == "it is a mount point"
    places = _places(tmp_path)
    assert uninstall.folder_problem(None, places, []) == "the shortcut names no folder"
    assert uninstall.folder_problem("Games/Example", places, []) == "it is not a full path"
    assert uninstall.folder_problem(str(tmp_path / "home" / "Games" / "Gone"), places, []) == "it is not there"
    stick = _mk(tmp_path / "home" / "stick")
    assert uninstall.folder_problem(str(stick), _places(tmp_path, removable=[stick]), []) is not None


# The plan


def _game(tmp_path, base, prefix=True):
    library = tmp_path / "home" / ".local" / "share" / "Steam"
    pfx = _mk(library / "steamapps" / "compatdata" / str(APPID)) if prefix else None
    return {
        "key": f"shortcut:7:{APPID}",
        "kind": "shortcut",
        "appid": APPID,
        "name": "Example Quest",
        "prefix": str(pfx) if pfx else None,
        "base_dir": str(base) if base else None,
    }


def test_plan_lists_prefix_and_folder_with_sizes_and_free_space(tmp_path):
    places = _places(tmp_path)
    base = _mk(tmp_path / "home" / "Games" / "Example")
    found = uninstall.plan(_game(tmp_path, base), places, [], sizes=lambda p: 100, free=lambda p: 1000)
    assert [(f["kind"], f["size"]) for f in found["folders"]] == [("prefix", 100), ("install", 100)]
    assert [f["freeAfter"] for f in found["folders"]] == [1200, 1200]  # same drive: both freed
    assert found["kept"] == [] and found["appid"] == APPID


def test_a_game_inside_its_prefix_is_deleted_with_the_prefix(tmp_path):
    places = _places(tmp_path)
    game = _game(tmp_path, None)
    inside = _mk(tmp_path / game["prefix"] / "pfx" / "drive_c" / "Games" / "Example")
    game["base_dir"] = str(inside)
    found = uninstall.plan(game, places, [], sizes=lambda p: 1, free=lambda p: 0)
    assert [f["kind"] for f in found["folders"]] == ["prefix"]


def test_plan_keeps_refused_folders_with_their_reason(tmp_path):
    places = _places(tmp_path)
    game = _game(tmp_path, _mk(tmp_path / "home" / "Games"), prefix=False)  # the library folder itself
    found = uninstall.plan(game, places, [], sizes=lambda p: 1, free=lambda p: 0)
    assert found["folders"] == []
    assert found["kept"][0]["path"].endswith("Games") and "would delete" in found["kept"][0]["reason"]
    game = _game(tmp_path, tmp_path / "home" / "Games" / "Gone", prefix=False)
    assert uninstall.plan(game, places, [], sizes=lambda p: 1, free=lambda p: 0)["kept"] == []  # nothing to say
    with pytest.raises(uninstall.UninstallError):
        uninstall.plan({**game, "kind": "steam"}, places, [])


def test_recheck_runs_the_guards_again(tmp_path):
    places = _places(tmp_path)
    base = _mk(tmp_path / "home" / "Games" / "Example")
    assert uninstall.recheck({"kind": "install", "path": str(base)}, APPID, places, []) is None
    assert uninstall.recheck({"kind": "install", "path": str(base)}, APPID, places, [str(base / "x")]) is not None
    assert uninstall.recheck({"kind": "prefix", "path": str(base)}, APPID, places, []) is not None


# Deletion


def test_delete_tree_reports_progress_and_stops_on_cancel(tmp_path):
    root = _mk(tmp_path / "game")
    for i in range(5):
        (_mk(root / f"d{i}") / "f.bin").write_bytes(b"x" * 10)
    seen = []
    assert uninstall.delete_tree(str(root), progress=seen.append) == 50
    assert not root.exists() and seen[-1] == 50
    root = _mk(tmp_path / "again")
    for i in range(5):
        (root / f"f{i}").write_bytes(b"y")
    calls = iter([False, False, True])
    with pytest.raises(uninstall.Cancelled):
        uninstall.delete_tree(str(root), cancelled=lambda: next(calls, True))
    assert root.exists() and len(os.listdir(root)) == 3


@pytest.mark.posix
@pytest.mark.skipif(os.name == "nt", reason="symlinks need POSIX")
def test_delete_tree_never_follows_a_link(tmp_path):
    outside = _mk(tmp_path / "keep")
    (outside / "precious.txt").write_text("keep me")
    root = _mk(tmp_path / "game")
    os.symlink(outside, root / "link-to-dir")
    os.symlink(outside / "precious.txt", root / "link-to-file")
    uninstall.delete_tree(str(root))
    assert (outside / "precious.txt").read_text() == "keep me"


# The app


def _app(tmp_path, synced=False):
    home = tmp_path / "home"
    game_dir = _mk(home / "Games" / "Example")
    (game_dir / "game.exe").write_bytes(b"x" * 100)
    make_fake_steam(
        home,
        users={"7": [shortcut_entry(-123456789, "Example Quest", (game_dir / "game.exe").as_posix())]},
        apps=[(None, 1000020, "Steam Game", "SteamGame")],
        most_recent="7",
        prefixes=[(None, APPID)],
    )
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="0.27.0", home=str(home), auto_refresh_manifest=False
    )
    app.UNINSTALL_OP_TIMEOUT = 2.0
    events = []

    async def emit(event, *args):
        events.append((event, args))

    app.emit = emit
    if synced:
        app.game_configs.update(f"shortcut:7:{APPID}", {"enabled": True, "gameKey": "example-quest"})
    return app, game_dir, events


KEY = f"shortcut:7:{APPID}"


async def _until(app, states, limit=200):
    for _ in range(limit):
        job = await app.uninstall_status()
        if job and job["state"] in states:
            return job
        await asyncio.sleep(0.02)
    raise AssertionError(f"never reached {states}: {await app.uninstall_status()}")


def test_uninstall_removes_shortcut_then_folders_then_records(tmp_path):
    app, game_dir, events = _app(tmp_path)
    prefix = tmp_path / "home" / ".local" / "share" / "Steam" / "steamapps" / "compatdata" / str(APPID)
    app.game_configs.update(KEY, {"aliases": ["EQ"]})

    async def go():
        await app.start()
        plan = await app.uninstall_plan(KEY)
        await app.uninstall_start(KEY)
        await _until(app, ("removing-shortcut",))
        assert game_dir.exists() and prefix.exists()  # nothing is deleted before Steam has removed the shortcut
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": None})
        job = await _until(app, ("done", "failed"))
        games = [g["key"] for g in (await app.discover_games())["games"]]
        await app.stop()
        return plan, op, job, games

    plan, op, job, _games = asyncio.run(go())
    assert [f["kind"] for f in plan["folders"]] == ["prefix", "install"] and plan["synced"] is False
    assert (op["kind"], op["module"], op["payload"]) == (
        "remove-shortcut",
        "uninstall",
        {"appid": APPID, "clearArtwork": True},
    )
    assert job["state"] == "done", job
    assert not game_dir.exists() and not prefix.exists()
    assert app.game_configs.get(KEY)["aliases"] == []  # Keepsake's records are gone
    assert any(e == "keepsake_toast" and "uninstalled" in str(a) for e, a in events)


def test_nothing_is_deleted_if_steam_still_lists_the_shortcut(tmp_path):
    app, game_dir, _events = _app(tmp_path)

    async def go():
        await app.start()
        await app.uninstall_start(KEY)
        await _until(app, ("removing-shortcut",))
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": "Example Quest"})
        job = await _until(app, ("done", "failed"))
        await app.stop()
        return job

    job = asyncio.run(go())
    assert job["state"] == "failed" and "still lists" in job["error"]
    assert game_dir.exists()


def test_nothing_is_deleted_if_steam_never_answers(tmp_path):
    app, game_dir, _events = _app(tmp_path)
    app.UNINSTALL_OP_TIMEOUT = 0.1

    async def go():
        await app.start()
        await app.uninstall_start(KEY)
        job = await _until(app, ("done", "failed"))
        await app.stop()
        return job

    job = asyncio.run(go())
    assert job["state"] == "failed" and "did not remove" in job["error"] and game_dir.exists()


def test_a_failed_final_backup_stops_before_anything_changes(tmp_path):
    app, game_dir, _events = _app(tmp_path, synced=True)

    async def pending(key):
        return {"status": "pending"}

    app.sync_push = pending

    async def go():
        await app.start()
        plan = await app.uninstall_plan(KEY)
        await app.uninstall_start(KEY)
        job = await _until(app, ("done", "failed"))
        claimed = await app.steam_ops_claim()
        await app.stop()
        return plan, job, claimed

    plan, job, claimed = asyncio.run(go())
    assert plan["synced"] is True
    assert job["state"] == "failed" and "final backup" in job["error"]
    assert claimed is None and game_dir.exists()


def test_a_final_backup_is_taken_and_where_to_restore_is_said(tmp_path):
    app, game_dir, _events = _app(tmp_path, synced=True)
    pushed = []

    async def published(key):
        pushed.append(key)
        return {"status": "published", "snapId": "snap-1"}

    app.sync_push = published

    async def go():
        await app.start()
        await app.uninstall_start(KEY)
        await _until(app, ("removing-shortcut",))
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": None})
        job = await _until(app, ("done", "failed"))
        await app.stop()
        return job

    job = asyncio.run(go())
    assert pushed == [KEY] and job["backup"] == "snap-1" and "History of Example Quest" in job["restoreFrom"]
    assert job["state"] == "done" and not game_dir.exists()


def test_skipping_the_backup_and_cancelling(tmp_path):
    app, game_dir, _events = _app(tmp_path, synced=True)

    async def never(key):
        raise AssertionError("no backup was asked for")

    app.sync_push = never

    async def go():
        await app.start()
        await app.uninstall_start(KEY, skip_backup=True)
        await _until(app, ("removing-shortcut",))
        with pytest.raises(ValueError, match="already running"):
            await app.uninstall_start(KEY)
        await app.uninstall_cancel()
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": None})
        job = await _until(app, ("done", "failed", "cancelled"))
        await app.stop()
        return job

    job = asyncio.run(go())
    assert job["state"] == "cancelled" and game_dir.exists()


def test_refusals_running_streaming_and_other_kinds(tmp_path, monkeypatch):
    app, _game_dir, _events = _app(tmp_path)

    async def go():
        await app.remote_copies_report([{"appid": APPID, "name": "Example Quest", "steam": "remote"}])
        with pytest.raises(ValueError, match="installed on another device"):
            await app.uninstall_plan(KEY)
        await app.remote_copies_report([{"appid": APPID, "name": "Example Quest", "steam": "local"}])
        monkeypatch.setattr("keepsake.app.find_game_processes", lambda *a, **k: [object()])
        with pytest.raises(ValueError, match="quit the game"):
            await app.uninstall_plan(KEY)
        monkeypatch.setattr("keepsake.app.find_game_processes", lambda *a, **k: [])
        with pytest.raises(ValueError, match="Steam uninstalls its own"):
            await app.uninstall_start("steam:1000020")
        return await app.uninstall_plan(KEY)

    assert asyncio.run(go())["steam"] is False


def test_steam_games_go_through_steams_own_uninstall(tmp_path):
    app, _game_dir, _events = _app(tmp_path)
    app.game_configs.update("steam:1000020", {"enabled": True, "gameKey": "steam-game"})
    pushed = []

    async def published(key):
        pushed.append(key)
        return {"status": "no-change"}

    app.sync_push = published

    async def go():
        await app.start()
        plan = await app.uninstall_plan("steam:1000020")
        with pytest.raises(ValueError, match="not a Steam game"):
            await app.uninstall_steam(KEY)
        result = await app.uninstall_steam("steam:1000020", backup=True)
        op = await app.steam_ops_claim()
        await app.uninstall_steam("steam:1000020", backup=False)
        await app.stop()
        return plan, result, op

    plan, result, op = asyncio.run(go())
    assert plan["steam"] is True and plan["folders"] == [] and plan["synced"] is True
    assert pushed == ["steam:1000020"]  # once: the second time the backup was declined
    assert op["kind"] == "open-uninstall" and op["payload"] == {"appid": 1000020}
    assert result["backup"] == {"status": "no-change"}


def test_forget_clears_links_and_installer_records(tmp_path):
    app, _game_dir, _events = _app(tmp_path)
    removed, forgotten = [], []

    class Links:
        def for_appid(self, appid):
            return ("link-1", {}) if appid == APPID else None

        def remove(self, link_id):
            removed.append(link_id)

    class Installer:
        def forget_appid(self, appid):
            forgotten.append(appid)

    app.game_links, app.installer = Links(), Installer()
    app.game_configs.update(KEY, {"aliases": ["EQ"]})
    app._uninstall_forget(KEY, APPID)
    assert removed == ["link-1"] and forgotten == [APPID] and app.game_configs.get(KEY)["aliases"] == []
    assert discovery.unsigned_appid(-123456789) == APPID


HOME_FOLDERS = (  # written out here, so a folder dropped from the module's list fails a test
    "Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos", "Games", ".local", ".local/share",
    ".config", ".cache", ".steam", ".var", "homebrew", "Applications",
)  # fmt: skip


@pytest.mark.parametrize("name", HOME_FOLDERS)
def test_each_home_folder_is_protected_by_name_alone(tmp_path, name):
    home = _mk(tmp_path / "h")
    if name == ".local":  # .local holds .local/share, protected too: check .local on its own list
        places = uninstall.Places(home=str(home), libraries=[], is_mount=lambda p: False, is_link=lambda p: False)
        assert any(p.endswith(".local") for p in places.protected())
    places = uninstall.Places(home=str(home), libraries=[], is_mount=lambda p: False, is_link=lambda p: False)
    assert "would delete" in uninstall.folder_problem(str(_mk(home / name)), places, [])
    assert uninstall.folder_problem(str(_mk(home / name / "SomeGame")), places, []) is None


def test_a_cancel_during_the_backup_stops_before_steam_is_asked(tmp_path):
    app, game_dir, _events = _app(tmp_path, synced=True)

    async def published(key):
        app._uninstall_cancel = True  # the user pressed Stop while the backup ran
        return {"status": "published", "snapId": "snap-2"}

    app.sync_push = published

    async def go():
        await app.start()
        await app.uninstall_start(KEY)
        job = await _until(app, ("done", "failed", "cancelled"))
        claimed = await app.steam_ops_claim()
        await app.stop()
        return job, claimed

    job, claimed = asyncio.run(go())
    assert job["state"] == "cancelled" and claimed is None and game_dir.exists()


def test_folders_are_checked_again_just_before_deleting(tmp_path):
    app, game_dir, _events = _app(tmp_path)
    prefix = tmp_path / "home" / ".local" / "share" / "Steam" / "steamapps" / "compatdata" / str(APPID)

    async def go():
        await app.start()
        await app.uninstall_start(KEY)
        await _until(app, ("removing-shortcut",))
        uninstall.delete_tree(str(game_dir))  # the folder changed since the plan
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": None})
        job = await _until(app, ("done", "failed"))
        await app.stop()
        return job

    job = asyncio.run(go())
    assert job["state"] == "done" and not prefix.exists()
    assert [k["reason"] for k in job["kept"]] == ["it is not there"]


def test_a_folder_shared_with_another_shortcut_is_kept(tmp_path):
    home = tmp_path / "home"
    shared = _mk(home / "Games" / "Bundle")
    (shared / "a.exe").write_text("a")
    (shared / "b.exe").write_text("b")
    make_fake_steam(
        home,
        users={
            "7": [
                shortcut_entry(-123456789, "Game A", (shared / "a.exe").as_posix()),
                shortcut_entry(-123456790, "Game B", (shared / "b.exe").as_posix()),
            ]
        },
        most_recent="7",
        prefixes=[(None, APPID)],
    )
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="0.27.0", home=str(home), auto_refresh_manifest=False
    )
    plan = asyncio.run(app.uninstall_plan(KEY))
    assert [f["kind"] for f in plan["folders"]] == ["prefix"]
    assert "another game" in plan["kept"][0]["reason"]
