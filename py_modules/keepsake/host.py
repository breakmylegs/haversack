"""Keepsake without Decky: the headless host for Linux and Windows PCs (ADR-0038, P2).

    python -m keepsake.host [--open] [--port N]

Runs the same :class:`~keepsake.app.KeepsakeApp` the Decky plugin runs, with the
platform's own folders, and serves the desktop UI and a JSON API on loopback only.

Rules for the loopback API (slice 23's acceptance, moved forward):

- Bound to ``127.0.0.1`` only, never another interface.
- The ``Host`` header must be ``127.0.0.1:<port>`` or ``localhost:<port>``, so a web page
  that rebinds its own name to 127.0.0.1 is refused (DNS rebinding).
- Every call carries the per-run token in ``X-Keepsake-Token`` (compared in constant
  time); a page on another origin cannot read or send it. A request with an ``Origin``
  other than the host's own is refused (CSRF).
- Only the callables the Decky plugin exposes (``main.py``) can be called; a test
  keeps the two lists the same.
- Bodies are JSON, at most 1 MiB; answers are JSON with ``no-store`` caching.

The token and port are written to ``host.json`` in the runtime folder, readable only
by the user, so the launcher and the desktop UI can find the running host.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import webbrowser
from collections.abc import Callable, Coroutine, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import discovery, hosts, pcinstall, pcupdate, pcwatch
from .fsutil import atomic_write_json
from .log import log_event
from .paths import PluginPaths

DEFAULT_PORT = 47120  # clear of 8080, 8384, 27040 and 1714 to 1764 (CLAUDE.md), and of Replication's 47110
PORT_TRIES = 10
MAX_BODY = 1024 * 1024
CALL_TIMEOUT = 300.0
STATE_FILE = "host.json"
UI_SCRIPT = re.compile(r"/dist/[a-z][a-z0-9_-]{0,40}\.js")  # the compiled desktop interface (ADR-0040)

# The KeepsakeApp methods the Decky plugin exposes through main.py; tests/test_host.py keeps them equal.
CALLABLES = frozenset(
    {
        "get_status",
        "take_startup_notice",
        "check_for_updates",
        "prepare_update",
        "discover_games",
        "check_running_prefix",
        "manifest_status",
        "refresh_manifest",
        "manifest_progress",
        "match_games",
        "search_titles",
        "get_game",
        "update_game_config",
        "add_custom_path",
        "preview_game",
        "cloud_status",
        "start_signin",
        "cancel_signin",
        "sign_out",
        "test_cloud",
        "backend_config",
        "set_backend_config",
        "modules_status",
        "set_module_enabled",
        "reset_module",
        "steam_probe",
        "steam_ops_claim",
        "steam_ops_finish",
        "steam_ops_list",
        "advisor_view",
        "advisor_select_game",
        "advisor_refresh",
        "advisor_redetect",
        "advisor_settings",
        "advisor_ai_models",
        "advisor_ai_generate",
        "replication_status",
        "replication_set_listener",
        "replication_set_address",
        "replication_open_pairing",
        "replication_close_pairing",
        "replication_pair",
        "replication_answer",
        "replication_cancel",
        "replication_find",
        "replication_check",
        "replication_remove",
        "replication_wake",
        "replication_transfers",
        "replication_pause",
        "replication_resume",
        "replication_stop",
        "replication_send",
        "replication_offers",
        "replication_offer_check",
        "replication_accept",
        "replication_decline",
        "replication_withdraw",
        "replication_dismiss",
        "replication_remove_game",
        "installer_status",
        "installer_start",
        "installer_net_locations",
        "installer_net_remember",
        "installer_net_forget",
        "installer_net_browse",
        "installer_net_download",
        "installer_net_cancel",
        "installer_net_status",
        "installer_create_shortcut",
        "installer_finished_installing",
        "installer_retarget",
        "installer_cancel",
        "installer_add_cd_drive",
        "installer_swap_disc",
        "installer_remove_shortcut",
        "installer_artwork_search",
        "installer_artwork_apply",
        "installer_handoff",
        "steam_ops_file",
        "enable_steam_without_cloud",
        "on_suspend",
        "ludusavi_scan",
        "ludusavi_import",
        "ludusavi_import_all",
        "ludusavi_import_cancel",
        "ludusavi_import_status",
        "set_game_key",
        "approve_match",
        "reject_match",
        "new_game_key",
        "on_game_event",
        "strict_wrap",
        "strict_unwrap",
        "sync_pull",
        "sync_push",
        "bring_newer",
        "game_playtime",
        "scrub_cloud",
        "storage_usage",
        "clear_shader_cache",
        "reset_prefix",
        "cancel_prefix_reset",
        "delete_old_prefix",
        "repair_snapshot",
        "export_snapshots",
        "resolve_conflict",
        "sync_status",
        "idle_pass",
        "snapshot_game",
        "list_snapshots",
        "restore_snapshot",
        "restore_preview",
        "undo_restore",
        "pin_snapshot",
        "release_quarantine",
        "run_retention",
        "qam_summary",
        "sync_now",
        "list_conflicts",
        "conflict_details",
        "recent_history",
        "plan_sync",
        "finish_setup",
        "health_checks",
        "game_config_sync",
        "simulate_sync_job",
        "get_settings",
        "set_setting",
        "get_logs",
        "activity",
        "get_environment",
        "get_steam_probe",
        "get_game_processes",
        "https_test",
        "record_probe_event",
        "signin_probe",
        "export_diagnostics",
        "freeze_test",
    }
)

# Calls only the PC host has: it updates and restarts itself, where Decky has its own installer (ADR-0043).
HOST_CALLABLES = frozenset({"pc_update_status", "pc_update_apply", "pc_rollback", "pc_restart"})
RESTART_DELAY = 0.5  # long enough for the answer to reach the page before the host stops


def _spawn(command: list[str]) -> None:
    subprocess.Popen(command, close_fds=True)


class PcControl:
    """The host-only calls (ADR-0043). Nothing here runs on a Decky device."""

    def __init__(
        self,
        app: Any,
        host: str,
        stop: Callable[[], None],
        env: Mapping[str, str] | None = None,
        spawn: Callable[[list[str]], None] = _spawn,
        fetch: pcupdate.Downloader = pcupdate.download,
    ) -> None:
        self.app, self.host, self._stop, self._env, self._spawn, self._fetch = app, host, stop, env, spawn, fetch
        self._lock = asyncio.Lock()

    def _installed(self) -> dict[str, Any]:
        return pcinstall.installed(self.host, self._env)

    async def pc_update_status(self) -> dict[str, Any]:
        installed = self._installed()
        return {
            "installed": bool(installed.get("version")),
            "running": self.app.version,
            "current": installed.get("version"),
            "previous": installed.get("previous"),
            "busy": self.app.jobs.busy_reason(),
        }

    async def pc_update_apply(self, tag: str) -> dict[str, Any]:
        if not self._installed().get("version"):
            return {"ok": False, "reason": "not-installed"}
        async with self._lock:
            prepared: dict[str, Any] = await asyncio.to_thread(self.app.updater.prepare_desktop, str(tag))
            if not prepared.get("ok"):
                log_event(
                    logging.INFO, "update.pc_refused", "PC update refused", tag=tag, reason=prepared.get("reason")
                )
                return prepared
            try:
                result = await asyncio.to_thread(pcupdate.apply, prepared, self.host, self._fetch, self._env)
            except pcupdate.UpdateError as exc:
                log_event(logging.WARNING, "update.pc_failed", "PC update failed", tag=tag, error=str(exc))
                return {"ok": False, "reason": "install-failed", "detail": str(exc)}
        log_event(logging.INFO, "update.pc_installed", "PC update installed", version=result["version"])
        return result

    async def pc_rollback(self) -> dict[str, Any]:
        async with self._lock:
            try:
                result = await asyncio.to_thread(pcupdate.rollback, self.host, self._env)
            except pcupdate.UpdateError as exc:
                return {"ok": False, "reason": "no-previous", "detail": str(exc)}
        log_event(
            logging.INFO, "update.pc_rollback", "Switched back to the previous version", version=result["version"]
        )
        return result

    async def pc_restart(self) -> dict[str, Any]:
        """Start the installed launcher, which waits for this host to stop, then stop."""
        busy = self.app.jobs.busy_reason()
        if busy:
            return {"ok": False, "reason": "busy", "detail": busy}
        launcher = os.path.join(pcinstall.app_root(self.host, self._env), pcinstall.LAUNCHER)
        if not os.path.isfile(launcher):
            return {"ok": False, "reason": "not-installed"}
        self._spawn([pcinstall.pythonw(sys.executable), launcher, "--restart"])
        asyncio.get_running_loop().call_later(RESTART_DELAY, self._stop)
        return {"ok": True}


def platform_paths(host: str, env: Mapping[str, str] | None = None) -> PluginPaths:
    """Settings, state and logs where the platform keeps them; never inside the program folder."""
    env = os.environ if env is None else env
    package_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if host == "windows":
        roaming = env.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        local = env.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        settings, state = os.path.join(roaming, "Keepsake"), os.path.join(local, "Keepsake")
    else:
        home = os.path.expanduser("~")
        settings = os.path.join(env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "keepsake")
        state = os.path.join(env.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state"), "keepsake")
    return PluginPaths(
        settings_dir=os.path.join(settings, "settings"),
        runtime_dir=os.path.join(state, "runtime"),
        log_dir=os.path.join(state, "logs"),
        plugin_dir=package_root,
    )


class Events:
    """Fan-out of the app's events to every open event stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: list[list[tuple[str, Any]]] = []
        self._cond = threading.Condition(self._lock)

    async def emit(self, event: str, *args: Any) -> None:
        with self._cond:
            for queue in self._queues:
                queue.append((event, list(args)))
            self._cond.notify_all()

    def subscribe(self) -> list[tuple[str, Any]]:
        with self._lock:
            queue: list[tuple[str, Any]] = []
            self._queues.append(queue)
            return queue

    def unsubscribe(self, queue: list[tuple[str, Any]]) -> None:
        with self._lock:
            if queue in self._queues:
                self._queues.remove(queue)

    def wait(self, queue: list[tuple[str, Any]], timeout: float) -> list[tuple[str, Any]]:
        with self._cond:
            if not queue:
                self._cond.wait(timeout)
            items, queue[:] = list(queue), []
            return items


class Api:
    """What the HTTP handler needs: the app, its loop, the token and the events."""

    def __init__(
        self,
        app: Any,
        loop: asyncio.AbstractEventLoop,
        token: str,
        events: Events,
        page: bytes,
        ui_dir: str | None = None,
    ) -> None:
        self.app, self.loop, self.token, self.events, self.page = app, loop, token, events, page
        self.ui_dir = ui_dir  # the built desktop interface (ADR-0040); None serves ``page`` only
        self.control: PcControl | None = None  # the host-only calls, once the host has set them up
        self.port = 0

    def ui_file(self, path: str) -> tuple[bytes, str] | None:
        """A file of the desktop interface, from a fixed list: never a path the request chose."""
        if self.ui_dir is None:
            return (self.page, "text/html; charset=utf-8") if path == "/" else None
        if path == "/":
            name, kind = "index.html", "text/html; charset=utf-8"
        elif path == "/app.css":
            name, kind = "app.css", "text/css; charset=utf-8"
        elif UI_SCRIPT.fullmatch(path):
            name, kind = os.path.join("dist", path.rsplit("/", 1)[1]), "text/javascript; charset=utf-8"
        else:
            return None
        try:
            with open(os.path.join(self.ui_dir, name), "rb") as handle:
                return handle.read(), kind
        except OSError:
            return (self.page, "text/html; charset=utf-8") if path == "/" else None

    def allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def allowed_origins(self) -> set[str]:
        return {f"http://{h}" for h in self.allowed_hosts()}

    def callable(self, name: str) -> bool:
        return name in CALLABLES or (name in HOST_CALLABLES and self.control is not None)

    def call(self, name: str, args: list[Any]) -> Any:
        target = self.control if name in HOST_CALLABLES else self.app
        method: Callable[..., Coroutine[Any, Any, Any]] = getattr(target, name)
        return asyncio.run_coroutine_threadsafe(method(*args), self.loop).result(CALL_TIMEOUT)


def make_handler(api: Api) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Keepsake"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            pass  # requests are never logged: bodies can hold settings, never tokens in logs (T11)

        def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, value: Any) -> None:
            self._send(status, json.dumps(value).encode("utf-8"))

        def _trusted(self, token: str | None) -> bool:
            if self.headers.get("Host", "") not in api.allowed_hosts():
                self._json(421, {"ok": False, "error": "this address is only served as 127.0.0.1"})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in api.allowed_origins():
                self._json(403, {"ok": False, "error": "requests from other sites are refused"})
                return False
            if token is not None and not hmac.compare_digest(token.encode(), api.token.encode()):
                self._json(401, {"ok": False, "error": "open Keepsake from its own launcher"})
                return False
            return True

        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            if parts.path == "/api/events":
                token = (parse_qs(parts.query).get("token") or [""])[0]
                if self._trusted(token):
                    self._stream()
                return
            if not self._trusted(None):
                return
            found = api.ui_file(parts.path)
            if found is None:
                self._json(404, {"ok": False, "error": "not found"})
            else:
                self._send(200, *found)

        def _stream(self) -> None:
            queue = api.events.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    items = api.events.wait(queue, 15.0)
                    chunk = (
                        b"".join(f"event: {event}\ndata: {json.dumps(args)}\n\n".encode() for event, args in items)
                        or b": keep-alive\n\n"
                    )
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except OSError:
                pass  # the page closed the stream
            finally:
                api.events.unsubscribe(queue)

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                self.close_connection = True  # the rest of an oversized body is never read
                self._json(413, {"ok": False, "error": "the request is too large"})
                return
            # Read the (capped) body before any refusal, so the connection closes cleanly.
            raw = self.rfile.read(length)
            if not self._trusted(self.headers.get("X-Keepsake-Token") or ""):
                return
            parts = urlsplit(self.path)
            name = parts.path.removeprefix("/api/call/")
            if not parts.path.startswith("/api/call/") or not api.callable(name):
                self._json(404, {"ok": False, "error": "no such call"})
                return
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                self._json(415, {"ok": False, "error": "send JSON"})
                return
            try:
                body = json.loads(raw or b"{}")
                args = body.get("args", []) if isinstance(body, dict) else None
                if not isinstance(args, list):
                    raise ValueError("args must be a list")
            except ValueError:
                self._json(400, {"ok": False, "error": "the request is not valid JSON"})
                return
            try:
                result = api.call(name, args)
            except (ValueError, TypeError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001 - reported to the page, never a traceback
                self._json(500, {"ok": False, "error": type(exc).__name__})
                return
            self._json(200, {"ok": True, "result": result})

    return Handler


class LoopbackServer(ThreadingHTTPServer):
    """Owns its port outright.

    ``ThreadingHTTPServer`` sets ``SO_REUSEADDR``, which on Windows lets another
    process bind the same port and take the traffic. Reuse is off, and Windows
    gets ``SO_EXCLUSIVEADDRUSE``, so a port already in use is simply refused.
    """

    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def serve(api: Api, port: int = DEFAULT_PORT, tries: int = PORT_TRIES) -> ThreadingHTTPServer:
    """Bind on 127.0.0.1, trying the next ports if one is taken; port 0 picks any free one (tests)."""
    last: OSError | None = None
    for candidate in [port] if port == 0 else range(port, port + tries):
        try:
            server = LoopbackServer(("127.0.0.1", candidate), make_handler(api))
        except OSError as exc:
            last = exc
            continue
        api.port = server.server_address[1]
        threading.Thread(target=server.serve_forever, name="keepsake-host", daemon=True).start()
        return server
    raise OSError(f"no free port from {port}: {last}")


PLACEHOLDER = (
    b"<!doctype html><meta charset=utf-8><title>Keepsake</title>"
    b"<p>Keepsake is running. The desktop interface arrives in a later release (ADR-0038).</p>"
)


def package_version(plugin_dir: str) -> str | None:
    """The installed package's version (its ``VERSION`` file, ADR-0042); None when run from source."""
    try:
        return pcinstall.package_version(plugin_dir)
    except pcinstall.InstallError:
        return None


async def run(port: int, open_browser: bool) -> None:
    from .app import KeepsakeApp

    host = hosts.host()
    paths = platform_paths(host)
    events = Events()
    app = KeepsakeApp(paths, emit=events.emit, host=host, version=package_version(paths.plugin_dir))
    await app.start()
    ui_dir = os.path.join(paths.plugin_dir, "desktop")
    api = Api(app, asyncio.get_running_loop(), secrets.token_urlsafe(32), events, PLACEHOLDER, ui_dir)
    stop = asyncio.Event()
    api.control = PcControl(app, host, stop.set)
    server = serve(api, port)
    os.makedirs(paths.runtime_dir, exist_ok=True)
    atomic_write_json(os.path.join(paths.runtime_dir, STATE_FILE), {"port": api.port, "token": api.token})
    url = f"http://127.0.0.1:{api.port}/#token={api.token}"  # the fragment never reaches a server
    print(f"Keepsake ({host}) is running on http://127.0.0.1:{api.port}/", flush=True)
    if open_browser:
        webbrowser.open(url)
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    # Games start and exit outside Keepsake on a PC: watch for them (ADR-0038, P4).
    async def watched_games() -> list[dict[str, Any]]:
        return list((await app.discover_games())["games"])

    watcher = pcwatch.Watcher(watched_games, app.on_game_event, home=discovery.real_home(None))
    watching = asyncio.create_task(watcher.run(stop))
    try:
        await stop.wait()
    finally:
        await watching
        server.shutdown()
        await app.stop()
        try:
            os.unlink(os.path.join(paths.runtime_dir, STATE_FILE))  # a stopped host leaves no token behind
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m keepsake.host", description="Keepsake on a PC (ADR-0038)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="open the desktop interface in the browser")
    options = parser.parse_args(argv)
    asyncio.run(run(options.port, options.open))
    return 0


if __name__ == "__main__":
    sys.exit(main())
