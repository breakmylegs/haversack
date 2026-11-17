"""Running games on a PC host (ADR-0038, P4). Synthetic games and paths only."""

import asyncio
import os
import sys

import pytest

from keepsake import pcwatch
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths

windows = pytest.mark.skipif(sys.platform != "win32", reason="the Windows process list")


def steam_game(tmp_path, appid=1999999101):
    return {
        "key": f"steam:{appid}",
        "kind": "steam",
        "appid": appid,
        "base_dir": str(tmp_path / "steamapps" / "common" / "Game"),
    }


def shortcut(exe, appid=4171510507):
    return {"key": f"shortcut:7:{appid}", "kind": "shortcut", "appid": appid, "exe": exe, "base_dir": None}


def test_a_steam_game_runs_when_a_process_sits_in_its_install_folder(tmp_path):
    game = steam_game(tmp_path)
    inside = str(tmp_path / "steamapps" / "common" / "Game" / "bin" / "Game.exe")
    assert pcwatch.game_running(game, [inside])
    assert not pcwatch.game_running(game, [str(tmp_path / "steamapps" / "common" / "GameTwo" / "x.exe")])
    if sys.platform == "win32":  # Windows paths compare without regard to case
        assert pcwatch.game_running(game, [inside.upper()])


def test_a_shortcut_matches_its_program_and_only_a_specific_folder(tmp_path):
    exe = str(tmp_path / "Games" / "Quest" / "Quest.exe")
    assert pcwatch.game_running(shortcut(exe), [exe])
    assert pcwatch.game_running(shortcut(exe), [str(tmp_path / "Games" / "Quest" / "Launcher.exe")])
    root_exe = os.path.join(os.path.abspath(os.sep), "Quest.exe")  # a program at the drive root
    assert pcwatch.game_running(shortcut(root_exe), [root_exe])
    assert not pcwatch.game_running(shortcut(root_exe), [os.path.join(os.path.abspath(os.sep), "Other.exe")])
    home_exe = str(tmp_path / "Quest.exe")
    assert not pcwatch.game_running(shortcut(home_exe), [str(tmp_path / "anything.exe")], home=str(tmp_path))


def test_the_watcher_sends_start_then_exit(tmp_path):
    game = steam_game(tmp_path)
    inside = str(tmp_path / "steamapps" / "common" / "Game" / "Game.exe")
    snapshots = [[], [inside], [inside], []]
    events = []

    async def games():
        return [game]

    async def on_event(kind, appid):
        events.append((kind, appid))

    watcher = pcwatch.Watcher(games, on_event, lister=lambda: snapshots.pop(0))

    async def go():
        return [await watcher.poll() for _ in range(4)]

    results = asyncio.run(go())
    assert events == [("start", 1999999101), ("exit", 1999999101)]
    assert results[1] == (["steam:1999999101"], []) and results[2] == ([], [])


@windows
def test_the_real_windows_process_list_includes_this_python():
    found = {os.path.normcase(os.path.realpath(p)) for p in pcwatch.list_processes()}
    assert os.path.normcase(os.path.realpath(sys.executable)) in found


@pytest.mark.parametrize("which", ["windows", "linux-desktop"])
def test_on_a_pc_a_start_never_runs_the_launch_gate(tmp_path, which):
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, auto_refresh_manifest=False, home=str(tmp_path), host=which)
    game = steam_game(tmp_path)
    started = []

    async def games_for(raw_id):
        return [game]

    async def launch(g):
        raise AssertionError("the launch gate pulls saves; never under a running game on a PC (P6)")

    async def pc_started(g):
        started.append(g["key"])

    app._games_for_appid = games_for
    app._launch = launch
    app._pc_started = pc_started

    async def go():
        result = await app.on_game_event("start", 1999999101)
        await asyncio.gather(*app._background)
        return result

    assert asyncio.run(go()) == {"handled": 1} and started == ["steam:1999999101"]


def test_the_running_check_follows_the_host(tmp_path):
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    game = steam_game(tmp_path)
    pc = KeepsakeApp(paths, auto_refresh_manifest=False, home=str(tmp_path), host="windows")
    pc._pc_processes = lambda: [str(tmp_path / "steamapps" / "common" / "Game" / "Game.exe")]
    assert pc._game_running(game) is True
    pc._pc_processes = lambda: []
    assert pc._game_running(game) is False
    decky = KeepsakeApp(paths, auto_refresh_manifest=False, home=str(tmp_path), proc_root=str(tmp_path / "no-proc"))
    decky._pc_processes = lambda: [str(tmp_path / "steamapps" / "common" / "Game" / "Game.exe")]
    assert decky._game_running(game) is False  # Decky reads /proc, never the PC list
