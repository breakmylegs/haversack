import asyncio
import json

import pytest

from helpers import write_fake_proc
from keepsake.app import KeepsakeApp
from keepsake.freeze import FROZEN_FILE, SIGCONT, SIGSTOP
from keepsake.paths import PluginPaths

APPID = 4171510507


def make_app(tmp_path, kill_calls):
    paths = PluginPaths(
        settings_dir=str(tmp_path / "settings"),
        runtime_dir=str(tmp_path / "runtime"),
        log_dir=str(tmp_path / "logs"),
        plugin_dir=str(tmp_path / "plugin"),
    )
    proc_root = str(tmp_path / "proc")
    app = KeepsakeApp(paths, proc_root=proc_root)
    app.freezer._kill = lambda pid, sig: kill_calls.append((pid, sig))
    return app, proc_root


def test_freeze_test_releases_and_clamps(tmp_path, monkeypatch):
    calls = []
    app, proc_root = make_app(tmp_path, calls)
    import os

    uid = os.getuid() if hasattr(os, "getuid") else -1
    write_fake_proc(proc_root, 500, 1, "game.exe", uid=uid, env={"SteamAppId": str(APPID)})

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr("keepsake.app.asyncio.sleep", fast_sleep)
    result = asyncio.run(app.freeze_test(APPID, 99))
    assert result == {"ok": True, "stopped": 1, "resumed": 1, "seconds": 10}
    assert calls == [(500, SIGSTOP), (500, SIGCONT)]


def test_freeze_test_releases_when_cancelled(tmp_path):
    calls = []
    app, proc_root = make_app(tmp_path, calls)
    import os

    uid = os.getuid() if hasattr(os, "getuid") else -1
    write_fake_proc(proc_root, 500, 1, "game.exe", uid=uid, env={"SteamAppId": str(APPID)})

    async def run():
        task = asyncio.create_task(app.freeze_test(APPID, 5))
        for _ in range(500):
            if (500, SIGSTOP) in calls:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert calls == [(500, SIGSTOP), (500, SIGCONT)]


def test_freeze_test_without_processes(tmp_path):
    app, _ = make_app(tmp_path, [])
    assert asyncio.run(app.freeze_test(APPID)) == {"ok": False, "reason": "no-processes"}


def test_start_releases_left_over_frozen(tmp_path):
    calls = []
    app, proc_root = make_app(tmp_path, calls)
    write_fake_proc(proc_root, 600, 1, "game.exe")
    (tmp_path / "runtime" / FROZEN_FILE).write_text(json.dumps([{"pid": 600, "starttime": 1000}]))
    asyncio.run(app.start())
    assert calls == [(600, SIGCONT)]


def test_settings_round_trip(tmp_path):
    app, _ = make_app(tmp_path, [])
    asyncio.run(app.set_setting("deviceName", "Handheld"))
    assert asyncio.run(app.get_settings())["deviceName"] == "Handheld"
