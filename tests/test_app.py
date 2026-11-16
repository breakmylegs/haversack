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
    app = KeepsakeApp(paths, proc_root=proc_root, auto_refresh_manifest=False)
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


def make_update_app(tmp_path, version, emitted):
    paths = PluginPaths(
        settings_dir=str(tmp_path / "settings"),
        runtime_dir=str(tmp_path / "runtime"),
        log_dir=str(tmp_path / "logs"),
        plugin_dir=str(tmp_path / "plugin"),
    )

    async def emit(event, *args):
        emitted.append(event)

    def no_network(url, headers=None):
        raise AssertionError(f"unexpected network call to {url}")

    return KeepsakeApp(
        paths,
        emit=emit,
        proc_root=str(tmp_path / "proc"),
        version=version,
        fetch=no_network,
        auto_refresh_manifest=False,
    )


def test_update_refused_while_simulated_sync_runs_then_idle_event(tmp_path):
    emitted = []
    app = make_update_app(tmp_path, "0.2.0", emitted)

    async def run():
        await app.start()
        job = asyncio.create_task(app.simulate_sync_job(1))
        await asyncio.sleep(0.1)
        assert (await app.get_status())["busy"] == "sync"
        refused = await app.prepare_update("v0.2.1")
        await job
        await asyncio.sleep(0.05)
        return refused

    refused = asyncio.run(run())
    assert refused == {"ok": False, "reason": "busy", "detail": "sync"}
    assert "keepsake_idle" in emitted


def test_startup_notice_after_update_is_given_once(tmp_path):
    asyncio.run(make_update_app(tmp_path, "0.2.0", []).start())
    app = make_update_app(tmp_path, "0.2.1", [])

    async def run():
        await app.start()
        return await app.take_startup_notice(), await app.take_startup_notice()

    first, second = asyncio.run(run())
    assert first == {"from": "0.2.0", "to": "0.2.1"}
    assert second is None


def make_discovery_app(tmp_path):
    from helpers import make_fake_steam, shortcut_entry

    home = tmp_path / "home"
    home.mkdir()
    root = make_fake_steam(
        home, users={"7": [shortcut_entry(-123456789, "Example Quest", "/g.exe")]}, prefixes=[(None, APPID)]
    )
    paths = PluginPaths(
        settings_dir=str(tmp_path / "settings"),
        runtime_dir=str(tmp_path / "runtime"),
        log_dir=str(tmp_path / "logs"),
        plugin_dir=str(tmp_path / "plugin"),
    )
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="0.3.0", home=str(home), auto_refresh_manifest=False
    )
    return app, root


def test_discover_games_caches_until_refresh(tmp_path):
    app, root = make_discovery_app(tmp_path)
    first = asyncio.run(app.discover_games())
    assert [g["name"] for g in first["games"]] == ["Example Quest"]
    (root / "userdata" / "7" / "config" / "shortcuts.vdf").unlink()
    assert len(asyncio.run(app.discover_games())["games"]) == 1
    assert asyncio.run(app.discover_games(True))["games"] == []


@pytest.mark.parametrize(
    ("observed", "status", "blocked"),
    [("same", "match", False), ("/elsewhere/steamapps/compatdata/999", "mismatch", True), (None, "unknown", False)],
)
def test_check_running_prefix_records_result(tmp_path, observed, status, blocked):
    import os

    from keepsake import discovery
    from keepsake.procs import SHORTCUT_GAMEID_FLAG

    app, root = make_discovery_app(tmp_path)
    uid = os.getuid() if hasattr(os, "getuid") else -1
    if observed is not None:
        compat = str(root / "steamapps" / "compatdata" / str(APPID)) if observed == "same" else observed
        write_fake_proc(
            str(tmp_path / "proc"),
            900,
            1,
            "game.exe",
            uid=uid,
            env={"SteamGameId": str((APPID << 32) | SHORTCUT_GAMEID_FLAG), "STEAM_COMPAT_DATA_PATH": compat},
        )
    key = f"shortcut:7:{APPID}"
    result = asyncio.run(app.check_running_prefix(key))
    assert result["status"] == status
    assert discovery.sync_blocked(app.paths.runtime_dir, key) is blocked
    assert (key in asyncio.run(app.discover_games())["mismatches"]) is blocked


def test_check_running_prefix_unknown_game(tmp_path):
    app, _ = make_discovery_app(tmp_path)
    assert asyncio.run(app.check_running_prefix("shortcut:7:1"))["reason"] == "unknown-game"


def test_settings_round_trip(tmp_path):
    app, _ = make_app(tmp_path, [])
    asyncio.run(app.set_setting("deviceName", "Handheld"))
    assert asyncio.run(app.get_settings())["deviceName"] == "Handheld"


def test_manifest_refresh_sends_throttled_progress_and_can_be_polled(tmp_path):
    from keepsake.net import HttpResponse
    from test_manifest import SAMPLE

    events, seen_while_running = [], []
    paths = PluginPaths(
        settings_dir=str(tmp_path / "settings"),
        runtime_dir=str(tmp_path / "runtime"),
        log_dir=str(tmp_path / "logs"),
        plugin_dir=str(tmp_path / "plugin"),
    )

    async def emit(event, *args):
        events.append((event, args))

    def download(url, dest, headers=None, max_bytes=None, progress=None):
        with open(dest, "w", encoding="utf-8") as handle:
            handle.write(SAMPLE)
        for done in range(1, 21):  # twenty chunks in a burst: only the first is sent
            progress(done, 20)
        seen_while_running.append(dict(app._manifest_progress))
        return HttpResponse(status=200, headers={})

    app = KeepsakeApp(paths, emit=emit, proc_root=str(tmp_path / "proc"), auto_refresh_manifest=False)
    app.manifest._download = download

    async def go():
        assert (await app.manifest_progress()) == {"stage": "idle", "running": False}
        result = await app.refresh_manifest(True)
        await asyncio.sleep(0)  # let progress sent from the worker thread arrive
        return result, await app.manifest_progress()

    result, after = asyncio.run(go())
    assert result["ok"] and after == {"stage": "idle", "running": False}
    assert seen_while_running == [{"stage": "downloading", "bytes": 20, "total": 20, "running": True}]
    sent = [args[0] for event, args in events if event == "keepsake_manifest_progress"]
    stages = [s["stage"] for s in sent]
    assert stages[0] == "checking" and stages[-1] == "finished" and "saving" in stages
    assert stages.count("downloading") == 1  # throttled to two a second
    assert sent[-1]["ok"] is True and sent[-1]["running"] is False and sent[-1]["games"] == result["games"]
