"""v0.30.1: the tray never blocks Plasma, and the plugin answers fast with slow or vanished disks."""

from __future__ import annotations

import asyncio
import io
import json
import os
import threading
import time

import pytest

from keepsake import devicechecks, discovery, resolve
from keepsake.desktop import dbus, tray

MS_100 = 0.1


def runtime_with_state(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / tray.STATE_FILE).write_text(json.dumps({"port": 47120, "token": "tok"}))
    return str(runtime)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self):
        self.signals, self.answers, self.pending = [], [], []

    def signal(self, *args):
        self.signals.append(args)

    def answer(self, call, result, error=None):
        self.answers.append((call["member"], result, error))

    def call(self, *args):
        return []


def call(member, iface, path, body=()):
    return {"type": dbus.CALL, "serial": 1, "path": path, "interface": iface, "member": member, "body": list(body)}


CALLS = [
    call("GetAll", tray.PROPS_IFACE, tray.ITEM_PATH, [tray.ITEM_IFACE]),
    call("Get", tray.PROPS_IFACE, tray.ITEM_PATH, [tray.ITEM_IFACE, "ToolTip"]),
    call("GetAll", tray.PROPS_IFACE, tray.MENU_PATH, [tray.MENU_IFACE]),
    call("GetLayout", tray.MENU_IFACE, tray.MENU_PATH, [0, -1, []]),
    call("GetGroupProperties", tray.MENU_IFACE, tray.MENU_PATH, [[], []]),
    call("AboutToShow", tray.MENU_IFACE, tray.MENU_PATH, [0]),
    call("AboutToShowGroup", tray.MENU_IFACE, tray.MENU_PATH, [[0]]),
    call("Event", tray.MENU_IFACE, tray.MENU_PATH, [tray.MENU_OPEN, "clicked", ("s", ""), 0]),
    call("Activate", tray.ITEM_IFACE, tray.ITEM_PATH, [0, 0]),
    call("Ping", "org.freedesktop.DBus.Peer", "/"),
]


def test_every_dbus_call_answers_at_once_while_the_plugin_hangs(tmp_path):
    release = threading.Event()
    asked = []

    def hanging(request, timeout):
        asked.append(timeout)
        release.wait(30)  # a plugin stuck for 30 seconds
        raise OSError("timed out")

    item = tray.Tray(runtime_with_state(tmp_path), "/plugin", FakeConn(), hanging, portal=lambda link: True)
    refresher = threading.Thread(target=item.refresher, daemon=True)
    refresher.start()
    item.request_refresh()
    for _ in range(100):
        if asked:
            break
        time.sleep(0.01)
    assert asked == [1.0]  # the refresher is now stuck in the plugin call, with a 1 s timeout
    try:
        for found in CALLS * 3:
            started = time.perf_counter()
            item.answer(found)
            assert time.perf_counter() - started < MS_100, found["member"]
        assert len(asked) == 1  # only one check in flight, however many asks
    finally:
        item.running = False
        release.set()
        item.wanted.set()
        refresher.join(5)


def test_a_refused_plugin_is_reported_and_open_is_greyed(tmp_path):
    def refused(request, timeout):
        raise ConnectionRefusedError

    item = tray.Tray(runtime_with_state(tmp_path), "/plugin", FakeConn(), refused)
    started = time.perf_counter()
    item.refresh()
    assert time.perf_counter() - started < 1.0
    layout = item.handle(call("GetLayout", tray.MENU_IFACE, tray.MENU_PATH, [0, -1, []]))[1][1]
    assert layout[2][0][1][1]["label"] == ("s", tray.NOT_REACHABLE) and layout[2][2][1][1]["enabled"] == ("b", False)


def test_answers_never_call_the_plugin(tmp_path):
    asked = []

    def counting(request, timeout):
        asked.append(1)
        return Response(json.dumps({"ok": True, "result": {}}).encode())

    item = tray.Tray(runtime_with_state(tmp_path), "/plugin", FakeConn(), counting)
    for found in CALLS:
        item.handle(found)
    assert asked == [] and item.wanted.is_set()  # asked for a check, did not make one


def test_signals_only_on_change_and_at_most_every_two_seconds(tmp_path):
    now = [100.0]
    status = {"conflicts": 0}

    def opener(request, timeout):
        return Response(json.dumps({"ok": True, "result": dict(status)}).encode())

    conn = FakeConn()
    item = tray.Tray(runtime_with_state(tmp_path), "/plugin", conn, opener, clock=lambda: now[0])
    assert item.refresh() is True and len(conn.signals) == 2  # first status: one LayoutUpdated and one NewToolTip
    assert item.refresh() is False and len(conn.signals) == 2  # unchanged: nothing sent
    status["conflicts"] = 1
    now[0] += 0.5
    assert item.refresh() is True and len(conn.signals) == 2  # changed, but too soon: held back
    item.flush_signals()
    assert len(conn.signals) == 2
    now[0] += 2.0
    item.flush_signals()
    assert len(conn.signals) == 4 and conn.signals[-2][4][0] == item.revision
    now[0] += 10.0
    item.flush_signals()
    assert len(conn.signals) == 4  # nothing changed since: nothing sent, however long it has been


def test_a_click_opens_the_window_from_the_refresher_not_the_dbus_thread(tmp_path):
    opened = []

    def opener(request, timeout):
        return Response(json.dumps({"ok": True, "result": {}}).encode())

    item = tray.Tray(
        runtime_with_state(tmp_path), "/plugin", FakeConn(), opener, portal=lambda link: opened.append(link) or True
    )
    item.handle(call("Activate", tray.ITEM_IFACE, tray.ITEM_PATH, [0, 0]))
    assert opened == []  # not on the D-Bus thread
    refresher = threading.Thread(target=item.refresher, daemon=True)
    refresher.start()
    for _ in range(200):
        if opened:
            break
        time.sleep(0.01)
    item.running = False
    item.wanted.set()
    refresher.join(5)
    assert opened == ["http://127.0.0.1:47120/#token=tok"]


# The plugin


def test_the_page_answers_get_status_without_the_event_loop(tmp_path):
    from keepsake import host
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.30.1", home=str(tmp_path))
    stopped_loop = asyncio.new_event_loop()  # never runs: as if the plugin's loop were stuck
    try:
        api = host.Api(app, stopped_loop, "tok", host.Events(), b"")
        started = time.perf_counter()
        status = api.call("get_status", [])
        assert time.perf_counter() - started < MS_100
        assert status == {"version": "0.30.1", "safeMode": False, "busy": None, "scanSlow": False}
    finally:
        stopped_loop.close()


def test_a_scan_held_by_a_slow_disk_uses_the_last_list(tmp_path, monkeypatch):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    monkeypatch.setattr("keepsake.app.SCAN_WAIT", 0.2)
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.30.1", home=str(tmp_path))
    release = threading.Event()
    calls = []

    def stuck():
        calls.append(1)
        release.wait(30)  # a disk spinning up, or gone
        return {"roots": [], "games": []}

    monkeypatch.setattr(app, "_scan_all", stuck)

    async def go():
        with pytest.raises(ValueError, match="disk may be slow"):
            await app.discover_games()  # nothing to fall back on yet
        app._games = {"roots": [], "games": []}
        listed = await app.discover_games(refresh=True)
        status_ms = []
        for _ in range(20):
            started = time.perf_counter()
            await app.get_status()
            status_ms.append(time.perf_counter() - started)
        again = await app.discover_games(refresh=True)
        return listed, status_ms, again

    try:
        listed, status_ms, _again = asyncio.run(go())
    finally:
        release.set()
    assert listed["games"] == [] and app.status_now()["scanSlow"] is True
    assert max(status_ms) < MS_100
    assert len(calls) == 1  # one scan at a time: the second refresh waited on the same one
    app._disk.shutdown(wait=False)


def test_a_manifest_that_vanishes_mid_scan_is_skipped(tmp_path, monkeypatch):
    library = tmp_path / "lib"
    (library / "steamapps").mkdir(parents=True)
    for appid in (10, 20):
        (library / "steamapps" / f"appmanifest_{appid}.acf").write_text(
            f'"AppState" {{ "appid" "{appid}" "name" "Game {appid}" "installdir" "G{appid}" }}'
        )
    real_open = open

    def vanishing(path, *args, **kwargs):
        if str(path).endswith("appmanifest_10.acf"):
            raise FileNotFoundError(path)  # the disk went away between listing and reading
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", vanishing)
    assert [a.appid for a in discovery.read_app_manifests(str(library))] == [20]


@pytest.mark.posix
@pytest.mark.skipif(os.name == "nt", reason="symlinks need POSIX")
def test_a_save_tree_with_a_symlink_loop_and_links_leaving_it_finishes_quickly(tmp_path):
    root = tmp_path / "saves"
    (root / "Game" / "slots").mkdir(parents=True)
    (root / "Game" / "slots" / "a.sav").write_text("a")
    os.symlink(root / "Game", root / "Game" / "slots" / "loop")  # a loop
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "big.bin").write_text("x")
    os.symlink(outside, root / "Game" / "emu-saves")  # EmuDeck-style link leaving the root
    result = resolve.ScanResult()
    started = time.perf_counter()
    resolve.scan(str(root), "Game", False, [], result)
    assert time.perf_counter() - started < 1.0
    assert result.escaped == ["Game/emu-saves"]  # recorded, not walked
    assert all("big.bin" not in str(f) for f in result.files)


@pytest.mark.parametrize(
    ("found", "status"),
    [
        ({"tray": True, "trayMs": 3.0, "statusMs": 2.0, "page": True}, "pass"),
        ({"tray": True, "trayMs": 450.0, "statusMs": 2.0, "page": True}, "fail"),
        ({"tray": True, "trayMs": 3.0, "statusMs": 900.0, "page": True}, "fail"),
        ({"tray": True, "trayMs": None, "statusMs": 2.0, "trayError": "TimeoutError", "page": True}, "fail"),
        ({"tray": False, "trayMs": None, "statusMs": None, "page": False}, "skip"),
    ],
)
def test_device_check(found, status):
    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"tray-responsive": probe})
    outcome = asyncio.run(devicechecks.run("tray-responsive", ctx))
    assert outcome["status"] == status and outcome["title"] == "Desktop tray responsive"
