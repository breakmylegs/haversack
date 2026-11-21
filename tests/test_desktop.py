"""The desktop app with the plugin (ADR-0068): D-Bus wire format, entries, the tray, the module and its check."""

from __future__ import annotations

import asyncio
import io
import json
import os
import struct

import pytest

from keepsake import devicechecks
from keepsake.app import KeepsakeApp
from keepsake.desktop import dbus, entries, tray
from keepsake.paths import PluginPaths

# D-Bus


@pytest.mark.parametrize(
    ("signature", "values"),
    [
        ("y", [7]),
        ("b", [True]),
        ("nqiuxt", [-2, 3, -4, 5, -6, 7]),
        ("d", [1.5]),
        ("sog", ["héllo", "/a/b", "a{sv}"]),
        ("as", [["a", "bb", ""]]),
        ("a{sv}", [{"x": ("i", 1), "y": ("s", "z"), "z": ("as", ["p"])}]),
        ("(ia{sv}av)", [(1, {"label": ("s", "Open")}, [("(ia{sv}av)", (2, {}, []))])]),
        ("u(ia{sv}av)", [3, (0, {}, [])]),
        ("a(ia{sv})", [[(1, {"enabled": ("b", False)}), (2, {})]]),
        ("ai", [[]]),
        ("(sa(iiay)ss)", [("", [(1, 1, [255, 0])], "Keepsake", "ok")]),
    ],
)
def test_wire_format_round_trips(signature, values):
    data = dbus.marshal(signature, values)
    back = dbus.unmarshal(signature, data)
    normalised = json.loads(json.dumps(back))
    assert normalised == json.loads(json.dumps(values))


def test_alignment_and_bad_signatures():
    assert dbus.marshal("yu", [1, 2]) == b"\x01\x00\x00\x00\x02\x00\x00\x00"
    assert dbus.marshal("yt", [1, 2])[8:] == struct.pack("<Q", 2)
    assert dbus.split("sa{sv}(ii)v") == ["s", "a{sv}", "(ii)", "v"]
    for bad in ("(ii", "a", "z", "(i}"):
        with pytest.raises(dbus.DBusError):
            dbus.split(bad)
    with pytest.raises(dbus.DBusError):
        dbus.unmarshal("s", b"\x05\x00\x00\x00ab")  # truncated


def test_messages_round_trip_and_wait_for_whole_messages():
    raw = dbus.message(dbus.CALL, 5, {1: "/StatusNotifierItem", 2: "org.x", 3: "Get", 6: ":1.2"}, "ss", ["a", "b"])
    found, length = dbus.parse(raw + b"extra")
    assert length == len(raw)
    assert (found["type"], found["serial"], found["path"], found["member"], found["body"]) == (
        dbus.CALL,
        5,
        "/StatusNotifierItem",
        "Get",
        ["a", "b"],
    )
    assert dbus.parse(raw[:-1]) is None and dbus.parse(b"l\x01") is None
    with pytest.raises(dbus.DBusError):
        dbus.parse(b"B" + raw[1:])


def test_session_socket(monkeypatch, tmp_path):
    assert dbus.session_socket("unix:path=/run/user/1000/bus,guid=x") == "/run/user/1000/bus"
    assert dbus.session_socket("unix:abstract=/tmp/dbus-x;tcp:host=y") == "\0/tmp/dbus-x"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert dbus.session_socket("") is None
    (tmp_path / "bus").write_text("")
    assert dbus.session_socket("") == os.path.join(str(tmp_path), "bus")


# Entries


def test_entries_are_written_for_this_version_and_refreshed(tmp_path):
    home, plugin, runtime = tmp_path / "home", tmp_path / "plugins" / "Keepsake", tmp_path / "data" / "runtime"
    written = entries.install(str(home), str(plugin), str(runtime), "0.27.0-beta.2")
    assert len(written) == 2
    autostart = entries.read(entries.paths(str(home))["autostart"])
    menu = entries.read(entries.paths(str(home))["appMenu"])
    assert autostart["Type"] == "Application" and autostart["NoDisplay"] == "true" and "--open" not in autostart["Exec"]
    assert menu["Exec"].endswith("--open") and menu["Categories"] == "Game;Utility;"
    assert autostart["Exec"].startswith("python3 ") and "--runtime" in autostart["Exec"]
    assert autostart[entries.MARKER] == "0.27.0-beta.2"
    assert entries.install(str(home), str(plugin), str(runtime), "0.27.0-beta.2") == []  # unchanged: not rewritten
    assert len(entries.install(str(home), str(plugin), str(runtime), "0.27.0-beta.3")) == 2  # an update rewrites
    assert entries.read(entries.paths(str(home))["appMenu"])[entries.MARKER] == "0.27.0-beta.3"


def test_quoting_paths_with_spaces():
    text = entries.render("autostart", "/home/deck/my plugins/Keepsake", "/home/deck/data 100%", "1.0.0")
    line = next(x for x in text.splitlines() if x.startswith("Exec="))
    assert '"/home/deck/my plugins/Keepsake/py_modules/keepsake/desktop/tray.py"' in line
    assert '"/home/deck/data 100%%"' in line  # % is doubled in Exec


def test_remove_only_deletes_keepsakes_own_files(tmp_path):
    home = tmp_path / "home"
    entries.install(str(home), str(tmp_path / "p"), str(tmp_path / "r"), "1.0.0")
    mine = entries.paths(str(home))["appMenu"]
    with open(mine, "w", encoding="utf-8") as handle:
        handle.write("[Desktop Entry]\nType=Application\nName=My own\nExec=true\n")
    assert entries.remove(str(home)) == [entries.paths(str(home))["autostart"]]
    assert os.path.exists(mine)  # the user's own file of the same name stays
    assert entries.install(str(home), str(tmp_path / "p"), str(tmp_path / "r"), "1.0.0") == [
        entries.paths(str(home))["autostart"]
    ]  # and is never overwritten


def test_check_reports_missing_old_and_broken_entries(tmp_path):
    home, plugin = tmp_path / "home", tmp_path / "p"
    assert entries.check(str(home), str(plugin), "1.0.0") == {"autostart": ["missing"], "appMenu": ["missing"]}
    entries.install(str(home), str(plugin), str(tmp_path / "r"), "0.9.0")
    found = entries.check(str(home), str(plugin), "1.0.0")
    assert "names version 0.9.0" in found["autostart"] and "its icon is missing" in found["autostart"]
    icon = plugin / "assets" / "icons" / "hicolor" / "256x256" / "apps" / "keepsake-tray.png"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b"png")
    entries.install(str(home), str(plugin), str(tmp_path / "r"), "1.0.0")
    assert entries.check(str(home), str(plugin), "1.0.0") == {"autostart": [], "appMenu": []}
    assert entries.check(str(home), str(tmp_path / "other"), "1.0.0")["appMenu"][0] == "does not run this plugin's tray"


# The tray


class FakeConn:
    def __init__(self, portal_fails=False):
        self.calls, self.signals, self.answers, self.pending = [], [], [], []
        self.portal_fails = portal_fails

    def call(self, *args):
        self.calls.append(args)
        if self.portal_fails and args[0] == "org.freedesktop.portal.Desktop":
            raise dbus.DBusError("no portal")
        return []

    def signal(self, *args):
        self.signals.append(args)

    def answer(self, call, result, error=None):
        self.answers.append((call["member"], result, error))


def opener_for(status, ok=True):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(request, timeout):
        assert request.headers.get("X-keepsake-token") == "tok" and request.full_url.endswith("/api/call/get_status")
        return Response(json.dumps({"ok": ok, "result": status}).encode())

    return opener


def runtime_with_state(tmp_path, port=47120):
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / tray.STATE_FILE).write_text(json.dumps({"port": port, "token": "tok"}))
    return str(runtime)


def test_backend_status_line(tmp_path):
    runtime = runtime_with_state(tmp_path)
    assert tray.backend(runtime, opener_for({"conflicts": 0})) == (
        "http://127.0.0.1:47120/#token=tok",
        "Keepsake is running",
    )
    assert tray.backend(runtime, opener_for({"conflicts": 2}))[1] == "Keepsake is running: 2 save conflicts to resolve"
    assert tray.backend(runtime, opener_for({}, ok=False)) == (None, tray.NOT_REACHABLE)

    def refused(request, timeout):
        raise OSError("connection refused")

    assert tray.backend(runtime, refused) == (None, tray.NOT_REACHABLE)
    assert tray.backend(str(tmp_path / "nothing"), refused) == (None, tray.NOT_REACHABLE)
    bad = runtime_with_state(tmp_path / "b", port=99999)
    assert tray.backend(bad, opener_for({})) == (None, tray.NOT_REACHABLE)


def call(member, iface, path, body=()):
    return {"type": dbus.CALL, "serial": 1, "path": path, "interface": iface, "member": member, "body": list(body)}


def test_tray_properties_menu_and_events(tmp_path, monkeypatch):
    conn = FakeConn()
    item = tray.Tray(runtime_with_state(tmp_path), "/plugin", conn, opener_for({"conflicts": 0}))
    item.refresh()  # the refresher's first check
    props = item.handle(call("GetAll", tray.PROPS_IFACE, tray.ITEM_PATH, [tray.ITEM_IFACE]))[1][0]
    assert props["Status"] == ("s", "Active") and props["Menu"] == ("o", tray.MENU_PATH)
    assert props["IconThemePath"] == ("s", os.path.join("/plugin", "assets", "icons"))
    assert item.handle(call("Get", tray.PROPS_IFACE, tray.MENU_PATH, [tray.MENU_IFACE, "Version"])) == ("v", [("u", 3)])
    _revision, layout = item.handle(call("GetLayout", tray.MENU_IFACE, tray.MENU_PATH, [0, -1, []]))[1]
    labels = [child[1][1].get("label", ("s", "-"))[1] for child in layout[2]]
    assert labels == ["Keepsake is running", "-", "Open Keepsake", "Quit"]
    assert layout[2][2][1][1]["enabled"] == ("b", True)
    item.handle(call("Event", tray.MENU_IFACE, tray.MENU_PATH, [tray.MENU_OPEN, "clicked", ("s", ""), 0]))
    assert item.open_after and item.wanted.is_set()  # the refresher opens it, never the D-Bus thread
    item.open_after = False
    item.wanted.clear()
    item.handle(call("Activate", tray.ITEM_IFACE, tray.ITEM_PATH, [0, 0]))
    assert item.open_after and item.wanted.is_set()
    assert item.running is True
    item.handle(call("EventGroup", tray.MENU_IFACE, tray.MENU_PATH, [[(tray.MENU_QUIT, "clicked", ("s", ""), 0)]]))
    assert item.running is False  # Quit stops the tray
    with pytest.raises(KeyError):
        item.handle(call("Nonsense", tray.ITEM_IFACE, tray.ITEM_PATH))
    found = item.handle(call("GetGroupProperties", tray.MENU_IFACE, tray.MENU_PATH, [[tray.MENU_QUIT], []]))
    assert found == ("a(ia{sv})", [[(tray.MENU_QUIT, {"label": ("s", "Quit")})]])
    assert item.handle(call("Ping", "org.freedesktop.DBus.Peer", "/")) is None


def test_unreachable_backend_says_so_and_greys_out_open(tmp_path):
    def refused(request, timeout):
        raise OSError

    item = tray.Tray(str(tmp_path), "/plugin", FakeConn(), refused)
    item.refresh()
    layout = item.handle(call("GetLayout", tray.MENU_IFACE, tray.MENU_PATH, [0, -1, []]))[1][1]
    assert layout[2][0][1][1]["label"] == ("s", tray.NOT_REACHABLE)
    assert layout[2][2][1][1]["enabled"] == ("b", False)
    assert item.open_window() is False


def test_refresh_signals_only_on_change_and_window_opens_through_the_portal(tmp_path):
    conn = FakeConn()
    runtime = runtime_with_state(tmp_path)
    status = {"conflicts": 0}
    now = [0.0]
    opened = []
    item = tray.Tray(
        runtime,
        "/plugin",
        conn,
        lambda r, timeout: opener_for(status)(r, timeout),
        portal=lambda link: opened.append(link) or True,
        clock=lambda: now[0],
    )
    assert item.refresh() is True and conn.signals[0][2] == "LayoutUpdated" and item.revision == 2  # first status
    assert item.refresh() is False and len(conn.signals) == 2  # unchanged: nothing sent
    status["conflicts"] = 1
    now[0] += 5
    assert item.refresh() is True and len(conn.signals) == 4 and item.revision == 3
    assert item.open_window() is True
    assert opened == ["http://127.0.0.1:47120/#token=tok"]  # through the portal, on its own connection


def test_window_falls_back_to_the_desktops_browser(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    item = tray.Tray(runtime_with_state(tmp_path), "/plugin", FakeConn(), opener_for({}), portal=lambda link: False)
    assert item.open_window() is True and opened == ["http://127.0.0.1:47120/#token=tok"]


def test_hand_over_finds_no_running_tray():
    assert tray.hand_over("open", "\0keepsake-tray-test-nobody") is False


def test_tray_registers_with_the_watcher(tmp_path):
    conn = FakeConn()
    tray.Tray(str(tmp_path), "/plugin", conn, opener_for({})).register()
    assert conn.calls[0][3] == "RequestName" and conn.calls[1][:4] == (*tray.WATCHER, "RegisterStatusNotifierItem")


# The module


def _app(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    return KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.27.0-beta.2", home=str(home)), home


def test_desktop_up_serves_writes_state_and_entries_then_down_clears_the_token(tmp_path):
    app, home = _app(tmp_path)

    async def go():
        app._loop = asyncio.get_running_loop()
        await asyncio.to_thread(app._desktop_up)
        state = json.loads((tmp_path / "runtime" / "host.json").read_text())
        health = await asyncio.to_thread(app._desktop_health)
        await asyncio.to_thread(app._desktop_down)
        return state, health

    state, health = asyncio.run(go())
    assert state["port"] and len(state["token"]) > 30
    assert not (tmp_path / "runtime" / "host.json").exists()  # no token left behind
    assert entries.read(entries.paths(str(home))["autostart"])[entries.MARKER] == "0.27.0-beta.2"
    assert health[0]["status"] == "ok"
    assert app._desktop_server is None


def test_switching_desktop_off_removes_the_entries_and_leftovers_are_reported(tmp_path):
    app, home = _app(tmp_path)
    app.host = "decky"
    entries.install(str(home), str(tmp_path / "plugin"), str(tmp_path / "runtime"), "0.27.0-beta.2")

    async def go():
        await app.set_module_enabled("desktop", False)
        gone = [os.path.exists(p) for p in entries.paths(str(home)).values()]
        entries.install(str(home), str(tmp_path / "plugin"), str(tmp_path / "runtime"), "0.27.0-beta.2")
        return gone, app._desktop_leftovers()

    gone, leftovers = asyncio.run(go())
    assert gone == [False, False]
    assert leftovers[0]["id"] == "desktop-leftovers" and len(leftovers[0]["items"]) == 2


def test_desktop_is_on_by_default():
    from keepsake.modules import DEFAULT_FLAGS

    assert DEFAULT_FLAGS["desktop"] is True


def test_decky_uninstall_removes_the_entries(tmp_path, monkeypatch):
    import importlib.util

    home = tmp_path / "home"
    entries.install(str(home), str(tmp_path / "p"), str(tmp_path / "r"), "1.0.0")
    monkeypatch.setenv("DECKY_USER_HOME", str(home))
    spec = importlib.util.spec_from_file_location(
        "decky_main", os.path.join(os.path.dirname(__file__), "..", "main.py")
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(__import__("sys").modules, "decky", type("decky", (), {})())
    try:
        spec.loader.exec_module(module)
    except Exception:  # main.py needs Decky's own module to load fully
        pytest.skip("main.py needs Decky's runtime")
    asyncio.run(module.Plugin()._uninstall())
    assert not any(os.path.exists(p) for p in entries.paths(str(home)).values())


@pytest.mark.parametrize(
    ("found", "status"),
    [
        ({"entries": {"autostart": [], "appMenu": []}, "python3": True, "sessionBus": True, "page": True}, "pass"),
        ({"entries": {"autostart": [], "appMenu": []}, "python3": True, "sessionBus": False, "page": True}, "warn"),
        (
            {"entries": {"autostart": ["missing"], "appMenu": []}, "python3": True, "sessionBus": True, "page": True},
            "fail",
        ),
        ({"entries": {"autostart": [], "appMenu": []}, "python3": False, "sessionBus": True, "page": True}, "fail"),
    ],
)
def test_device_check(found, status):
    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"desktop-app": probe})
    outcome = asyncio.run(devicechecks.run("desktop-app", ctx))
    assert outcome["status"] == status and outcome["title"] == "Desktop app ready"
    assert (
        asyncio.run(devicechecks.run("desktop-app", devicechecks.Context("", "", "", "", {}, "")))["status"] == "skip"
    )


def test_quoting_escapes_what_the_specification_reserves():
    text = entries.render("appMenu", '/home/deck/odd "$name"', "/r", "1.0.0")
    line = next(x for x in text.splitlines() if x.startswith("Exec="))
    assert r'"/home/deck/odd \"\$name\"/py_modules/keepsake/desktop/tray.py"' in line


def test_no_leftover_warning_while_desktop_is_on(tmp_path, monkeypatch):
    app, home = _app(tmp_path)
    app.host = "decky"
    entries.install(str(home), str(tmp_path / "plugin"), str(tmp_path / "runtime"), "0.27.0-beta.2")
    monkeypatch.setattr(app.registry, "enabled", lambda name: name == "desktop")
    assert app._desktop_leftovers() == []


def test_device_check_needs_the_page_running():
    found = {"entries": {"autostart": [], "appMenu": []}, "python3": True, "sessionBus": True, "page": False}

    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"desktop-app": probe})
    outcome = asyncio.run(devicechecks.run("desktop-app", ctx))
    assert outcome["status"] == "warn" and "page is not running" in outcome["found"]


def test_the_portal_uses_its_own_connection_and_reports_failure(monkeypatch):
    calls = []

    class Conn:
        def __init__(self, timeout):
            calls.append(("open", timeout))

        def call(self, *args):
            calls.append(args[3])
            return []

        def close(self):
            calls.append("close")

    monkeypatch.setattr(dbus, "Connection", Conn)
    assert tray.open_with_portal("http://127.0.0.1:1/#token=t") is True
    assert calls == [("open", 2.0), "OpenURI", "close"]

    def no_bus(timeout):
        raise dbus.DBusError("no session bus")

    monkeypatch.setattr(dbus, "Connection", no_bus)
    assert tray.open_with_portal("http://127.0.0.1:1/#token=t") is False
