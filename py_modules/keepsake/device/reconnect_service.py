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
import secrets
import threading
import time
import zipfile
from collections.abc import Callable
from typing import Any

from . import bluez, cable, hcilog
from .helper import HelperClient, HelperError
from .reconnect import Rules, classify, journal_signs, masked, normal_mac, read_journal, redact, rule_key
from .sspgate import SspGate

FULL_REPORT_TRIES = 6
CAPTURE_SECONDS = 40.0
CONFIRM = "I understand"


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
        version: str = "dev",
        helper: HelperClient | None = None,
        busy: Callable[[], str | None] = lambda: None,
    ) -> None:
        self.rules = Rules(os.path.join(settings_dir, "reconnect-help.json"))
        self.helper = helper or HelperClient(version)
        self.busy = busy
        self.gate: SspGate | None = None
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
        gate = self.rules.ssp_gate()
        if gate:
            self._start_gate(str(gate["path"]))

    def stop(self) -> None:
        self.watcher.stop()
        self._stop_gate()

    def _start_gate(self, path: str) -> None:
        self._stop_gate()
        self.gate = SspGate(self.helper, path, self.connect)
        self.gate.start()

    def _stop_gate(self) -> None:
        gate, self.gate = self.gate, None
        if gate is not None:
            gate.stop()  # SSP back on

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
        helper = self.helper.status()
        if helper.get("ready"):
            for device in out:
                if device["help"]:
                    try:
                        device["stored"] = self.helper.bt_state(device["adapter"], device["mac"])
                    except HelperError:
                        device["stored"] = None
        gate = self.rules.ssp_gate()
        return {
            "available": problem is None,
            "problem": problem,
            "helper": helper,
            "sspGate": {
                "on": bool(gate),
                "adapter": (gate or {}).get("adapter"),
                "state": self.gate.state if self.gate else "on",
            },
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
        if read["state"] == "permission" and self.helper.installed():
            read = await asyncio.to_thread(cable.read_stored_host, m, nodes, self.helper.get_feature)
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
        capture_task = None
        if self.helper.status().get("ready"):
            capture_task = asyncio.create_task(asyncio.to_thread(self.helper.capture, CAPTURE_SECONDS))
        watched = await asyncio.to_thread(bluez.watch_reconnect, a, m, self.rules.enabled, self.connect)
        btsnoop: bytes | None = None
        capture_problem = None
        if capture_task is not None:
            try:
                btsnoop = await capture_task
            except HelperError as exc:
                capture_problem = str(exc)[:120]
        try:
            lines = await asyncio.to_thread(self.journal, since)
            journal_problem = None
        except Exception as exc:  # noqa: BLE001 - the journal is evidence, not a requirement
            lines, journal_problem = [], str(exc)[:120]
        signs = journal_signs(lines, m)
        hci = hcilog.signs(btsnoop) if btsnoop else None
        diagnosis = classify(watched["bond"], watched["events"], signs, hci=hci)
        diagnosis["journal"] = "unavailable" if journal_problem else "read"
        diagnosis["capture"] = "read" if btsnoop else (capture_problem or "needs the Keepsake Helper")
        await asyncio.to_thread(self.rules.record, a, m, diagnosis)
        key = rule_key(a, m)
        self.captures[key] = {
            **self.captures.get(key, {}),
            "bond": watched["bond"],
            "events": watched["events"],
            "journal": lines,
            "journalProblem": journal_problem,
            "diagnosis": diagnosis,
            "btsnoop": btsnoop,
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
            "hciCapture": "hci.btsnoop" if capture.get("btsnoop") else "none (needs the Keepsake Helper)",
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
                if capture.get("btsnoop"):
                    # Raw packets: the adapter address is in them, so they are left out when redacting.
                    if not redact_adapter:
                        bundle.writestr("hci.btsnoop", capture["btsnoop"])

        await asyncio.to_thread(write)
        self.rules.action("export", a, m, redacted=bool(redact_adapter))
        return {"file": name, "path": path}

    # Root jobs through the Keepsake Helper (R23, ADR-0083)

    def _ready(self) -> None:
        status = self.helper.status()
        if not status.get("ready"):
            raise ValueError(
                "update the Keepsake Helper to match Keepsake"
                if status.get("problem") == "version"
                else "install the Keepsake Helper first"
            )

    def _cable_pair(self, a: str, m: str, order: str) -> dict[str, Any]:
        self._ready()
        busy = self.busy()
        if busy:
            raise ValueError(f"not now: {busy}")
        stored = self.helper.bt_state(a, m)
        if not stored.get("record") or not stored.get("services"):
            raise ValueError(
                "BlueZ does not know this controller's services yet. "
                "Put it in pairing mode and use Reconnect once first."
            )
        nodes = cable.hid_nodes(self.sys_root, self.dev_root)
        usb = [(n, cable.provider_for(n)) for n in nodes if n.bus == "usb"]
        matched = None
        for node, provider in usb:
            if provider is None:
                continue
            identity = provider.read_identity(node, self.helper.get_feature)
            if identity["controller"] == m:
                matched = (node, provider)
                break
        if matched is None:
            raise ValueError(
                "connect this controller with a USB data cable first"
                if not any(p for _n, p in usb)
                else "the controller on the cable is a different one, or cable pairing is not supported for it"
            )
        node, provider = matched
        if self.rules.dry_run():
            self.rules.action("cable-pair", a, m, dryRun=True)
            return {"ok": True, "state": "dry-run", "message": "Dry run: nothing was written."}
        key = secrets.token_bytes(16)
        provider.write_pairing(node, a, key, self.helper.set_feature)
        provider.commit(node, self.helper.set_feature)
        if not provider.verify(node, a, self.helper.get_feature):
            self.rules.action("cable-pair", a, m, state="not-taken")
            raise ValueError("the controller did not take the new pairing; nothing was changed on this handheld")
        since = time.time() - 1
        file_key = key if order == "same" else bytes(reversed(key))
        done = self.helper.bt_install(a, m, file_key, provider.key_type)
        time.sleep(3.0)
        try:
            sixaxis = "sixaxis" in journal_signs(self.journal(since))
        except Exception:  # noqa: BLE001 - the journal only adds a warning
            sixaxis = False
        self.rules.action("cable-pair", a, m, order=order, sixaxis=sixaxis)
        return {
            "ok": True,
            "state": "paired",
            "backup": done.get("backup"),
            "sixaxis": sixaxis,
            "message": (
                "BlueZ's sixaxis plugin acted on the controller while it was plugged in, so it may have "
                "replaced the key. Unplug it and run cable pairing again."
                if sixaxis
                else "Paired. Unplug the controller, turn it off, then press its button."
            ),
        }

    async def cable_pair(self, adapter: Any, mac: Any, order: str = "same") -> dict[str, Any]:
        """Cable pairing through the device's provider and the helper. bluetoothd restarts."""
        a, m = self._gate(adapter, mac)
        if order not in ("same", "reversed"):
            raise ValueError("the key order is same or reversed")
        try:
            return await asyncio.to_thread(self._cable_pair, a, m, order)
        except (HelperError, cable.CableError, OSError) as exc:
            raise ValueError(str(exc)) from exc

    async def cable_restore(self, adapter: Any, mac: Any) -> dict[str, Any]:
        a, m = self._gate(adapter, mac)
        await asyncio.to_thread(self._ready)
        busy = self.busy()
        if busy:
            raise ValueError(f"not now: {busy}")
        try:
            done = await asyncio.to_thread(self.helper.bt_restore, a, m)
        except HelperError as exc:
            raise ValueError(str(exc)) from exc
        self.rules.action("restore-backup", a, m)
        return {"ok": True, "restored": done.get("restored")}

    async def set_ssp_gate(self, on: bool, adapter: Any = None, confirm: str = "") -> dict[str, Any]:
        """The SSP gate: on only with the exact confirmation text, after the screen's two steps."""
        if not on:
            await asyncio.to_thread(self._stop_gate)
            await asyncio.to_thread(self.rules.set_ssp_gate, None, None)
            return await self.status()
        if confirm != CONFIRM:
            raise ValueError("confirm the warning first")
        await asyncio.to_thread(self._ready)
        a = normal_mac(adapter)
        found = await asyncio.to_thread(bluez.list_devices, self.connect)
        path = next((f"/org/bluez/{x['name']}" for x in found["adapters"] if x["address"] == a), None)
        if a is None or path is None:
            raise ValueError("choose a Bluetooth adapter")
        await asyncio.to_thread(self.rules.set_ssp_gate, a, path)
        await asyncio.to_thread(self._start_gate, path)
        return await self.status()

    async def ssp_confirm_power_cycle(self) -> dict[str, Any]:
        """The kernel needs the adapter off to turn SSP off, and devices are connected: the user said yes."""
        gate = self.gate
        if gate is None:
            raise ValueError("the SSP gate is off")
        await asyncio.to_thread(gate.apply, 1, True)
        return await self.status()

    def arm_pairing(self, seconds: float = 60.0) -> None:
        if self.gate is not None:
            self.gate.arm(seconds)

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
            "helper": {k: status["helper"].get(k) for k in ("installed", "ready", "problem")},
            "sspGate": status["sspGate"]["state"] if status["sspGate"]["on"] else "off",
        }
