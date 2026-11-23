"""Pause the running game (R29 stage 3, ADR-0094): its own record and an hour's watchdog, released on
Resume, game exit, the Device module stopping, unload and the next start. Haversack's own freezes keep
their 30 seconds."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from helpers import write_fake_proc
from keepsake import app as app_module
from keepsake.freeze import HARD_CEILING_SECONDS, PAUSE_CEILING_SECONDS, PAUSED_FILE, SIGCONT, SIGSTOP, Freezer
from keepsake.procs import read_proc
from test_freeze import FakeKill

APPID = 4000555


def test_the_automatic_freeze_keeps_its_thirty_seconds(tmp_path: Any) -> None:
    assert Freezer(str(tmp_path), kill=FakeKill(), ceiling=999)._ceiling == HARD_CEILING_SECONDS
    pauser = Freezer(str(tmp_path), kill=FakeKill(), ceiling=10**6, state_file=PAUSED_FILE, max_ceiling=10**6)
    assert pauser._ceiling == PAUSE_CEILING_SECONDS == 3600  # never above an hour, whatever is asked
    assert pauser._path.endswith(PAUSED_FILE)


def test_the_pause_watchdog_resumes_and_tells(tmp_path: Any) -> None:
    root = str(tmp_path / "proc")
    write_fake_proc(root, 10, 1, "game", starttime=1000)
    kill, told = FakeKill(), []
    pauser = Freezer(str(tmp_path), root, kill, 0.2, PAUSED_FILE, PAUSE_CEILING_SECONDS, on_watchdog=told.append)
    pauser.freeze([read_proc(10, root)])
    deadline = time.monotonic() + 3
    while not told and time.monotonic() < deadline:
        time.sleep(0.02)
    assert told == [[10]] and (10, SIGCONT) in kill.calls and pauser.recorded() == []


def test_a_failing_notice_never_undoes_the_resume(tmp_path: Any) -> None:
    root = str(tmp_path / "proc")
    write_fake_proc(root, 10, 1, "game", starttime=1000)
    kill = FakeKill()

    def broken(_resumed: list[int]) -> None:
        raise RuntimeError("no loop")

    pauser = Freezer(str(tmp_path), root, kill, 0.1, PAUSED_FILE, PAUSE_CEILING_SECONDS, on_watchdog=broken)
    pauser.freeze([read_proc(10, root)])
    pauser._watchdog_fire()
    assert (10, SIGCONT) in kill.calls and pauser.recorded() == []


def make_app(tmp_path: Any, monkeypatch: Any) -> tuple[Any, FakeKill]:
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    root = tmp_path / "proc"
    write_fake_proc(str(root), 50, 1, "game.exe", starttime=7000)
    write_fake_proc(str(root), 51, 50, "wine", starttime=7001)
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, auto_refresh_manifest=False, home=str(tmp_path / "home"), proc_root=str(root))
    kill = FakeKill()
    app.pauser._kill = kill
    monkeypatch.setattr(
        app_module, "find_game_processes", lambda appid, compat, proc_root: [read_proc(50, proc_root), read_proc(51, proc_root)]
    )
    return app, kill


def test_pause_and_resume_the_running_game(tmp_path: Any, monkeypatch: Any) -> None:
    app, kill = make_app(tmp_path, monkeypatch)

    async def run() -> None:
        with pytest.raises(ValueError, match="no game is running"):
            await app.game_pause()
        app._device_game = APPID
        status = await app.game_pause()
        assert status["paused"] is True and status["game"] == APPID and status["limitMinutes"] == 60
        assert kill.calls == [(50, SIGSTOP), (51, SIGSTOP)]
        assert len(app.pauser.recorded()) == 2 and app.freezer.recorded() == []  # its own record
        again = await app.game_pause()  # a second press changes nothing
        assert again["paused"] is True and len(kill.calls) == 2
        resumed = await app.game_resume()
        assert resumed["paused"] is False and set(kill.calls[2:]) == {(50, SIGCONT), (51, SIGCONT)}
        assert app.pauser.recorded() == [] and app.pauser.status()["watchdogArmed"] is False

    asyncio.run(run())


def test_a_paused_game_is_released_when_it_exits_or_the_module_stops(tmp_path: Any, monkeypatch: Any) -> None:
    app, kill = make_app(tmp_path, monkeypatch)

    async def run() -> None:
        await app.registry.start_all()
        await app.bus.publish("game_started", {"appid": APPID})
        await asyncio.sleep(0)
        app._device_game = APPID
        await app.game_pause()
        await app.bus.publish("game_exited", {"appid": APPID})
        assert (50, SIGCONT) in kill.calls and app.pauser.recorded() == []
        app._device_game = APPID
        await app.game_pause()
        kill.calls.clear()
        await app.set_module_enabled("device", False)
        assert (50, SIGCONT) in kill.calls and app.pauser.recorded() == []
        with pytest.raises(ValueError, match="Device controls are off"):
            await app.game_pause()
        await app.stop()

    asyncio.run(run())


def test_a_pause_left_by_a_crash_is_released_at_the_next_start(tmp_path: Any, monkeypatch: Any) -> None:
    app, kill = make_app(tmp_path, monkeypatch)

    async def crash() -> None:
        app._device_game = APPID
        await app.game_pause()

    asyncio.run(crash())
    app.pauser._disarm_watchdog()  # the process died: no watchdog survives it
    again, kill2 = make_app(tmp_path, monkeypatch)
    assert len(again.pauser.recorded()) == 2

    async def start() -> None:
        await again.start()
        await again.stop()

    asyncio.run(start())
    assert {(50, SIGCONT), (51, SIGCONT)} <= set(kill2.calls) and again.pauser.recorded() == []


def test_unload_releases_a_paused_game(tmp_path: Any, monkeypatch: Any) -> None:
    app, kill = make_app(tmp_path, monkeypatch)

    async def run() -> None:
        app._device_game = APPID
        await app.game_pause()
        await app.stop()

    asyncio.run(run())
    assert (50, SIGCONT) in kill.calls and app.pauser.recorded() == []


def test_no_pause_while_haversack_is_checking_the_saves(tmp_path: Any, monkeypatch: Any) -> None:
    app, kill = make_app(tmp_path, monkeypatch)

    async def run() -> None:
        app._device_game = APPID
        async with app._freeze_lock:
            with pytest.raises(ValueError, match="checking this game's saves"):
                await app.game_pause()

    asyncio.run(run())
    assert kill.calls == []
