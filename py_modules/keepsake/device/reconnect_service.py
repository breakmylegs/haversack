"""Controller reconnect help as one service for the app (R22, ADR-0082).

Holds the user's rules, the watcher thread and the last capture per device, and turns them into
the calls the screens use. Every blocking step (D-Bus, sysfs, hidraw, journalctl) runs in a worker
thread, so the event loop never waits on Bluetooth. Every action on a device goes through the
rule for exactly that adapter and device.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import zipfile
from collections.abc import Callable
from typing import Any

from . import bluez, cable
from .reconnect import Rules, classify, journal_signs, masked, normal_mac, read_journal, redact, rule_key

FULL_REPORT_TRIES = 6


class ReconnectService:
    def __init__(
        self,
        settings_dir: str,
        sys_root: str = "/sys",
        dev_root: str = "/dev",
        connect: Callable[[], Any] = bluez.system_connect,
        journal: Callable[[float], list[str]] = read_journal,
        get: cable.Get = cable.get_feature,
        notify: Callable[[], None] = lambda: None,
    ) -> None:
        self.rules = Rules(os.path.join(settings_dir, "reconnect-help.json"))
        self.export_dir = settings_dir
        self.sys_root = sys_root
        self.dev_root = dev_root
        self.connect = connect
        self.journal = journal
        self.get = get
        self.notify = notify
        self.captures: dict[str, dict[str, Any]] = {}
        self.watcher = bluez.Watcher(
            self.rules.enabled,
            on_failure=self._failure,
            on_connected=self._connected,
            dry_run=self.rules.dry_run,
            connect=connect,
        )

    # Lifecycle

    def start(self) -> None:
        self.watcher.start()

    def stop(self) -> None:
        self.watcher.stop()

    # Watcher callbacks (on the watcher's thread)

    def _failure(self, adapter: str, mac: str, reason: str) -> None:
        if self.rules.suggest(adapter, mac, reason):
            self.notify()

    def _connected(self, adapter: str, mac: str, rule: dict[str, Any]) -> None:
        if not rule.get("fullMode"):
            return

        def ask() -> None:
            # The hidraw node appears a moment after HID connects: sysfs is looked at, never the radio.
            for _ in range(FULL_REPORT_TRIES):
                if cable.full_report(mac, True, cable.hid_nodes(self.sys_root, self.dev_root), self.get):
                    self.rules.action("full-report", adapter, mac)
                    return
                time.sleep(0.5)

        threading.Thread(target=ask, name="keepsake-full-report", daemon=True).start()

    # Calls

    def _status(self) -> dict[str, Any]:
        state = self.rules.state()
        try:
            found = bluez.list_devices(self.connect)
            problem = None
        except bluez.BlueZError as exc:
            found, problem = {"adapters": [], "devices": []}, str(exc)
        usb = [n for n in cable.hid_nodes(self.sys_root, self.dev_root) if n.bus == "usb"]
        cable_ready = any(cable.provider_for(n) for n in usb)
        out = []
        for device in found["devices"]:
            key = rule_key(device["adapter"], device["mac"])
            rule = state["rules"].get(key)
            out.append(
                {
                    **device,
                    "help": rule is not None,
                    "commit": bool(rule and rule.get("commit", True)),
                    "fullMode": bool(rule and rule.get("fullMode")),
                    "last": state["last"].get(key),
                    "suggest": state["suggest"].get(key),
                    "captured": key in self.captures,
                }
            )
        return {
            "available": problem is None,
            "problem": problem,
            "adapters": found["adapters"],
            "devices": out,
            "dryRun": state["dryRun"],
            "watcher": self.watcher.running(),
            "cableReady": cable_ready,
            "actions": self.rules.actions(20),
        }

    async def status(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._status)

    async def set_help(self, adapter: Any, mac: Any, on: bool, label: str = "") -> dict[str, Any]:
        if on:
            await asyncio.to_thread(self.rules.enable, adapter, mac, label)
        else:
            await asyncio.to_thread(self.rules.disable, adapter, mac)
        return await self.status()

    async def set_option(self, adapter: Any, mac: Any, option: str, on: bool) -> dict[str, Any]:
        await asyncio.to_thread(self.rules.set_option, adapter, mac, option, on)
        return await self.status()

    async def set_dry_run(self, on: bool) -> dict[str, Any]:
        await asyncio.to_thread(self.rules.set_dry_run, on)
        return await self.status()

    async def dismiss(self, adapter: Any, mac: Any) -> dict[str, Any]:
        await asyncio.to_thread(self.rules.dismiss, adapter, mac)
        return await self.status()

    async def assist(self, adapter: Any, mac: Any) -> dict[str, Any]:
        dry = self.rules.dry_run()
        result = await asyncio.to_thread(bluez.assist, adapter, mac, self.rules.enabled, self.connect, dry_run=dry)
        self.rules.action("assist", normal_mac(adapter), normal_mac(mac), state=result.get("state"), dryRun=dry)
        return result

    def _gate(self, adapter: Any, mac: Any) -> tuple[str, str]:
        a, m = normal_mac(adapter), normal_mac(mac)
        if a is None or m is None or self.rules.enabled(a, m) is None:
            raise ValueError(bluez.NOT_HELPED)
        return a, m

    async def read_usb(self, adapter: Any, mac: Any) -> dict[str, Any]:
        """ "Read stored host over USB": compare the controller's stored host with this adapter."""
        a, m = self._gate(adapter, mac)
        nodes = await asyncio.to_thread(cable.hid_nodes, self.sys_root, self.dev_root)
        read = await asyncio.to_thread(cable.read_stored_host, m, nodes, self.get)
        self.rules.action("read-usb", a, m, state=read["state"])
        if not read["ok"]:
            return {"read": read, "diagnosis": None}
        bond = await asyncio.to_thread(bluez.read_bond, a, m, self.connect)
        diagnosis = classify(bond, [], identity=read, adapter=a, watched=False)
        diagnosis["storesThisHandheld"] = read.get("host") == a
        await asyncio.to_thread(self.rules.record, a, m, diagnosis)
        key = rule_key(a, m)
        self.captures[key] = {**self.captures.get(key, {}), "usb": {"family": read["family"], "host": read["host"]}}
        # Only whether it matches leaves this call: the screen needs no addresses.
        return {
            "read": {"ok": True, "family": read["family"], "storesThisHandheld": read["host"] == a},
            "diagnosis": diagnosis,
        }

    async def diagnose(self, adapter: Any, mac: Any) -> dict[str, Any]:
        """The time-boxed watch while the user presses the button, the journal, then the outcome."""
        a, m = self._gate(adapter, mac)
        since = time.time() - 2
        watched = await asyncio.to_thread(bluez.watch_reconnect, a, m, self.rules.enabled, self.connect)
        try:
            lines = await asyncio.to_thread(self.journal, since)
            journal_problem = None
        except Exception as exc:  # noqa: BLE001 - the journal is evidence, not a requirement
            lines, journal_problem = [], str(exc)[:120]
        signs = journal_signs(lines, m)
        diagnosis = classify(watched["bond"], watched["events"], signs)
        diagnosis["journal"] = "unavailable" if journal_problem else "read"
        await asyncio.to_thread(self.rules.record, a, m, diagnosis)
        key = rule_key(a, m)
        self.captures[key] = {
            **self.captures.get(key, {}),
            "bond": watched["bond"],
            "events": watched["events"],
            "journal": lines,
            "journalProblem": journal_problem,
            "diagnosis": diagnosis,
        }
        self.rules.action("diagnose", a, m, outcome=diagnosis["outcome"])
        return diagnosis

    async def export(self, adapter: Any, mac: Any, redact_adapter: bool = True) -> dict[str, Any]:
        """ "Export report bundle": the last capture and the device's details in one zip, to share.

        Separate from the Device checks export. The device's own address stays (it is what the
        report is about); this handheld's adapter address is replaced on request.
        """
        a, m = self._gate(adapter, mac)
        key = rule_key(a, m)
        capture = self.captures.get(key)
        if not capture:
            raise ValueError("run the diagnosis first")
        status = await self.status()
        device: dict[str, Any] = next((d for d in status["devices"] if d["adapter"] == a and d["mac"] == m), {})
        meta = {k: device.get(k) for k in ("name", "class", "modalias", "transport", "services", "unregisteredPrefix")}
        report = {
            "kind": "keepsake-reconnect-report",
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "device": {"address": m, **meta},
            "adapter": "HOST-ADAPTER" if redact_adapter else a,
            "bond": capture.get("bond"),
            "events": capture.get("events", []),
            "usb": capture.get("usb"),
            "diagnosis": capture.get("diagnosis"),
            "journalProblem": capture.get("journalProblem"),
            "hciCapture": "needs the root helper (next release)",
        }
        lines = redact(capture.get("journal", []), a if redact_adapter else None)
        if redact_adapter and isinstance(report["usb"], dict) and report["usb"].get("host") == a:
            report["usb"] = {**report["usb"], "host": "HOST-ADAPTER"}
        name = f"reconnect-report-{m.replace(':', '')[-4:]}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
        path = os.path.join(self.export_dir, name)

        def write() -> None:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("report.json", json.dumps(report, indent=1))
                bundle.writestr("journal.txt", "\n".join(lines) + ("\n" if lines else ""))

        await asyncio.to_thread(write)
        self.rules.action("export", a, m, redacted=bool(redact_adapter))
        return {"file": name, "path": path}

    async def probe(self) -> dict[str, Any]:
        """For the Device check: counts and outcome codes only, addresses masked."""
        status = await self.status()
        helped = [d for d in status["devices"] if d["help"]]
        try:
            await asyncio.to_thread(self.journal, time.time() - 60)
            journal = "read"
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            journal = str(exc)[:80]
        return {
            "available": status["available"],
            "problem": status["problem"],
            "adapters": len(status["adapters"]),
            "paired": len(status["devices"]),
            "classic": sum(1 for d in status["devices"] if d["transport"] == "bredr"),
            "helped": [
                {
                    "device": masked(d["mac"]),
                    "connected": d["connected"],
                    "commit": d["commit"],
                    "outcome": (d["last"] or {}).get("outcome"),
                }
                for d in helped
            ],
            "suggested": sum(1 for d in status["devices"] if d["suggest"]),
            "watcher": status["watcher"],
            "dryRun": status["dryRun"],
            "cableReady": status["cableReady"],
            "journal": journal,
        }
