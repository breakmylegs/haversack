import asyncio

from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths

APPID = 4171510507


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


def test_startup_notice_after_update_is_given_once(tmp_path):
    asyncio.run(make_update_app(tmp_path, "0.2.0", []).start())
    app = make_update_app(tmp_path, "0.2.1", [])

    async def run():
        await app.start()
        return await app.take_startup_notice(), await app.take_startup_notice()

    first, second = asyncio.run(run())
    assert {k: first[k] for k in ("from", "to")} == {"from": "0.2.0", "to": "0.2.1"}  # plus What's new notes
    assert second is None


def test_update_waits_while_a_game_runs(tmp_path):
    """Game sessions come from Steam's start and exit events, for every game (ADR-0098)."""
    app = make_update_app(tmp_path, "0.2.0", [])

    async def run():
        await app.on_game_event("start", 4171510507 - 2**32)  # signed: the same game as below
        busy = (await app.get_status())["busy"], await app.prepare_update("v0.2.1")
        await app.on_game_event("exit", 4171510507)
        return busy, (await app.get_status())["busy"]

    (status_busy, refused), after = asyncio.run(run())
    assert status_busy == "session"
    assert refused == {"ok": False, "reason": "busy", "detail": "session"}
    assert after is None


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


def test_settings_round_trip(tmp_path):
    app, _ = make_discovery_app(tmp_path)
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
