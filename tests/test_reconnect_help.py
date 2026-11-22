"""Controller reconnect help (R22, ADR-0082): rules, journal, classifier, cable providers, BlueZ.

Every address here is made up. The fake BlueZ bus records each call, so the tests can prove that
devices without help (a genuine DS4, an Xbox pad, an 8BitDo) are never acted on.
"""

from __future__ import annotations

import asyncio
import json
import os
import zipfile
from typing import Any

import pytest

from keepsake import devicechecks
from keepsake.desktop import dbus
from keepsake.device import bluez, cable, reconnect
from keepsake.device.reconnect_service import ReconnectService

ADAPTER = "C0:FF:EE:00:00:01"
OTHER_ADAPTER = "C0:FF:EE:00:00:02"
CLONE = "A1:B2:C3:D4:E5:01"  # first byte odd: not from a registered manufacturer
GENUINE = "10:20:30:40:50:60"
XBOX = "10:20:30:40:50:61"
EIGHTBITDO = "10:20:30:40:50:62"


def dev_path(mac: str, hci: str = "hci0") -> str:
    return f"/org/bluez/{hci}/dev_{mac.replace(':', '_')}"


def device(mac: str, hci: str = "hci0", **props: Any) -> dict[str, Any]:
    base = {
        "Address": ("s", mac),
        "Adapter": ("o", f"/org/bluez/{hci}"),
        "Alias": ("s", "Wireless Controller"),
        "Class": ("u", 0x002508),
        "Modalias": ("s", "usb:v054Cp09CCd0100"),
        "Paired": ("b", True),
        "Bonded": ("b", True),
        "Connected": ("b", False),
        "UUIDs": ("as", [bluez.HID_UUID]),
    }
    base.update({k: (type(v).__name__, v) for k, v in props.items()})
    return {bluez.DEVICE: base}


def objects() -> dict[str, Any]:
    return {
        "/org/bluez/hci0": {bluez.ADAPTER: {"Address": ("s", ADAPTER), "Powered": ("b", True)}},
        "/org/bluez/hci1": {bluez.ADAPTER: {"Address": ("s", OTHER_ADAPTER), "Powered": ("b", True)}},
        dev_path(CLONE): device(CLONE),
        dev_path(GENUINE): device(GENUINE),
        dev_path(XBOX): device(XBOX, Modalias="usb:v045Ep0B13d0001"),
        dev_path(EIGHTBITDO): device(EIGHTBITDO, Modalias="usb:v2DC8p6001d0001"),
        dev_path(CLONE, "hci1"): device(CLONE, "hci1"),
        "/org/bluez/hci0/dev_LE": {
            bluez.DEVICE: {
                "Address": ("s", "D0:00:00:00:00:09"),
                "Adapter": ("o", "/org/bluez/hci0"),
                "Paired": ("b", True),
                "AddressType": ("s", "random"),
            }
        },
    }


class FakeSock:
    def settimeout(self, _seconds: float) -> None:
        pass


class FakeBus:
    """A BlueZ bus: answers calls, records them, and plays scripted signals."""

    def __init__(self, signals: list[dict[str, Any]] | None = None, objs: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, str, list[Any]]] = []
        self.signals = list(signals or [])
        self.pending: list[dict[str, Any]] = []
        self.objs = objs if objs is not None else objects()
        self.sock = FakeSock()
        self.closed = False
        self.fail_on: str | None = None

    def call(
        self, _dest: str, path: str, _iface: str, member: str, _sig: str = "", body: list[Any] | None = None
    ) -> list[Any]:
        self.calls.append((member, path, list(body or [])))
        if member == self.fail_on:
            raise dbus.DBusError(f"org.bluez.Error.Failed: {member}")
        if member == "GetManagedObjects":
            return [self.objs]
        if member == "Get":
            return [("b", bool(self.objs[path][bluez.DEVICE]["Connected"][1]))]
        return []

    def receive(self) -> dict[str, Any]:
        if not self.signals:
            raise TimeoutError
        found = self.signals.pop(0)
        if isinstance(found, Exception):
            raise found
        return found

    def close(self) -> None:
        self.closed = True

    def members(self) -> list[str]:
        return [m for m, _p, _b in self.calls]

    def touched(self, mac: str) -> list[str]:
        """Calls that act on this device (anything but reading)."""
        return [m for m, p, _b in self.calls if p == dev_path(mac) and m not in ("Get",)]


def changed(mac: str, hci: str = "hci0", **props: Any) -> dict[str, Any]:
    return {
        "type": dbus.SIGNAL,
        "member": "PropertiesChanged",
        "path": dev_path(mac, hci),
        "body": [bluez.DEVICE, {k: ("b" if isinstance(v, bool) else "n", v) for k, v in props.items()}, []],
    }


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


@pytest.fixture
def rules(tmp_path: Any) -> reconnect.Rules:
    return reconnect.Rules(str(tmp_path / "reconnect-help.json"), clock=lambda: 1_800_000_000.0)


# Addresses


def test_normal_mac_and_masking() -> None:
    assert reconnect.normal_mac("a1-b2-c3-d4-e5-01") == CLONE
    assert reconnect.normal_mac("00:00:00:00:00:00") is None
    assert reconnect.normal_mac("ff:ff:ff:ff:ff:ff") is None
    assert reconnect.normal_mac("A1:B2:C3") is None
    assert reconnect.masked(CLONE) == "XX:XX:XX:XX:E5:01"


@pytest.mark.parametrize(
    ("mac", "flag"),
    [
        (CLONE, True),
        ("02:00:00:00:00:01", True),
        ("03:00:00:00:00:01", True),
        (GENUINE, False),
        ("04:00:00:00:00:01", False),
    ],
)
def test_unregistered_prefix(mac: str, flag: bool) -> None:
    assert reconnect.unregistered_prefix(mac) is flag


# Rules


def test_rules_are_keyed_by_adapter_and_device(rules: reconnect.Rules) -> None:
    rules.enable(ADAPTER, CLONE, "Clone")
    assert rules.enabled(ADAPTER, CLONE) is not None
    assert rules.enabled(OTHER_ADAPTER, CLONE) is None  # bonds are per adapter
    assert rules.enabled(ADAPTER, GENUINE) is None
    assert rules.disable(ADAPTER, CLONE) is True
    assert rules.enabled(ADAPTER, CLONE) is None


def test_rules_reject_bad_addresses_and_unknown_options(rules: reconnect.Rules) -> None:
    with pytest.raises(ValueError):
        rules.enable(ADAPTER, "not-a-mac")
    with pytest.raises(ValueError):
        rules.set_option(ADAPTER, CLONE, "commit", False)  # help is not on
    rules.enable(ADAPTER, CLONE)
    with pytest.raises(ValueError):
        rules.set_option(ADAPTER, CLONE, "removeDevice", True)


def test_action_log_is_append_only_and_masked(rules: reconnect.Rules) -> None:
    rules.enable(ADAPTER, CLONE)
    rules.set_dry_run(True)
    rules.disable(ADAPTER, CLONE)
    entries = rules.actions()
    assert [e["action"] for e in entries] == ["help-on", "dry-run", "help-off"]
    with open(rules.log_path, encoding="utf-8") as handle:
        text = handle.read()
    assert CLONE not in text and ADAPTER not in text
    assert entries[0]["device"] == "XX:XX:XX:XX:E5:01"
    assert entries[0]["at"].endswith("Z")


def test_suggestions_are_noted_once_and_cleared_by_help(rules: reconnect.Rules) -> None:
    assert rules.suggest(ADAPTER, CLONE, "dropped") is True
    assert rules.suggest(ADAPTER, CLONE, "dropped") is False
    rules.enable(ADAPTER, CLONE)
    assert rules.state()["suggest"] == {}


def test_tampered_rule_file_keys_are_ignored(rules: reconnect.Rules) -> None:
    with open(rules.path, "w", encoding="utf-8") as handle:
        json.dump({"rules": {f"{ADAPTER}/{GENUINE}": {"adapter": ADAPTER, "mac": CLONE}}}, handle)
    assert rules.enabled(ADAPTER, GENUINE) is None
    assert rules.enabled(ADAPTER, CLONE) is None


# Journal


def test_read_journal_runs_bounded_journalctl() -> None:
    seen: list[list[str]] = []

    def runner(argv: list[str]) -> str:
        seen.append(argv)
        return "1.0 host bluetoothd[1]: line\n"

    lines = reconnect.read_journal(1_800_000_000.5, runner)
    assert len(lines) == 2
    assert all(a[0] == "journalctl" and "--since=@1800000000" in a and "-n" in a for a in seen)
    assert ["-u", "bluetooth.service"] == seen[0][-4:-2] and "-k" in seen[1]


def test_journal_signs_skip_other_devices() -> None:
    lines = [
        f"1 h bluetoothd[1]: Refusing input device connect: Operation already in progress (114) {GENUINE}",
        f"2 h kernel: Bluetooth: {CLONE} Authentication Failure",
        "3 h bluetoothd[1]: sixaxis: compatible device connected",
    ]
    assert reconnect.journal_signs(lines, CLONE) == {"auth-failure", "sixaxis"}
    assert "collision" in reconnect.journal_signs(lines)


def test_redact_replaces_the_adapter_only() -> None:
    lines = [f"x {ADAPTER.lower()} y {CLONE}", f"/org/bluez/hci0/dev_x {ADAPTER.replace(':', '_')}"]
    out = reconnect.redact(lines, ADAPTER)
    assert ADAPTER.lower() not in out[0] and CLONE in out[0]
    assert "HOST_ADAPTER" in out[1]


# Classifier


def bond(**over: Any) -> dict[str, Any]:
    return {"Paired": True, "Bonded": True, "UUIDs": 3, **over}


@pytest.mark.parametrize(
    ("args", "outcome"),
    [
        ({"bond": bond(), "events": []}, "O1"),
        ({"bond": bond(), "events": [(1.0, "Connected", True), (1.5, "Connected", False)]}, "O2"),
        ({"bond": bond(UUIDs=0), "events": [(1.0, "Connected", True), (1.5, "Connected", False)]}, "O5"),
        ({"bond": bond(), "events": [(1.0, "Connected", True), (30.0, "Connected", False)]}, "O7"),
        ({"bond": bond(), "events": [(1.0, "Connected", True)]}, "OK"),
        ({"bond": bond(Paired=False, Bonded=False), "events": []}, "O4"),
        ({"bond": bond(), "events": [], "signs": {"collision"}}, "O6"),
        ({"bond": None, "events": []}, "NONE"),
        (
            {
                "bond": bond(),
                "events": [],
                "identity": {"controller": CLONE, "host": "0A:0B:0C:0D:0E:0F"},
                "adapter": ADAPTER,
            },
            "OTHER-HOST",
        ),
        ({"bond": bond(), "events": [], "identity": {"controller": CLONE, "host": None}, "adapter": ADAPTER}, "O1"),
        (
            {
                "bond": bond(),
                "events": [],
                "identity": {"controller": CLONE, "host": ADAPTER},
                "adapter": ADAPTER,
                "watched": False,
            },
            "STORED",
        ),
    ],
)
def test_classify(args: dict[str, Any], outcome: str) -> None:
    found = reconnect.classify(**args)
    assert found["outcome"] == outcome
    assert found["title"] and found["advice"]


def test_classify_flags_sixaxis_activity() -> None:
    found = reconnect.classify(bond(), [(1.0, "Connected", True)], {"sixaxis"})
    assert found["sixaxis"] is True and "journal: sixaxis" in found["evidence"]


# Cable providers (fake hidraw)


def hidraw(tmp_path: Any, name: str, bus: int, vendor: str, product: str, uniq: str = "") -> None:
    folder = tmp_path / "sys" / "class" / "hidraw" / name / "device"
    folder.mkdir(parents=True)
    (folder / "uevent").write_text(
        f"DRIVER=playstation\nHID_ID={bus:04X}:0000{vendor}:0000{product}\nHID_NAME=Pad\nHID_UNIQ={uniq}\n"
    )


def le(mac: str) -> bytes:
    return bytes(reversed(bytes.fromhex(mac.replace(":", ""))))


def pairing_report(controller: str, host: str | None) -> bytes:
    return bytes([0x12]) + le(controller) + b"\x00\x00\x00" + (le(host) if host else bytes(6))


class FakeHid:
    def __init__(self, reports: dict[str, bytes] | None = None, error: Exception | None = None) -> None:
        self.reports = reports or {}
        self.error = error
        self.gets: list[tuple[str, int, int]] = []
        self.sets: list[tuple[str, bytes]] = []

    def get(self, node: str, report: int, length: int) -> bytes:
        self.gets.append((node, report, length))
        if self.error:
            raise self.error
        return self.reports.get(node, bytes(length))

    def put(self, node: str, data: bytes) -> None:
        self.sets.append((node, data))


def test_hid_nodes_and_provider_choice(tmp_path: Any) -> None:
    hidraw(tmp_path, "hidraw0", 3, "054C", "09CC")
    hidraw(tmp_path, "hidraw1", 3, "045E", "0B12")  # an Xbox pad on USB
    hidraw(tmp_path, "hidraw2", 5, "054C", "05C4", CLONE.lower())
    nodes = cable.hid_nodes(str(tmp_path / "sys"), "/dev")
    assert [(n.bus, n.vendor, n.product) for n in nodes] == [
        ("usb", "054C", "09CC"),
        ("usb", "045E", "0B12"),
        ("bluetooth", "054C", "05C4"),
    ]
    assert nodes[2].address == CLONE
    assert isinstance(cable.provider_for(nodes[0]), cable.DualShock4)
    assert cable.provider_for(nodes[1]) is None


def test_read_stored_host_confirms_identity(tmp_path: Any) -> None:
    hidraw(tmp_path, "hidraw0", 3, "054C", "09CC")
    nodes = cable.hid_nodes(str(tmp_path / "sys"), "/dev")
    hid = FakeHid({"/dev/hidraw0": pairing_report(CLONE, ADAPTER)})
    found = cable.read_stored_host(CLONE, nodes, hid.get)
    assert found["ok"] and found["controller"] == CLONE and found["host"] == ADAPTER
    assert hid.gets == [("/dev/hidraw0", 0x12, 16)]


def test_read_stored_host_aborts_on_a_different_controller(tmp_path: Any) -> None:
    hidraw(tmp_path, "hidraw0", 3, "054C", "09CC")
    nodes = cable.hid_nodes(str(tmp_path / "sys"), "/dev")
    hid = FakeHid({"/dev/hidraw0": pairing_report(GENUINE, ADAPTER)})
    found = cable.read_stored_host(CLONE, nodes, hid.get)
    assert found["state"] == "mismatch" and not found["ok"]
    assert hid.sets == []


@pytest.mark.parametrize(
    ("product_vendor", "hid", "state"),
    [
        (("045E", "0B12"), FakeHid(), "unsupported"),
        (("054C", "09CC"), FakeHid(error=PermissionError()), "permission"),
        (("054C", "09CC"), FakeHid(error=OSError()), "unreadable"),
    ],
)
def test_read_stored_host_problems(tmp_path: Any, product_vendor: tuple[str, str], hid: FakeHid, state: str) -> None:
    hidraw(tmp_path, "hidraw0", 3, *product_vendor)
    nodes = cable.hid_nodes(str(tmp_path / "sys"), "/dev")
    assert cable.read_stored_host(CLONE, nodes, hid.get)["state"] == state


def test_read_stored_host_without_usb() -> None:
    assert cable.read_stored_host(CLONE, [], FakeHid().get)["state"] == "no-usb"


def test_ds4_rejects_a_wrong_report() -> None:
    node = cable.HidNode("/dev/hidraw0", "usb", "054C", "09CC", None)
    with pytest.raises(cable.CableError):
        cable.DualShock4().read_identity(node, FakeHid({"/dev/hidraw0": bytes([0x13]) + bytes(15)}).get)


def test_ds4_write_and_commit_layouts() -> None:
    node = cable.HidNode("/dev/hidraw0", "usb", "054C", "09CC", None)
    hid = FakeHid()
    provider = cable.DualShock4()
    key = bytes(range(16))
    provider.write_pairing(node, ADAPTER, key, hid.put)
    provider.commit(node, hid.put)
    pairing, commit = hid.sets[0][1], hid.sets[1][1]
    assert len(pairing) == 23 and pairing[0] == 0x13 and pairing[1:7] == le(ADAPTER) and pairing[7:] == key
    assert len(commit) == 17 and commit[:2] == b"\x14\x02" and commit[2:] == bytes(15)
    assert provider.key_type == 4
    with pytest.raises(cable.CableError):
        provider.write_pairing(node, ADAPTER, b"short", hid.put)


def test_full_report_needs_the_rule_and_the_address(tmp_path: Any) -> None:
    hidraw(tmp_path, "hidraw0", 5, "054C", "09CC", GENUINE)
    hidraw(tmp_path, "hidraw1", 5, "054C", "09CC", CLONE)
    nodes = cable.hid_nodes(str(tmp_path / "sys"), "/dev")
    hid = FakeHid()
    assert cable.full_report(CLONE, False, nodes, hid.get) is False
    assert cable.full_report(CLONE, True, nodes, hid.get) is True
    assert hid.gets == [("/dev/hidraw1", 0x02, 37)]  # the genuine pad's node is never read


# BlueZ (fake bus)


def gate_for(*keys: tuple[str, str], commit: bool = True) -> bluez.Gate:
    def gate(adapter: str, mac: str) -> dict[str, Any] | None:
        return {"commit": commit} if (adapter, mac) in keys else None

    return gate


def test_devices_lists_every_paired_device_with_details() -> None:
    found = bluez.devices(FakeBus())
    assert len(found["adapters"]) == 2
    clone = next(d for d in found["devices"] if d["mac"] == CLONE and d["adapter"] == ADAPTER)
    assert clone["class"] == "0x002508" and clone["modalias"] == "usb:v054Cp09CCd0100"
    assert clone["unregisteredPrefix"] is True and clone["transport"] == "bredr" and clone["adapterName"] == "hci0"
    genuine = next(d for d in found["devices"] if d["mac"] == GENUINE)
    assert genuine["unregisteredPrefix"] is False
    assert next(d for d in found["devices"] if d["mac"] == "D0:00:00:00:00:09")["transport"] == "le"


def test_assist_refuses_devices_without_help() -> None:
    for mac in (GENUINE, XBOX, EIGHTBITDO):
        bus = FakeBus()
        with pytest.raises(bluez.BlueZError):
            bluez.assist(ADAPTER, mac, gate_for((ADAPTER, CLONE)), lambda bus=bus: bus)
        assert bus.calls == []
    bus = FakeBus()
    with pytest.raises(bluez.BlueZError):
        bluez.assist(OTHER_ADAPTER, CLONE, gate_for((ADAPTER, CLONE)), lambda: bus)
    assert bus.calls == []


def test_assist_stops_discovery_when_seen_then_connects() -> None:
    bus = FakeBus([changed(GENUINE, RSSI=-50), changed(CLONE, RSSI=-40)])
    result = bluez.assist(ADAPTER, CLONE, gate_for((ADAPTER, CLONE)), lambda: bus, Clock())
    assert result["state"] == "connected"
    members = bus.members()
    assert members.index("StartDiscovery") < members.index("StopDiscovery") < members.index("ConnectProfile")
    assert bus.calls[-1] == ("ConnectProfile", dev_path(CLONE), [bluez.HID_UUID])
    assert bus.touched(GENUINE) == [] and bus.closed


def test_assist_uses_the_ruled_adapter_only() -> None:
    bus = FakeBus([changed(CLONE, RSSI=-50), changed(CLONE, "hci1", RSSI=-40)])
    result = bluez.assist(OTHER_ADAPTER, CLONE, gate_for((OTHER_ADAPTER, CLONE)), lambda: bus, Clock())
    assert result["state"] == "connected"
    assert bus.calls[-1] == ("ConnectProfile", dev_path(CLONE, "hci1"), [bluez.HID_UUID])
    assert bus.touched(CLONE) == []  # the same pad's bond on hci0 is left alone


def test_assist_always_stops_discovery() -> None:
    bus = FakeBus([])
    result = bluez.assist(ADAPTER, CLONE, gate_for((ADAPTER, CLONE)), lambda: bus, Clock(), window=5)
    assert result["state"] == "not-seen"
    assert bus.members().count("StopDiscovery") == 1 and "ConnectProfile" not in bus.members()
    bus = FakeBus([OSError("bus gone")])
    with pytest.raises(OSError):
        bluez.assist(ADAPTER, CLONE, gate_for((ADAPTER, CLONE)), lambda: bus, Clock())
    assert "StopDiscovery" in bus.members()


def test_assist_skips_connected_devices_and_dry_run() -> None:
    objs = objects()
    objs[dev_path(CLONE)] = device(CLONE, Connected=True)
    bus = FakeBus(objs=objs)
    assert bluez.assist(ADAPTER, CLONE, gate_for((ADAPTER, CLONE)), lambda: bus)["state"] == "already"
    assert "StartDiscovery" not in bus.members()
    bus = FakeBus()
    assert bluez.assist(ADAPTER, CLONE, gate_for((ADAPTER, CLONE)), lambda: bus, dry_run=True)["state"] == "dry-run"
    assert "StartDiscovery" not in bus.members()


def test_watch_reconnect_records_one_attempt() -> None:
    bus = FakeBus([changed(GENUINE, Connected=True), changed(CLONE, Connected=True), changed(CLONE, Connected=False)])
    found = bluez.watch_reconnect(ADAPTER, CLONE, gate_for((ADAPTER, CLONE)), lambda: bus, Clock())
    assert [(n, v) for _t, n, v in found["events"]] == [("Connected", True), ("Connected", False)]
    assert found["bond"]["Paired"] is True and found["bond"]["UUIDs"] == 1
    assert "ConnectProfile" not in bus.members() and "StartDiscovery" not in bus.members()


def watcher(gate: bluez.Gate, **kwargs: Any) -> tuple[bluez.Watcher, FakeBus]:
    bus = FakeBus()
    w = bluez.Watcher(gate, connect=lambda: bus, **kwargs)
    w.refresh(bus)
    bus.calls.clear()
    return w, bus


def test_watcher_commits_only_for_helped_devices() -> None:
    w, bus = watcher(gate_for((ADAPTER, CLONE)))
    for mac in (GENUINE, XBOX, EIGHTBITDO):
        assert w.handle(bus, changed(mac, Paired=True)) is None
    assert w.handle(bus, changed(CLONE, "hci1", Paired=True)) is None  # same pad, other adapter: no rule
    assert bus.calls == []
    assert w.handle(bus, changed(CLONE, Paired=True)) == "commit"
    assert bus.calls == [
        ("Get", dev_path(CLONE), [bluez.DEVICE, "Connected"]),
        ("ConnectProfile", dev_path(CLONE), [bluez.HID_UUID]),
    ]


def test_watcher_never_collides_or_runs_when_commit_is_off() -> None:
    w, bus = watcher(gate_for((ADAPTER, CLONE)))
    assert w.handle(bus, changed(CLONE, Paired=True, Connected=True)) is None
    assert "ConnectProfile" not in bus.members()
    w, bus = watcher(gate_for((ADAPTER, CLONE), commit=False))
    assert w.handle(bus, changed(CLONE, Paired=True)) is None
    assert bus.calls == []
    w, bus = watcher(gate_for((ADAPTER, CLONE)), dry_run=lambda: True)
    assert w.handle(bus, changed(CLONE, Paired=True)) == "dry-run"
    assert "ConnectProfile" not in bus.members()


def test_watcher_suggests_but_never_acts_on_quick_drops() -> None:
    noted: list[tuple[str, str, str]] = []
    clock = Clock()
    w, bus = watcher(gate_for(), on_failure=lambda a, m, r: noted.append((a, m, r)), clock=clock)
    w.handle(bus, changed(GENUINE, Connected=True))
    assert w.handle(bus, changed(GENUINE, Connected=False)) == "suggest"
    assert noted == [(ADAPTER, GENUINE, "connected, then dropped within 5 seconds")]
    assert bus.calls == []
    w.handle(bus, changed(XBOX, Connected=True))
    clock.now += 60
    assert w.handle(bus, changed(XBOX, Connected=False)) is None


def test_watcher_full_mode_callback_only_for_helped() -> None:
    seen: list[str] = []
    w, bus = watcher(gate_for((ADAPTER, CLONE)), on_connected=lambda a, m, r: seen.append(m))
    w.handle(bus, changed(GENUINE, Connected=True))
    assert w.handle(bus, changed(CLONE, Connected=True)) == "connected"
    assert seen == [CLONE]


# The service


def service(
    tmp_path: Any, bus: FakeBus, hid: FakeHid | None = None, journal: list[str] | None = None
) -> ReconnectService:
    return ReconnectService(
        str(tmp_path / "settings"),
        str(tmp_path / "sys"),
        "/dev",
        connect=lambda: bus,
        journal=lambda since: list(journal or []),
        get=(hid or FakeHid()).get,
    )


def test_service_status_marks_help_and_suggestions(tmp_path: Any) -> None:
    svc = service(tmp_path, FakeBus())
    asyncio.run(svc.set_help(ADAPTER, CLONE, True, "Clone"))
    svc.rules.suggest(ADAPTER, GENUINE, "dropped")
    status = asyncio.run(svc.status())
    by = {(d["adapter"], d["mac"]): d for d in status["devices"]}
    assert by[(ADAPTER, CLONE)]["help"] and not by[(OTHER_ADAPTER, CLONE)]["help"]
    assert by[(ADAPTER, GENUINE)]["suggest"]["reason"] == "dropped"
    assert status["available"] and not status["dryRun"]


def test_service_actions_need_help(tmp_path: Any) -> None:
    svc = service(tmp_path, FakeBus())
    for call in (svc.read_usb, svc.diagnose, svc.export):
        with pytest.raises(ValueError):
            asyncio.run(call(ADAPTER, GENUINE))


def test_service_read_usb_reports_only_the_match(tmp_path: Any) -> None:
    hidraw(tmp_path, "hidraw0", 3, "054C", "09CC")
    svc = service(tmp_path, FakeBus(), FakeHid({"/dev/hidraw0": pairing_report(CLONE, "0A:0B:0C:0D:0E:0F")}))
    asyncio.run(svc.set_help(ADAPTER, CLONE, True))
    found = asyncio.run(svc.read_usb(ADAPTER, CLONE))
    assert found["read"] == {"ok": True, "family": "DualShock 4", "storesThisHandheld": False}
    assert found["diagnosis"]["outcome"] == "OTHER-HOST"
    assert "0A:0B" not in json.dumps(found["read"])


def test_service_diagnose_then_export_redacts_the_adapter(tmp_path: Any) -> None:
    bus = FakeBus([changed(CLONE, Connected=True), changed(CLONE, Connected=False)])
    lines = [f"1 h kernel: Bluetooth: hci0 {ADAPTER} {CLONE} Authentication Failure"]
    svc = service(tmp_path, bus, journal=lines)
    asyncio.run(svc.set_help(ADAPTER, CLONE, True))
    diagnosis = asyncio.run(svc.diagnose(ADAPTER, CLONE))
    assert diagnosis["outcome"] == "O2" and "journal: auth failure" in diagnosis["evidence"]
    assert svc.rules.state()["last"][f"{ADAPTER}/{CLONE}"]["outcome"] == "O2"
    found = asyncio.run(svc.export(ADAPTER, CLONE, True))
    with zipfile.ZipFile(found["path"]) as bundle:
        text = bundle.read("report.json").decode() + bundle.read("journal.txt").decode()
    assert ADAPTER not in text and CLONE in text and "HOST-ADAPTER" in text
    found = asyncio.run(svc.export(ADAPTER, CLONE, False))
    with zipfile.ZipFile(found["path"]) as bundle:
        assert ADAPTER in bundle.read("report.json").decode()
    for name in os.listdir(tmp_path / "settings"):
        assert CLONE.replace(":", "") not in name


def test_service_probe_and_device_check_are_redacted(tmp_path: Any) -> None:
    svc = service(tmp_path, FakeBus())
    asyncio.run(svc.set_help(ADAPTER, CLONE, True))
    probe = asyncio.run(svc.probe())
    assert ADAPTER not in json.dumps(probe) and CLONE not in json.dumps(probe)
    assert probe["helped"][0]["device"] == "XX:XX:XX:XX:E5:01" and probe["journal"] == "read"
    ctx = devicechecks.Context(
        home=str(tmp_path),
        proc_root=str(tmp_path),
        sys_root=str(tmp_path),
        library=None,
        places=[],
        work_dir=str(tmp_path),
        links=None,
        connect_for=None,
        probes={"reconnect-help": svc.probe},
    )
    outcome = asyncio.run(devicechecks.run("reconnect-help", ctx))
    assert outcome["status"] == "warn"  # the watcher thread is not running in the test
    assert "help on for 1" in outcome["found"]


def test_device_check_fails_when_bluetooth_cannot_be_read(tmp_path: Any) -> None:
    async def probe() -> dict[str, Any]:
        return {"available": False, "problem": "Bluetooth could not be reached (OSError)"}

    ctx = devicechecks.Context(
        home=str(tmp_path),
        proc_root=str(tmp_path),
        sys_root=str(tmp_path),
        library=None,
        places=[],
        work_dir=str(tmp_path),
        links=None,
        connect_for=None,
        probes={"reconnect-help": probe},
    )
    assert asyncio.run(devicechecks.run("reconnect-help", ctx))["status"] == "fail"
