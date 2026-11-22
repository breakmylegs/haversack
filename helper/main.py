"""Keepsake Helper: Decky's entry point. All logic is in ``py_modules/keepsake_helper`` (ADR-0083).

A separate plugin with the root flag, so that Keepsake itself never runs as root (P8). It serves
Keepsake alone, over an authenticated Unix socket, and only the jobs listed in ``server.JOBS``.
"""

from __future__ import annotations

import asyncio
import os
import pwd
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_modules"))

import decky

from keepsake_helper import bluetooth, dbus, server


def _version() -> str:
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return "dev"


class Plugin:
    helper: server.Helper | None = None
    listener = None
    stopping = threading.Event()

    async def _main(self) -> None:
        uid = pwd.getpwnam(decky.DECKY_USER).pw_uid
        systemd = bluetooth.Systemd(lambda: dbus.Connection("unix:path=/run/dbus/system_bus_socket", timeout=5.0))
        state = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "state.json")
        self.helper = server.Helper(_version(), uid, state, systemd)
        self.helper.restore_ssp("helper started")  # reconcile: nothing is left off from before
        self.listener = server.publish(self.helper)
        threading.Thread(target=self._serve, name="keepsake-helper", daemon=True).start()
        decky.logger.info("Keepsake Helper %s ready", self.helper.version)
        while not self.stopping.is_set():
            await asyncio.sleep(5)
            await asyncio.to_thread(self.helper.tick)

    def _serve(self) -> None:
        helper, listener = self.helper, self.listener
        if helper is None or listener is None:
            return
        while not self.stopping.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            threading.Thread(
                target=server.serve_one,
                args=(helper, conn, lambda c: server.peer_allowed(c, helper.uid)),
                daemon=True,
            ).start()

    async def _unload(self) -> None:
        self.stopping.set()
        if self.listener is not None:
            self.listener.close()
        if self.helper is not None:
            await asyncio.to_thread(self.helper.restore_ssp, "helper unloaded")

    async def _uninstall(self) -> None:
        if self.helper is not None:
            await asyncio.to_thread(self.helper.restore_ssp, "helper uninstalled")
