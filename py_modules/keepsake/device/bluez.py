"""BlueZ over the system bus for controller reconnect help, without root (R22, ADR-0082).

Steam is a BlueZ client as the signed-in user, so the same user may list devices, run discovery
and connect profiles. Every action passes one gate, the user's rule for exactly that adapter and
device (``reconnect.Rules.enabled``); devices without one are only ever read.

- The device list: every paired device on every adapter, for the user to choose from.
- The reconnect assist (Design E): discovery for at most 30 s after a user action, stopped the
  moment the device appears, then ``ConnectProfile(HID)`` on its existing bond. Discovery is
  stopped on every path, and BlueZ also ends a client's discovery when its connection closes.
- The watcher: for helped devices with Pair and commit on (Design B), connect HID the moment the
  device becomes Paired, once, unless it is already connected; for every device, note failure
  signs (connected then dropped within 5 s) so the screen can suggest a diagnosis. It never acts
  on a suggestion.
- The reconnect watch for the diagnosis: what BlueZ reports while the user presses the button.

No agent is registered, no setting is changed and nothing is written. Keepsake's own pure-Python
D-Bus client does the talking, so no binary and no library is needed (P9).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from ..desktop import dbus
from ..log import log_event
from .reconnect import masked, normal_mac, unregistered_prefix

BLUEZ = "org.bluez"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
PROPS = "org.freedesktop.DBus.Properties"
HID_UUID = "00001124-0000-1000-8000-00805f9b34fb"
SYSTEM_BUS = "unix:path=/run/dbus/system_bus_socket"
ASSIST_WINDOW = 30.0
CONNECT_TIMEOUT = 15.0
WATCH_WINDOW = 45.0
STEADY = 20.0
QUICK_DROP = 5.0
NOT_PAIRED = "Pair the controller from Steam's Bluetooth settings first."
NOT_SEEN = "The controller was not seen. Put it in pairing mode (its light flashes quickly), then try again."
NOT_HELPED = "Help is not on for that device."

Gate = Callable[[str, str], "dict[str, Any] | None"]


class BlueZError(Exception):
    pass


def system_connect() -> Any:
    return dbus.Connection(os.environ.get("DBUS_SYSTEM_BUS_ADDRESS") or SYSTEM_BUS, timeout=5.0)


def _plain(value: Any) -> Any:
    return value[1] if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str) else value


def path_mac(path: str) -> str | None:
    """``/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF`` to its address."""
    tail = path.rsplit("/", 1)[-1]
    return normal_mac(tail[4:].replace("_", ":")) if tail.startswith("dev_") else None


def managed(conn: Any) -> dict[str, dict[str, dict[str, Any]]]:
    (objects,) = conn.call(BLUEZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for path, ifaces in dict(objects).items():
        out[str(path)] = {str(i): {str(k): _plain(v) for k, v in dict(p).items()} for i, p in dict(ifaces).items()}
    return out


def adapters(objects: dict[str, dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Adapter object path to ``{address, name, powered}``."""
    out = {}
    for path, ifaces in objects.items():
        props = ifaces.get(ADAPTER)
        address = normal_mac(props.get("Address")) if props else None
        if props is not None and address:
            out[path] = {
                "address": address,
                "name": path.rsplit("/", 1)[-1],
                "alias": str(props.get("Alias") or "")[:40],
                "powered": bool(props.get("Powered")),
            }
    return out


def find(objects: dict[str, dict[str, dict[str, Any]]], adapter: str, mac: str) -> tuple[str, dict[str, Any]] | None:
    """The device object for exactly this adapter address and device address."""
    by_path = adapters(objects)
    for path, ifaces in objects.items():
        props = ifaces.get(DEVICE)
        if props is None or normal_mac(props.get("Address")) != mac:
            continue
        if by_path.get(str(props.get("Adapter") or ""), {}).get("address") == adapter:
            return path, props
    return None


def transport(props: dict[str, Any]) -> str:
    """ "bredr" when BlueZ knows a Classic device class, "le" for an LE-only device, else "unknown"."""
    if props.get("Class"):
        return "bredr"
    if props.get("AddressType") == "random" or props.get("Appearance"):
        return "le"
    return "unknown"


def describe(path: str, props: dict[str, Any], adapter: dict[str, Any]) -> dict[str, Any]:
    mac = normal_mac(props.get("Address")) or ""
    return {
        "adapter": adapter.get("address"),
        "adapterName": adapter.get("name"),
        "mac": mac,
        "name": str(props.get("Alias") or props.get("Name") or "Bluetooth device")[:60],
        "class": f"0x{int(props.get('Class') or 0):06X}" if props.get("Class") else None,
        "modalias": str(props.get("Modalias") or "")[:60] or None,
        "icon": str(props.get("Icon") or "") or None,
        "transport": transport(props),
        "paired": bool(props.get("Paired") or props.get("Bonded")),
        "connected": bool(props.get("Connected")),
        "services": len(props.get("UUIDs") or []),
        "unregisteredPrefix": unregistered_prefix(mac),
    }


def devices(conn: Any) -> dict[str, Any]:
    """The adapters and every paired device, for the user to choose from. Names stay on the device."""
    objects = managed(conn)
    by_path = adapters(objects)
    found = []
    for path, ifaces in sorted(objects.items()):
        props = ifaces.get(DEVICE)
        adapter = by_path.get(str((props or {}).get("Adapter") or ""))
        if props is None or adapter is None or not normal_mac(props.get("Address")):
            continue
        if props.get("Paired") or props.get("Bonded"):
            found.append(describe(path, props, adapter))
    return {"adapters": list(by_path.values()), "devices": found}


def bond(objects: dict[str, dict[str, dict[str, Any]]], adapter: str, mac: str) -> dict[str, Any] | None:
    found = find(objects, adapter, mac)
    if found is None:
        return None
    props = found[1]
    state = {k: props.get(k) for k in ("Paired", "Bonded", "Trusted", "Connected", "LegacyPairing")}
    state["UUIDs"] = len(props.get("UUIDs") or [])
    return state


def _match(conn: Any, path: str | None = None) -> None:
    rule = f"type='signal',sender='{BLUEZ}',interface='{PROPS}',member='PropertiesChanged'"
    rule += f",path='{path}'" if path else ",path_namespace='/org/bluez'"
    conn.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s", [rule])


def _next(conn: Any, deadline: float, clock: Callable[[], float]) -> dict[str, Any] | None:
    """The next queued or incoming message before ``deadline``, else None."""
    if conn.pending:
        queued: dict[str, Any] = conn.pending.pop(0)
        return queued
    remaining = deadline - clock()
    if remaining <= 0:
        return None
    conn.sock.settimeout(min(remaining, 1.0))
    try:
        received: dict[str, Any] = conn.receive()
        return received
    except TimeoutError:
        return None


def _changes(found: dict[str, Any], path: str | None = None) -> tuple[str, dict[str, Any]] | None:
    """A Device1 PropertiesChanged signal as ``(path, changed)``, optionally for one path only."""
    if found.get("type") != dbus.SIGNAL or found.get("member") != "PropertiesChanged":
        return None
    body = found.get("body") or []
    if len(body) < 2 or body[0] != DEVICE or (path and found.get("path") != path):
        return None
    return str(found.get("path")), {str(k): _plain(v) for k, v in dict(body[1]).items()}


def _with(connect: Callable[[], Any], work: Callable[[Any], Any]) -> Any:
    try:
        conn = connect()
    except (dbus.DBusError, OSError) as exc:
        raise BlueZError(f"Bluetooth could not be reached ({type(exc).__name__})") from exc
    try:
        return work(conn)
    except dbus.DBusError as exc:
        raise BlueZError(str(exc)[:200]) from exc
    finally:
        conn.close()


def list_devices(connect: Callable[[], Any] = system_connect) -> dict[str, Any]:
    return dict(_with(connect, devices))


def read_bond(adapter: str, mac: str, connect: Callable[[], Any] = system_connect) -> dict[str, Any] | None:
    return _with(connect, lambda conn: bond(managed(conn), adapter, mac))  # type: ignore[no-any-return]


def _connect_hid(conn: Any, path: str) -> None:
    conn.sock.settimeout(CONNECT_TIMEOUT)
    try:
        conn.call(BLUEZ, path, DEVICE, "ConnectProfile", "s", [HID_UUID])
    except dbus.DBusError as exc:
        if "AlreadyConnected" not in str(exc):
            raise


def _gated(gate: Gate, adapter: Any, mac: Any) -> tuple[str, str]:
    a, m = normal_mac(adapter), normal_mac(mac)
    if a is None or m is None or gate(a, m) is None:
        raise BlueZError(NOT_HELPED)
    return a, m


def assist(
    adapter: Any,
    mac: Any,
    gate: Gate,
    connect: Callable[[], Any] = system_connect,
    clock: Callable[[], float] = time.monotonic,
    window: float = ASSIST_WINDOW,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Reconnect a helped device the user has put in pairing mode (Design E)."""
    a, m = _gated(gate, adapter, mac)

    def work(conn: Any) -> dict[str, Any]:
        objects = managed(conn)
        found = find(objects, a, m)
        if found is None or not (found[1].get("Paired") or found[1].get("Bonded")):
            return {"ok": False, "state": "not-paired", "message": NOT_PAIRED}
        path, props = found
        if props.get("Connected"):
            return {"ok": True, "state": "already", "message": "The controller is already connected."}
        if dry_run:
            return {"ok": True, "state": "dry-run", "message": "Dry run: discovery and the connection were skipped."}
        adapter_path = str(props.get("Adapter") or "")
        _match(conn, path)
        try:
            conn.call(BLUEZ, adapter_path, ADAPTER, "SetDiscoveryFilter", "a{sv}", [{"Transport": ("s", "bredr")}])
        except dbus.DBusError:
            pass  # an older BlueZ: plain discovery is fine
        conn.call(BLUEZ, adapter_path, ADAPTER, "StartDiscovery")
        seen = connected = False
        try:
            deadline = clock() + min(window, ASSIST_WINDOW)
            while not seen:
                message = _next(conn, deadline, clock)
                if message is None and clock() >= deadline:
                    break
                change = _changes(message or {}, path)
                if change:
                    connected = bool(change[1].get("Connected"))
                    seen = connected or "RSSI" in change[1]
        finally:
            try:
                conn.call(BLUEZ, adapter_path, ADAPTER, "StopDiscovery")
            except dbus.DBusError:
                pass  # already stopped
        if not seen:
            return {"ok": False, "state": "not-seen", "message": NOT_SEEN}
        if not connected:
            _connect_hid(conn, path)
        log_event(logging.INFO, "reconnect.assist", "Controller reconnected", device=masked(m))
        return {"ok": True, "state": "connected", "message": "The controller is connected."}

    return dict(_with(connect, work))


def watch_reconnect(
    adapter: Any,
    mac: Any,
    gate: Gate,
    connect: Callable[[], Any] = system_connect,
    clock: Callable[[], float] = time.monotonic,
    window: float = WATCH_WINDOW,
) -> dict[str, Any]:
    """What BlueZ reports while the user presses a helped device's button (for the diagnosis)."""
    a, m = _gated(gate, adapter, mac)

    def work(conn: Any) -> dict[str, Any]:
        objects = managed(conn)
        found = find(objects, a, m)
        if found is None:
            return {"bond": None, "events": []}
        path, _props = found
        state = bond(objects, a, m)
        _match(conn, path)
        start = clock()
        deadline = start + window
        events: list[tuple[float, str, bool]] = []
        up_since: float | None = None
        while not (up_since is not None and clock() - up_since >= STEADY):
            message = _next(conn, deadline, clock)
            if message is None and clock() >= deadline:
                break
            change = _changes(message or {}, path)
            if not change:
                continue
            at = round(clock() - start, 2)
            for name in ("Connected", "ServicesResolved"):
                if name in change[1]:
                    events.append((at, name, bool(change[1][name])))
            if change[1].get("Connected") is True:
                up_since = clock()
            elif change[1].get("Connected") is False and up_since is not None:
                break  # one attempt is enough to classify
        return {"bond": state, "events": events}

    return dict(_with(connect, work))


class Watcher:
    """Pair and commit for helped devices, and failure signs for every device.

    A thread with its own system bus connection. If the bus goes (a bluetoothd restart), it waits
    and reconnects to the bus: that is the bus, never a device, so it is not a connect loop.
    """

    def __init__(
        self,
        gate: Gate,
        on_failure: Callable[[str, str, str], None] | None = None,
        on_connected: Callable[[str, str, dict[str, Any]], None] | None = None,
        dry_run: Callable[[], bool] = lambda: False,
        connect: Callable[[], Any] = system_connect,
        clock: Callable[[], float] = time.monotonic,
        retry: float = 30.0,
    ) -> None:
        self.gate = gate
        self.on_failure = on_failure
        self.on_connected = on_connected
        self.dry_run = dry_run
        self.connect = connect
        self.clock = clock
        self.retry = retry
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.adapters: dict[str, str] = {}  # adapter object path to its address
        self.up: dict[str, float] = {}  # device path to when it connected
        self.commits = 0

    def start(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, name="keepsake-reconnect-watcher", daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3.0)
        self.thread = None

    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                conn = self.connect()
            except (dbus.DBusError, OSError):
                self.stop_event.wait(self.retry)
                continue
            try:
                self.refresh(conn)
                _match(conn)
                while not self.stop_event.is_set():
                    message = _next(conn, time.monotonic() + 1.0, time.monotonic)
                    if message is not None:
                        self.handle(conn, message)
            except (dbus.DBusError, OSError):
                pass
            finally:
                conn.close()
            self.stop_event.wait(self.retry)

    def refresh(self, conn: Any) -> None:
        self.adapters = {path: a["address"] for path, a in adapters(managed(conn)).items()}

    def handle(self, conn: Any, message: dict[str, Any]) -> str | None:
        """One signal. Returns what was done: "commit", "dry-run", "suggest", "connected" or None."""
        change = _changes(message)
        if change is None:
            return None
        path, changed = change
        mac = path_mac(path)
        adapter_path = path.rsplit("/", 1)[0]
        if adapter_path not in self.adapters:
            self.refresh(conn)
        adapter = self.adapters.get(adapter_path)
        if mac is None or adapter is None:
            return None
        rule = self.gate(adapter, mac)
        if changed.get("Paired") is True and rule is not None and rule.get("commit", True):
            return self._commit(conn, path, adapter, mac, changed)
        if changed.get("Connected") is True:
            self.up[path] = self.clock()
            if rule is not None and self.on_connected is not None:
                self.on_connected(adapter, mac, rule)
                return "connected"
            return None
        if changed.get("Connected") is False:
            since = self.up.pop(path, None)
            if since is not None and self.clock() - since <= QUICK_DROP and self.on_failure is not None:
                # Read only: the screen suggests a diagnosis. Nothing is done to the device.
                self.on_failure(adapter, mac, "connected, then dropped within 5 seconds")
                return "suggest"
        return None

    def _commit(self, conn: Any, path: str, adapter: str, mac: str, changed: dict[str, Any]) -> str | None:
        connected = changed.get("Connected")
        if connected is None:
            connected = _plain(conn.call(BLUEZ, path, PROPS, "Get", "ss", [DEVICE, "Connected"])[0])
        if connected:
            return None  # Steam or the device already opened it: a second connect would collide (F5)
        if self.dry_run():
            log_event(logging.INFO, "reconnect.commit", "Dry run: pair and commit skipped", device=masked(mac))
            return "dry-run"
        try:
            _connect_hid(conn, path)
        except dbus.DBusError as exc:
            log_event(
                logging.WARNING, "reconnect.commit", "Pair and commit failed", device=masked(mac), error=str(exc)[:120]
            )
            return None
        self.commits += 1
        log_event(logging.INFO, "reconnect.commit", "Pair and commit: HID connected after pairing", device=masked(mac))
        return "commit"
