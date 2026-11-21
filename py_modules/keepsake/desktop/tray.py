"""Keepsake's tray icon in Desktop Mode, run by the system ``python3`` (ADR-0017, ADR-0018, ADR-0068).

    python3 tray.py --runtime <plugin runtime folder> [--open]

Started minimised at Desktop login by ``keepsake-tray.desktop``: only the tray icon, no window.
The app-menu entry adds ``--open``. Only one tray runs per user: a second start hands ``open`` to
the running one through an abstract Unix socket and exits, so the app menu brings up the running
one, never a second copy.

- **Icon:** a StatusNotifierItem on the session bus (``org.kde.StatusNotifierItem``), with a
  ``com.canonical.dbusmenu`` menu: a status line, **Open Keepsake** and **Quit**. Clicking the
  icon opens Keepsake. Quit stops the tray until the next login.
- **Window:** the desktop interface the plugin serves on 127.0.0.1 (ADR-0039), opened in the
  default browser through the desktop portal's ``OpenURI``, else Python's ``webbrowser``. Closing
  that window leaves the tray running.
- **Backend:** ``host.json`` in the runtime folder names the port and token; the tray trusts it
  only after a token-protected call answers. If the plugin cannot be reached, the status line says
  so plainly instead of failing silently.

**The D-Bus thread never waits** (v0.30.1, the plasmashell hang). Plasma calls a StatusNotifierItem
synchronously, so a reply that waits on anything slow freezes the taskbar. Every call is answered at
once from cached state. Checking the plugin happens only on one refresher thread, with a 1-second
timeout and at most one check at a time; ``AboutToShow`` and clicks only ask for one. Opening the
window uses its own short-lived D-Bus connection, so one thread alone reads the main socket. Signals
go out only when the status changes, at most once every two seconds.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import sys
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any

if __package__ in (None, ""):  # run as a script by the system python3: find the keepsake package
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from keepsake.desktop import dbus

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
ITEM_IFACE = "org.kde.StatusNotifierItem"
MENU_IFACE = "com.canonical.dbusmenu"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
WATCHER = ("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher")
STATE_FILE = "host.json"
CHECK_EVERY = 30.0
CHECK_TIMEOUT = 1.0  # the plugin answers from memory: anything slower is "not reachable"
SIGNAL_GAP = 2.0  # signals at most this often, so they can never flood the bus
MENU_STATUS, MENU_OPEN, MENU_QUIT = 1, 2, 3
NOT_REACHABLE = "Keepsake's plugin cannot be reached from Desktop Mode. Is Decky Loader running?"


def instance_address() -> str:
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return f"\0keepsake-tray-{uid}"


def hand_over(command: str, address: str | None = None) -> bool:
    """Give ``command`` to a running tray. True when one took it."""
    if not hasattr(socket, "AF_UNIX"):
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined, unused-ignore]
    sock.settimeout(2)
    try:
        sock.connect(address or instance_address())
        sock.sendall(command.encode() + b"\n")
        return sock.recv(16).startswith(b"ok")
    except OSError:
        return False
    finally:
        sock.close()


def backend(
    runtime_dir: str, opener: Any = urllib.request.urlopen, timeout: float = CHECK_TIMEOUT
) -> tuple[str | None, str]:
    """``(link, status)``: the desktop interface's link when the plugin answers, and a status line."""
    try:
        with open(os.path.join(runtime_dir, STATE_FILE), encoding="utf-8") as handle:
            state = json.load(handle)
        port, token = int(state["port"]), str(state["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return None, NOT_REACHABLE
    if not 1 <= port <= 65535 or not token:
        return None, NOT_REACHABLE
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/call/get_status",
        data=b'{"args": []}',
        headers={"Content-Type": "application/json", "X-Keepsake-Token": token},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            answer = json.loads(response.read(65536) or b"{}")
    except (OSError, ValueError):
        return None, NOT_REACHABLE
    if not isinstance(answer, dict) or not answer.get("ok"):
        return None, NOT_REACHABLE
    status = answer.get("result") if isinstance(answer.get("result"), dict) else {}
    line = "Keepsake is running"
    conflicts = int(status.get("conflicts") or 0) if isinstance(status, dict) else 0
    if conflicts:
        line += f": {conflicts} save {'conflict' if conflicts == 1 else 'conflicts'} to resolve"
    return f"http://127.0.0.1:{port}/#token={token}", line


def menu_layout(status: str, reachable: bool) -> tuple[Any, ...]:
    """The dbusmenu layout ``(ia{sv}av)``: the root and its three items."""

    def item(item_id: int, props: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
        return ("(ia{sv}av)", (item_id, props, []))

    children = [
        item(MENU_STATUS, {"label": ("s", status), "enabled": ("b", False)}),
        item(10, {"type": ("s", "separator")}),
        item(MENU_OPEN, {"label": ("s", "Open Keepsake"), "enabled": ("b", reachable)}),
        item(MENU_QUIT, {"label": ("s", "Quit")}),
    ]
    return (0, {"children-display": ("s", "submenu")}, children)


class Tray:
    def __init__(
        self,
        runtime_dir: str,
        plugin_dir: str,
        conn: Any = None,
        opener: Any = urllib.request.urlopen,
        portal: Callable[[str], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.runtime_dir, self.plugin_dir, self.opener, self.conn, self.clock = (
            runtime_dir,
            plugin_dir,
            opener,
            conn,
            clock,
        )
        self.portal = portal or open_with_portal
        self.link: str | None = None
        self.status = "Checking Keepsake's plugin..."
        self.revision = 1
        self.running = True
        self.send_lock = threading.Lock()  # sending only: the D-Bus thread alone reads the socket
        self.state_lock = threading.Lock()
        self.wanted = threading.Event()  # a check was asked for
        self.open_after = False  # open the window once the check is done
        self.last_signal = float("-inf")  # the first change goes out at once
        self.signal_due = False

    # The backend: only ever on the refresher thread

    def request_refresh(self, open_window: bool = False) -> None:
        """Ask for a check; never waits. Several asks before it runs count as one."""
        with self.state_lock:
            self.open_after = self.open_after or open_window
        self.wanted.set()

    def refresh(self) -> bool:
        """Check the plugin once (refresher thread). True when the status changed."""
        link, status = backend(self.runtime_dir, self.opener)
        with self.state_lock:
            changed = (link is None) != (self.link is None) or status != self.status
            self.link, self.status = link, status
            if changed:
                self.revision += 1
                self.signal_due = True
        self.flush_signals()
        return changed

    def flush_signals(self) -> None:
        """Send the change signals if due and the last ones went out long enough ago."""
        now = self.clock()
        with self.state_lock:
            if not self.signal_due or now - self.last_signal < SIGNAL_GAP:
                return
            self.signal_due, self.last_signal, revision = False, now, self.revision
        with self.send_lock:
            self.conn.signal(MENU_PATH, MENU_IFACE, "LayoutUpdated", "ui", [revision, 0])
            self.conn.signal(ITEM_PATH, ITEM_IFACE, "NewToolTip")

    def refresher(self) -> None:
        """Checks the plugin every 30 seconds, and when asked; opens the window when asked to."""
        while self.running:
            self.wanted.wait(CHECK_EVERY)
            self.wanted.clear()
            if not self.running:
                return
            with contextlib.suppress(Exception):  # the tray must outlive any surprise from the plugin
                self.refresh()
            with self.state_lock:
                open_now, self.open_after = self.open_after, False
                link = self.link
            if open_now and link:
                self.open_link(link)

    def open_link(self, link: str) -> bool:
        if self.portal(link):
            return True
        import webbrowser  # the desktop's own opener, as the PC launcher uses (ADR-0042)

        return bool(webbrowser.open(link))

    def open_window(self) -> bool:
        """For tests and the instance socket: check, then open (refresher-style, never on the D-Bus thread)."""
        self.refresh()
        return self.open_link(self.link) if self.link else False

    # D-Bus: answered at once, from cached state

    def item_properties(self) -> dict[str, tuple[str, Any]]:
        with self.state_lock:
            status = self.status
        tooltip: tuple[str, list[Any], str, str] = ("", [], "Keepsake", status)
        return {
            "Category": ("s", "ApplicationStatus"),
            "Id": ("s", "keepsake"),
            "Title": ("s", "Keepsake"),
            "Status": ("s", "Active"),
            "IconName": ("s", "keepsake-tray"),
            "IconThemePath": ("s", os.path.join(self.plugin_dir, "assets", "icons")),
            "ToolTip": ("(sa(iiay)ss)", tooltip),
            "ItemIsMenu": ("b", False),
            "Menu": ("o", MENU_PATH),
        }

    def menu_properties(self) -> dict[str, tuple[str, Any]]:
        return {
            "Version": ("u", 3),
            "TextDirection": ("s", "ltr"),
            "Status": ("s", "normal"),
            "IconThemePath": ("as", []),
        }

    def _layout(self) -> tuple[Any, ...]:
        with self.state_lock:
            return menu_layout(self.status, self.link is not None)

    def handle(self, call: dict[str, Any]) -> tuple[str, list[Any]] | None:
        """Answer one incoming method call, at once. Raises ``KeyError`` for an unknown method."""
        path, iface, member, body = call.get("path"), call.get("interface"), call.get("member"), call["body"]
        if iface == "org.freedesktop.DBus.Peer" and member == "Ping":
            return None
        if iface == PROPS_IFACE:
            table = self.item_properties() if path == ITEM_PATH else self.menu_properties() if path == MENU_PATH else {}
            if member == "GetAll":
                return ("a{sv}", [table])
            if member == "Get":
                return ("v", [table[body[1]]])
        if path == ITEM_PATH and iface == ITEM_IFACE:
            if member in ("Activate", "SecondaryActivate"):
                self.request_refresh(open_window=True)
                return None
            if member in ("ContextMenu", "Scroll"):
                return None
        if path == MENU_PATH and iface == MENU_IFACE:
            if member == "GetLayout":
                with self.state_lock:
                    revision = self.revision
                return ("u(ia{sv}av)", [revision, self._layout()])
            if member == "GetGroupProperties":
                found = [
                    (child[1][0], child[1][1]) for child in self._layout()[2] if child[1][0] in body[0] or not body[0]
                ]
                return ("a(ia{sv})", [found])
            if member == "Event":
                item_id, event = body[0], body[1]
                if event == "clicked" and item_id == MENU_OPEN:
                    self.request_refresh(open_window=True)
                elif event == "clicked" and item_id == MENU_QUIT:
                    self.running = False
                    self.wanted.set()
                return None
            if member == "EventGroup":
                for item_id, event, _data, _time in body[0]:
                    self.handle({**call, "member": "Event", "body": [item_id, event, None, 0]})
                return ("ai", [[]])
            if member == "AboutToShow":
                self.request_refresh()  # the menu shows the cached status now; a fresh one follows
                return ("b", [False])
            if member == "AboutToShowGroup":
                self.request_refresh()
                return ("aiai", [[], []])
        raise KeyError(f"{iface}.{member}")

    def register(self) -> None:
        name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.conn.call(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName", "su", [name, 4]
        )
        self.conn.call(*WATCHER, "RegisterStatusNotifierItem", "s", [name])

    def answer(self, found: dict[str, Any]) -> None:
        try:
            reply = self.handle(found)
            error = None
        except KeyError:
            reply, error = None, "org.freedesktop.DBus.Error.UnknownMethod"
        except (IndexError, TypeError):
            reply, error = None, "org.freedesktop.DBus.Error.InvalidArgs"
        with self.send_lock:
            self.conn.answer(found, reply, error)

    def serve_bus(self) -> None:
        """The only thread that reads the main D-Bus socket."""
        self.conn.sock.settimeout(1.0)
        while self.running:
            try:
                found = self.conn.pending.pop(0) if self.conn.pending else self.conn.receive()
            except TimeoutError:
                self.flush_signals()
                continue
            if found["type"] == dbus.CALL:
                self.answer(found)
            self.flush_signals()

    def serve_instance(self, server: socket.socket) -> None:
        while self.running:
            try:
                client, _ = server.accept()
            except OSError:
                return
            with client:
                command = client.recv(64).strip()
                if command == b"open":
                    client.sendall(b"ok\n")
                    self.request_refresh(open_window=True)
                elif command == b"quit":
                    client.sendall(b"ok\n")
                    self.running = False
                    self.wanted.set()
                elif command == b"ping":
                    client.sendall(b"ok\n")


def open_with_portal(link: str) -> bool:
    """The desktop portal's OpenURI, on a connection of its own: the main one stays with the D-Bus thread."""
    try:
        conn = dbus.Connection(timeout=2.0)
    except (dbus.DBusError, OSError):
        return False
    try:
        conn.call(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.OpenURI",
            "OpenURI",
            "ssa{sv}",
            ["", link, {}],
        )
        return True
    except (dbus.DBusError, OSError):
        return False
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="keepsake-tray")
    parser.add_argument("--runtime", required=True, help="the plugin's runtime folder (holds host.json)")
    parser.add_argument("--open", action="store_true", help="open Keepsake's window as well")
    options = parser.parse_args(argv)
    if hand_over("open" if options.open else "ping"):
        return 0  # one is running: it opened the window if asked
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined, unused-ignore]
    try:
        server.bind(instance_address())
        server.listen(4)
    except OSError:
        return 0  # another tray won the race
    plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    try:
        conn = dbus.Connection()
    except (dbus.DBusError, OSError) as exc:
        print(f"Keepsake's tray needs a desktop session: {exc}", file=sys.stderr)
        return 1
    tray = Tray(options.runtime, plugin_dir, conn)
    try:
        tray.register()
    except dbus.DBusError as exc:
        print(f"No system tray is available: {exc}", file=sys.stderr)
        return 1
    threading.Thread(target=tray.serve_instance, args=(server,), daemon=True).start()
    threading.Thread(target=tray.refresher, name="keepsake-tray-refresher", daemon=True).start()
    tray.request_refresh(open_window=options.open)
    tray.serve_bus()
    server.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
