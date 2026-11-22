"""The SSP gate (Design A, ADR-0083): Secure Simple Pairing on only while pairing.

Some clone controllers open HID before encryption is up, and BlueZ refuses them (fault F2,
outcome O3). With SSP off they reconnect. SSP is adapter-wide security, so the gate is opt-in
behind a two-step warning, and SSP is on whenever it might be needed:

- on while the adapter is Discovering (Steam's pairing screen, Keepsake's Reconnect) or a
  pairing is armed, off otherwise, after a short debounce;
- re-applied when bluetoothd restarts (it turns SSP back on at every start) and when the adapter
  powers on;
- off is held by a lease the helper enforces: if Keepsake stops renewing it, the helper puts
  SSP back on by itself; switching the gate off, unloading and errors also put it back on.

If the kernel refuses SSP off while the adapter is powered, the gate cycles the adapter's power
only when no device is connected; otherwise it waits for the user to confirm.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from ..desktop import dbus
from ..log import log_event
from . import bluez
from .helper import HelperClient, HelperError

LEASE = 120.0
RENEW = 30.0
DEBOUNCE = 1.5


class SspGate:
    def __init__(
        self,
        helper: HelperClient,
        adapter_path: str,
        connect: Callable[[], Any] = bluez.system_connect,
        clock: Callable[[], float] = time.monotonic,
        retry: float = 10.0,
    ) -> None:
        self.helper = helper
        self.adapter_path = adapter_path
        self.index = int(adapter_path.rsplit("hci", 1)[-1])
        self.connect = connect
        self.clock = clock
        self.retry = retry
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.armed_until = 0.0
        self.discovering = False
        self.state = "starting"  # "on", "off", "needs-confirm", "error: ..."
        self.last_renew = 0.0
        self.pending_at: float | None = None

    # Decisions (pure, tested)

    def wanted(self) -> bool:
        """True when SSP should be on: discovering, or a pairing is armed."""
        return self.discovering or self.clock() < self.armed_until

    def arm(self, seconds: float = 60.0) -> None:
        self.armed_until = self.clock() + seconds
        self.pending_at = self.clock()

    def apply(self, connected_devices: int, confirmed: bool = False) -> str:
        """Set SSP to what is wanted now, through the helper."""
        on = self.wanted()
        try:
            if on:
                self.helper.ssp_set(self.index, True)
                self.state = "on"
            else:
                result = self.helper.ssp_set(self.index, False, lease=LEASE)
                if not result.get("ok") and result.get("needsPowerCycle"):
                    if connected_devices == 0 or confirmed:
                        result = self.helper.ssp_set(self.index, False, lease=LEASE, power_cycle=True)
                    else:
                        self.state = "needs-confirm"
                        return self.state
                self.state = "off" if result.get("ok") else f"error: {result.get('problem') or 'not applied'}"
                self.last_renew = self.clock()
        except HelperError as exc:
            self.state = f"error: {exc}"
        log_event(logging.INFO, "reconnect.ssp", "SSP gate applied", state=self.state.split(":")[0])
        return self.state

    def renew_due(self) -> bool:
        return self.state == "off" and self.clock() - self.last_renew >= RENEW

    def renew(self) -> None:
        try:
            self.helper.ssp_renew(LEASE)
            self.last_renew = self.clock()
        except HelperError as exc:
            self.state = f"error: {exc}"

    def handle(self, message: dict[str, Any]) -> bool:
        """One signal; returns whether SSP must be re-applied (after the debounce)."""
        if message.get("type") != dbus.SIGNAL:
            return False
        member, body = message.get("member"), message.get("body") or []
        if member == "NameOwnerChanged" and body and body[0] == bluez.BLUEZ and len(body) >= 3 and body[2]:
            self.discovering = False  # a new bluetoothd: it has turned SSP back on
            return True
        if (
            member == "PropertiesChanged"
            and message.get("path") == self.adapter_path
            and body
            and body[0] == bluez.ADAPTER
        ):
            changed = {str(k): bluez._plain(v) for k, v in dict(body[1]).items()}
            if "Discovering" in changed:
                self.discovering = bool(changed["Discovering"])
                return True
            if changed.get("Powered") is True:
                return True
        return False

    # The thread

    def start(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, name="keepsake-ssp-gate", daemon=True)
            self.thread.start()

    def stop(self) -> None:
        """Stop and put SSP back on (the helper's lease would, too, a little later)."""
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3.0)
        self.thread = None
        try:
            self.helper.ssp_release()
            self.state = "on"
        except HelperError as exc:
            self.state = f"error: {exc}"

    def _connected(self, conn: Any) -> int:
        objects = bluez.managed(conn)
        return sum(1 for ifaces in objects.values() if ifaces.get(bluez.DEVICE, {}).get("Connected"))

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                conn = self.connect()
            except (dbus.DBusError, OSError):
                self.stop_event.wait(self.retry)
                continue
            try:
                rules = [
                    f"type='signal',sender='{bluez.BLUEZ}',interface='{bluez.PROPS}',member='PropertiesChanged',"
                    f"path='{self.adapter_path}'",
                    f"type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged',arg0='{bluez.BLUEZ}'",
                ]
                for rule in rules:
                    conn.call(
                        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s", [rule]
                    )
                props = bluez.managed(conn).get(self.adapter_path, {}).get(bluez.ADAPTER, {})
                self.discovering = bool(props.get("Discovering"))
                self.apply(self._connected(conn))  # reconcile at start
                while not self.stop_event.is_set():
                    message = bluez._next(conn, time.monotonic() + 1.0, time.monotonic)
                    if message is not None and self.handle(message):
                        self.pending_at = self.clock()
                    if self.pending_at is not None and self.clock() - self.pending_at >= DEBOUNCE:
                        self.pending_at = None
                        self.apply(self._connected(conn))
                    elif self.armed_until and self.clock() >= self.armed_until and self.state == "on":
                        self.armed_until = 0.0
                        self.pending_at = self.clock()
                    if self.renew_due():
                        self.renew()
            except (dbus.DBusError, OSError):
                pass
            finally:
                conn.close()
            self.stop_event.wait(self.retry)
