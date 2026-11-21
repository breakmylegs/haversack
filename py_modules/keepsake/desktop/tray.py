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
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.request
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


def backend(runtime_dir: str, opener: Any = urllib.request.urlopen) -> tuple[str | None, str]:
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
        with opener(request, timeout=3) as response:
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
    def __init__(self, runtime_dir: str, plugin_dir: str, conn: Any = None, opener: Any = urllib.request.urlopen):
        self.runtime_dir, self.plugin_dir, self.opener = runtime_dir, plugin_dir, opener
        self.conn = conn
        self.link, self.status = backend(runtime_dir, opener)
        self.revision = 1
        self.running = True
        self.lock = threading.Lock()

    # The backend

    def refresh(self) -> bool:
        link, status = backend(self.runtime_dir, self.opener)
        changed = (link is None) != (self.link is None) or status != self.status
        self.link, self.status = link, status
        if changed:
            self.revision += 1
            with self.lock:
                self.conn.signal(MENU_PATH, MENU_IFACE, "LayoutUpdated", "ui", [self.revision, 0])
                self.conn.signal(ITEM_PATH, ITEM_IFACE, "NewToolTip")
        return changed

    def open_window(self) -> bool:
        self.refresh()
        if self.link is None:
            return False
        try:
            with self.lock:
                self.conn.call(
                    "org.freedesktop.portal.Desktop",
                    "/org/freedesktop/portal/desktop",
                    "org.freedesktop.portal.OpenURI",
                    "OpenURI",
                    "ssa{sv}",
                    ["", self.link, {}],
                )
            return True
        except (dbus.DBusError, OSError):
            import webbrowser  # the desktop's own opener, as the PC launcher uses (ADR-0042)

            return bool(webbrowser.open(self.link))

    # D-Bus

    def item_properties(self) -> dict[str, tuple[str, Any]]:
        tooltip: tuple[str, list[Any], str, str] = ("", [], "Keepsake", self.status)
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

    def handle(self, call: dict[str, Any]) -> tuple[str, list[Any]] | None:
        """Answer one incoming method call. Raises ``KeyError`` for an unknown method."""
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
                threading.Thread(target=self.open_window, daemon=True).start()
                return None
            if member in ("ContextMenu", "Scroll"):
                return None
        if path == MENU_PATH and iface == MENU_IFACE:
            if member == "GetLayout":
                return ("u(ia{sv}av)", [self.revision, menu_layout(self.status, self.link is not None)])
            if member == "GetGroupProperties":
                layout = menu_layout(self.status, self.link is not None)
                found = [(child[1][0], child[1][1]) for child in layout[2] if child[1][0] in body[0] or not body[0]]
                return ("a(ia{sv})", [found])
            if member == "Event":
                item_id, event = body[0], body[1]
                if event == "clicked" and item_id == MENU_OPEN:
                    threading.Thread(target=self.open_window, daemon=True).start()
                elif event == "clicked" and item_id == MENU_QUIT:
                    self.running = False
                return None
            if member == "EventGroup":
                for item_id, event, _data, _time in body[0]:
                    self.handle({**call, "member": "Event", "body": [item_id, event, None, 0]})
                return ("ai", [[]])
            if member == "AboutToShow":
                self.refresh()
                return ("b", [False])
            if member == "AboutToShowGroup":
                return ("aiai", [[], []])
        raise KeyError(f"{iface}.{member}")

    def register(self) -> None:
        name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.conn.call(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName", "su", [name, 4]
        )
        self.conn.call(*WATCHER, "RegisterStatusNotifierItem", "s", [name])

    def serve_bus(self) -> None:
        last = time.monotonic()
        self.conn.sock.settimeout(1.0)
        while self.running:
            try:
                found = self.conn.pending.pop(0) if self.conn.pending else self.conn.receive()
            except TimeoutError:
                found = None
            if found is not None and found["type"] == dbus.CALL:
                try:
                    reply = self.handle(found)
                    with self.lock:
                        self.conn.answer(found, reply)
                except KeyError:
                    with self.lock:
                        self.conn.answer(found, None, "org.freedesktop.DBus.Error.UnknownMethod")
                except (IndexError, TypeError):
                    with self.lock:
                        self.conn.answer(found, None, "org.freedesktop.DBus.Error.InvalidArgs")
            if time.monotonic() - last > CHECK_EVERY:
                last = time.monotonic()
                self.refresh()

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
                    threading.Thread(target=self.open_window, daemon=True).start()
                elif command == b"quit":
                    client.sendall(b"ok\n")
                    self.running = False


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
    if options.open:
        threading.Thread(target=tray.open_window, daemon=True).start()
    tray.serve_bus()
    server.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
