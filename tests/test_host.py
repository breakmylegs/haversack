"""The headless PC host (ADR-0038, P2): loopback API rules, against a fake app. Synthetic data only."""

import ast
import asyncio
import http.client
import json
import pathlib
import socket
import sys
import threading

import pytest

from keepsake import host as host_module

ROOT = pathlib.Path(__file__).resolve().parent.parent


class FakeApp:
    def __init__(self):
        self.calls = []

    async def get_status(self):
        self.calls.append("get_status")
        return {"ok": True}

    async def set_setting(self, key, value):
        self.calls.append(("set_setting", key, value))
        if key == "bad":
            raise ValueError("that setting is not valid")
        return {key: value}

    async def sync_now(self):
        raise RuntimeError("synthetic failure with /home/someone/secret in it")


@pytest.fixture
def running():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    events = host_module.Events()
    api = host_module.Api(FakeApp(), loop, "synthetic-token", events, b"<p>ui</p>")
    server = host_module.serve(api, port=0)
    yield api, loop
    server.shutdown()
    server.server_close()
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)


def request(api, method, path, body=None, headers=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    send = {"Host": host or f"127.0.0.1:{api.port}", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        send.setdefault("Content-Type", "application/json")
        send["Content-Length"] = str(len(data))
    conn.request(method, path, body=data, headers=send)
    response = conn.getresponse()
    payload = response.read()
    conn.close()
    return response.status, payload, dict(response.getheaders())


def call(api, name, args, **kw):
    headers = {"X-Keepsake-Token": "synthetic-token", **kw.pop("headers", {})}
    status, payload, _ = request(api, "POST", f"/api/call/{name}", {"args": args}, headers=headers, **kw)
    return status, json.loads(payload)


def test_a_call_with_the_token_reaches_the_app(running):
    api, _ = running
    assert call(api, "set_setting", ["deviceName", "Synthetic"]) == (
        200,
        {"ok": True, "result": {"deviceName": "Synthetic"}},
    )
    assert call(api, "get_status", []) == (200, {"ok": True, "result": {"ok": True}})


def test_errors_are_plain_and_never_leak_details(running):
    api, _ = running
    assert call(api, "set_setting", ["bad", 1]) == (400, {"ok": False, "error": "that setting is not valid"})
    status, body = call(api, "sync_now", [])
    assert status == 500 and body == {"ok": False, "error": "RuntimeError"}  # no message, so no paths


@pytest.mark.parametrize(
    ("headers", "host", "status"),
    [
        ({"X-Keepsake-Token": "wrong"}, None, 401),
        ({}, None, 401),
        ({"X-Keepsake-Token": "synthetic-token"}, "evil.example", 421),  # DNS rebinding: a foreign name
        ({"X-Keepsake-Token": "synthetic-token", "Origin": "http://evil.example"}, None, 403),  # CSRF
    ],
)
def test_untrusted_requests_are_refused(running, headers, host, status):
    api, _ = running
    got, _payload, _ = request(api, "POST", "/api/call/get_status", {"args": []}, headers=headers, host=host)
    assert got == status and api.app.calls == []


def test_only_the_plugin_callables_can_be_called(running):
    api, _ = running
    assert call(api, "__init__", [])[0] == 404 and call(api, "_store", [])[0] == 404


class FakeControl:
    async def pc_update_status(self):
        return {"installed": True}


def test_host_only_calls_exist_only_once_the_host_has_set_them_up(running):
    api, _ = running
    assert call(api, "pc_update_status", [])[0] == 404
    api.control = FakeControl()
    assert call(api, "pc_update_status", []) == (200, {"ok": True, "result": {"installed": True}})
    assert call(api, "pc_update_status", [], headers={"X-Keepsake-Token": "wrong"})[0] == 401
    assert call(api, "_lock", [])[0] == 404 and api.app.calls == []


def test_request_shape_rules(running):
    api, _ = running
    headers = {"X-Keepsake-Token": "synthetic-token", "Content-Type": "text/plain"}
    assert request(api, "POST", "/api/call/get_status", {"args": []}, headers=headers)[0] == 415
    status, _body = call(api, "get_status", None)  # args must be a list
    assert status == 400
    big = {"X-Keepsake-Token": "synthetic-token", "Content-Length": str(host_module.MAX_BODY + 1)}
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    conn.putrequest("POST", "/api/call/get_status", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{api.port}")
    for k, v in {**big, "Content-Type": "application/json"}.items():
        conn.putheader(k, v)
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()


def test_the_page_is_served_with_strict_headers_only_on_its_own_name(running):
    api, _ = running
    status, payload, headers = request(api, "GET", "/")
    assert status == 200 and payload == b"<p>ui</p>"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"] and headers["Cache-Control"] == "no-store"
    assert request(api, "GET", "/", host="rebound.example")[0] == 421


def test_events_reach_an_open_stream(running):
    api, loop = running
    conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    conn.request("GET", "/api/events?token=synthetic-token", headers={"Host": f"127.0.0.1:{api.port}"})
    response = conn.getresponse()
    assert response.status == 200 and response.getheader("Content-Type") == "text/event-stream"
    assert response.readline() == b": connected\n"
    response.readline()
    asyncio.run_coroutine_threadsafe(api.events.emit("keepsake_signin", {"status": "signed-in"}), loop).result(5)
    assert response.readline() == b"event: keepsake_signin\n"
    assert json.loads(response.readline().removeprefix(b"data: ")) == [{"status": "signed-in"}]
    conn.close()
    status, _, _ = request(api, "GET", "/api/events?token=wrong")
    assert status == 401


def test_the_desktop_interface_is_served_from_a_fixed_list_only(tmp_path):
    ui = tmp_path / "desktop"
    (ui / "dist").mkdir(parents=True)
    (ui / "index.html").write_text("<p>desktop</p>")
    (ui / "app.css").write_text("body{}")
    (ui / "dist" / "main.js").write_text("export {};")
    (tmp_path / "secret.txt").write_text("not for the page")
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    api = host_module.Api(FakeApp(), loop, "synthetic-token", host_module.Events(), b"placeholder", str(ui))
    server = host_module.serve(api, port=0)
    try:
        status, body, headers = request(api, "GET", "/")
        assert (status, body) == (200, b"<p>desktop</p>")
        status, body, headers = request(api, "GET", "/dist/main.js")
        assert status == 200 and headers["Content-Type"].startswith("text/javascript") and body == b"export {};"
        assert request(api, "GET", "/app.css")[2]["Content-Type"].startswith("text/css")
        (ui / "dist" / "helpPage.js").write_text("export const x = 1;")
        assert request(api, "GET", "/dist/helpPage.js")[0] == 200  # mixed case: refused before v0.57.0
        for path in (
            "/dist/../secret.txt",
            "/dist/%2e%2e%2fsecret.txt",
            "/../secret.txt",
            "/dist/Main.JS",
            "/dist/main.js.map",
            "/secret.txt",
            "/dist/sub/main.js",
            "/index.html",
        ):
            assert request(api, "GET", path)[0] == 404, path
        (ui / "index.html").unlink()
        assert request(api, "GET", "/")[1] == b"placeholder"  # not built yet: the placeholder page
    finally:
        server.shutdown()
        server.server_close()
        loop.call_soon_threadsafe(loop.stop)


def test_every_desktop_module_is_one_the_host_serves():
    """Each desktop/src file compiles to dist/<name>.js; a name the host refuses breaks the whole app,
    as helpPage.js and looksPage.js did from v0.52.0 to v0.56.0 (it stayed on "Loading")."""
    names = [p.stem for p in (ROOT / "desktop" / "src").glob("*.ts")]
    assert "helpPage" in names and "main" in names
    for name in names:
        assert host_module.UI_SCRIPT.fullmatch(f"/dist/{name}.js"), name


def test_the_callables_match_the_decky_plugin():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    plugin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Plugin")
    exposed = {f.name for f in plugin.body if isinstance(f, ast.AsyncFunctionDef) and not f.name.startswith("_")}
    decky_only = {"rename_status", "rename_finish"}  # the move from Keepsake happens only under Decky (ADR-0089)
    assert exposed - decky_only == set(host_module.CALLABLES)


@pytest.mark.parametrize("which", ["windows", "linux-desktop"])
def test_on_a_pc_the_installer_is_unavailable_and_advisor_starts_off(tmp_path, which):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, auto_refresh_manifest=False, home=str(tmp_path), host=which)
    status = {m["name"]: m for m in asyncio.run(app.registry.status())}
    assert status["installer"]["available"] is False and "needs Decky" in status["installer"]["unavailableReason"]
    assert status["advisor"]["flag"] is False and status["saves"]["flag"] is True
    decky = KeepsakeApp(paths, auto_refresh_manifest=False, home=str(tmp_path))
    status = {m["name"]: m for m in asyncio.run(decky.registry.status())}
    assert status["installer"]["available"] is True and status["advisor"]["flag"] is True


def test_platform_folders(tmp_path):
    win = host_module.platform_paths(
        "windows", {"APPDATA": str(tmp_path / "Roaming"), "LOCALAPPDATA": str(tmp_path / "Local")}
    )
    assert win.settings_dir == str(tmp_path / "Roaming" / "Keepsake" / "settings")
    assert win.runtime_dir == str(tmp_path / "Local" / "Keepsake" / "runtime")
    linux = host_module.platform_paths("linux-desktop", {"XDG_CONFIG_HOME": "/c", "XDG_STATE_HOME": "/s"})
    assert linux.settings_dir.replace("\\", "/") == "/c/keepsake/settings"
    assert linux.log_dir.replace("\\", "/") == "/s/keepsake/logs"


@pytest.mark.skipif(sys.platform != "win32", reason="SO_EXCLUSIVEADDRUSE is Windows only")
def test_another_program_cannot_bind_over_the_host_port(running):
    api, _ = running
    hijacker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    hijacker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # what a hijacker would ask for
    try:
        with pytest.raises(OSError):
            hijacker.bind(("127.0.0.1", api.port))
    finally:
        hijacker.close()


def test_a_taken_port_moves_to_the_next(running):
    api, loop = running
    other = host_module.Api(FakeApp(), loop, "t", host_module.Events(), b"")
    server = host_module.serve(other, port=api.port, tries=3)
    try:
        assert other.port != api.port and api.port < other.port <= api.port + 2
    finally:
        server.shutdown()
        server.server_close()
