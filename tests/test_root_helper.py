"""The Keepsake Helper and Keepsake's root jobs through it (R23, ADR-0083). Every address is made up."""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import zipfile
from typing import Any

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "helper", "py_modules"))

from keepsake.device import hcilog, reconnect  # noqa: E402
from keepsake.device.helper import HelperClient, HelperError, HelperMissing, HelperVersion  # noqa: E402
from keepsake.device.reconnect_service import ReconnectService  # noqa: E402
from keepsake.device.sspgate import SspGate  # noqa: E402
from keepsake_helper import bluetooth, hid, keyfile, mgmt, server  # noqa: E402

ADAPTER = "C0:FF:EE:00:00:01"
CLONE = "A1:B2:C3:D4:E5:01"
GENUINE = "10:20:30:40:50:60"
KEY = bytes(range(16))


def name(address: str) -> str:
    return address.replace(":", "-") if sys.platform == "win32" else address


@pytest.fixture(autouse=True)
def windows_folders(monkeypatch: Any) -> None:
    monkeypatch.setattr(bluetooth, "folder_name", name)


INFO = (
    "[General]\n"
    "Name=Wireless Controller\n"
    "Class=0x002508\n"
    "SupportedTechnologies=BR/EDR;\n"
    "Trusted=false\n"
    "Blocked=false\n"
    "Services=00001124-0000-1000-8000-00805f9b34fb;\n"
    "\n"
    "[LinkKey]\n"
    "Key=00000000000000000000000000000000\n"
    "Type=4\n"
    "PINLength=0\n"
    "\n"
    "[DeviceID]\n"
    "Source=2\n"
    "Vendor=1356\n"
)


# The info file


def test_install_key_changes_only_the_key_and_trusted() -> None:
    after = keyfile.install_key(INFO, KEY, 4)
    before_lines, after_lines = INFO.split("\n"), after.split("\n")
    assert len(before_lines) == len(after_lines)
    changed = [(b, a) for b, a in zip(before_lines, after_lines, strict=True) if b != a]
    assert changed == [
        ("Trusted=false", "Trusted=true"),
        ("Key=00000000000000000000000000000000", f"Key={KEY.hex().upper()}"),
    ]


def test_install_key_adds_missing_section_and_keys() -> None:
    text = "[General]\nName=Pad\n"
    after = keyfile.install_key(text, KEY, 4)
    assert after.startswith("[General]\nName=Pad\nTrusted=true\n")
    assert keyfile.get_values(after, "LinkKey") == {"Key": KEY.hex().upper(), "Type": "4", "PINLength": "0"}


def test_install_key_keeps_crlf_and_blank_separators() -> None:
    text = INFO.replace("\n", "\r\n").replace("PINLength=0\r\n", "")
    after = keyfile.install_key(text, KEY, 4)
    assert "\r\n" in after and "\n" not in after.replace("\r\n", "")
    assert "PINLength=0\r\n\r\n[DeviceID]" in after


def test_install_key_rejects_bad_keys() -> None:
    with pytest.raises(ValueError):
        keyfile.install_key(INFO, b"short", 4)
    with pytest.raises(ValueError):
        keyfile.install_key(INFO, KEY, 9)


class FakeSystemd:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def stop(self) -> None:
        self.log.append("stop")

    def start(self) -> None:
        self.log.append("start")


def bt_root(tmp_path: Any, text: str | None = INFO, cache: bool = True) -> str:
    root = tmp_path / "bluetooth"
    folder = root / name(ADAPTER) / name(CLONE)
    folder.mkdir(parents=True)
    if text is not None:
        (folder / "info").write_bytes(text.encode("utf-8"))
    if cache:
        (root / name(ADAPTER) / "cache").mkdir()
        (root / name(ADAPTER) / "cache" / name(CLONE)).write_text("[ServiceRecords]\n")
    return str(root)


def test_state_never_returns_the_key(tmp_path: Any) -> None:
    root = bt_root(tmp_path)
    found = bluetooth.state(ADAPTER, CLONE, root)
    assert found["record"] and found["linkKey"] and found["keyType"] == 4 and found["cache"]
    assert "0000000000" not in json.dumps(found)


def test_install_backs_up_and_restarts_around_the_write(tmp_path: Any) -> None:
    root = bt_root(tmp_path)
    log: list[str] = []
    done = bluetooth.install(ADAPTER, CLONE, KEY, 4, FakeSystemd(log), root, clock=lambda: 1_800_000_000)
    assert log == ["stop", "start"]
    path = bluetooth.info_path(ADAPTER, CLONE, root)
    with open(path, encoding="utf-8") as handle:
        assert f"Key={KEY.hex().upper()}" in handle.read()
    with open(os.path.join(os.path.dirname(path), done["backup"]), encoding="utf-8", newline="") as handle:
        assert handle.read() == INFO
    restored = bluetooth.restore(ADAPTER, CLONE, FakeSystemd(log), root)
    assert restored["restored"] == done["backup"]
    with open(path, encoding="utf-8", newline="") as handle:
        assert handle.read() == INFO
    assert log == ["stop", "start", "stop", "start"]


def test_install_starts_bluetooth_again_when_the_write_fails(tmp_path: Any, monkeypatch: Any) -> None:
    root = bt_root(tmp_path)
    log: list[str] = []

    def broken(*_args: Any) -> str:
        raise ValueError("bad file")

    monkeypatch.setattr(keyfile, "install_key", broken)
    with pytest.raises(ValueError):
        bluetooth.install(ADAPTER, CLONE, KEY, 4, FakeSystemd(log), root)
    assert log == ["stop", "start"]


def test_install_needs_the_record_and_valid_addresses(tmp_path: Any) -> None:
    root = bt_root(tmp_path, text=None)
    with pytest.raises(bluetooth.BluetoothError):
        bluetooth.install(ADAPTER, CLONE, KEY, 4, FakeSystemd([]), root)
    for bad in ("../../etc", "C0:FF:EE:00:00", "00:00:00:00:00:00"):
        with pytest.raises(bluetooth.BluetoothError):
            bluetooth.info_path(bad, CLONE, root)


def test_backups_are_pruned(tmp_path: Any) -> None:
    root = bt_root(tmp_path)
    for n in range(8):
        bluetooth.install(ADAPTER, CLONE, KEY, 4, FakeSystemd([]), root, clock=lambda n=n: 1_800_000_000 + n)
    assert len(bluetooth.backups(ADAPTER, CLONE, root)) == bluetooth.MAX_BACKUPS


@pytest.mark.posix
@pytest.mark.skipif(sys.platform == "win32", reason="symbolic links need POSIX")
def test_info_path_refuses_symbolic_links(tmp_path: Any) -> None:
    root = tmp_path / "bluetooth"
    (root / name(ADAPTER)).mkdir(parents=True)
    os.symlink(str(tmp_path), str(root / name(ADAPTER) / name(CLONE)))
    with pytest.raises(bluetooth.BluetoothError):
        bluetooth.info_path(ADAPTER, CLONE, str(root))


# hidraw allow-list


def hidraw(tmp_path: Any, name: str, bus: int, vendor: str, product: str) -> str:
    folder = tmp_path / "sys" / "class" / "hidraw" / name / "device"
    folder.mkdir(parents=True)
    (folder / "uevent").write_text(f"HID_ID={bus:04X}:0000{vendor}:0000{product}\n")
    return str(tmp_path / "sys")


def test_hid_only_usb_provider_nodes(tmp_path: Any) -> None:
    sys_root = hidraw(tmp_path, "hidraw0", 3, "054C", "09CC")
    hidraw(tmp_path, "hidraw1", 5, "054C", "09CC")  # Bluetooth
    hidraw(tmp_path, "hidraw2", 3, "045E", "0B12")  # Xbox
    assert hid.check_node("/dev/hidraw0", sys_root) == "/dev/hidraw0"
    for node in ("/dev/hidraw1", "/dev/hidraw2", "/dev/hidraw9", "/dev/../etc/shadow", "/dev/sda", ""):
        with pytest.raises(hid.HidError):
            hid.check_node(node, sys_root)


def test_hid_reports_allow_list(tmp_path: Any) -> None:
    sys_root = hidraw(tmp_path, "hidraw0", 3, "054C", "09CC")
    seen: list[tuple[int, bytes]] = []

    def ioctl(_node: str, request: int, buffer: bytearray) -> None:
        seen.append((request, bytes(buffer)))

    assert len(hid.get_feature("/dev/hidraw0", 0x12, sys_root, ioctl)) == 16
    hid.set_feature("/dev/hidraw0", bytes([0x13]) + bytes(22), sys_root, ioctl)
    hid.set_feature("/dev/hidraw0", bytes([0x14, 0x02]) + bytes(15), sys_root, ioctl)
    for report in (0x02, 0x81, "18"):
        with pytest.raises(hid.HidError):
            hid.get_feature("/dev/hidraw0", report, sys_root, ioctl)
    for data in (bytes([0x14, 0x01]) + bytes(15), bytes([0x13]) + bytes(5), bytes([0x08]) + bytes(22), b""):
        with pytest.raises(hid.HidError):
            hid.set_feature("/dev/hidraw0", data, sys_root, ioctl)
    assert len(seen) == 3


# MGMT and capture (fake kernel socket)


class FakeMgmt:
    """Answers MGMT commands; ``refuse_powered`` rejects SSP off while powered."""

    def __init__(self, refuse_powered: bool = False, status: int = 0) -> None:
        self.sent: list[tuple[int, int, bytes]] = []
        self.replies: list[bytes] = []
        self.powered = True
        self.ssp = True
        self.refuse_powered = refuse_powered
        self.status = status

    def settimeout(self, _t: float) -> None:
        pass

    def send(self, data: bytes) -> None:
        opcode, index, length = struct.unpack("<HHH", data[:6])
        params = data[6 : 6 + length]
        self.sent.append((opcode, index, params))
        status = self.status
        if opcode == mgmt.OP_SET_SSP:
            if self.refuse_powered and self.powered and params == b"\x00":
                status = 0x0B
            elif status == 0:
                self.ssp = params == b"\x01"
        if opcode == mgmt.OP_SET_POWERED:
            self.powered = params == b"\x01"
        current = (mgmt.SETTING_POWERED if self.powered else 0) | (mgmt.SETTING_SSP if self.ssp else 0)
        body = struct.pack("<HB", opcode, status) + (struct.pack("<I", current) if status == 0 else b"")
        noise = struct.pack("<HHH", 0x0006, index, 4) + b"\x00" * 4  # an unrelated event first
        self.replies += [
            noise,
            struct.pack("<HHH", mgmt.EV_COMPLETE if status == 0 else mgmt.EV_STATUS, index, len(body)) + body,
        ]

    def recv(self, _size: int) -> bytes:
        return self.replies.pop(0)

    def close(self) -> None:
        pass


def test_set_ssp_off_and_on() -> None:
    fake = FakeMgmt()
    assert mgmt.set_ssp(0, False, lambda _c: fake) == {"ok": True, "ssp": False, "powered": True}
    assert mgmt.set_ssp(0, True, lambda _c: fake)["ssp"] is True


def test_set_ssp_reports_power_cycle_need_and_cycles_only_when_asked() -> None:
    fake = FakeMgmt(refuse_powered=True)
    found = mgmt.set_ssp(0, False, lambda _c: fake)
    assert found == {"ok": False, "problem": "rejected", "needsPowerCycle": True}
    assert [op for op, _i, _p in fake.sent] == [mgmt.OP_SET_SSP]
    found = mgmt.set_ssp(0, False, lambda _c: fake, power_cycle=True)
    assert found["ok"] and found["powered"]
    assert [(op, p) for op, _i, p in fake.sent[1:]] == [
        (mgmt.OP_SET_SSP, b"\x00"),
        (mgmt.OP_SET_POWERED, b"\x00"),
        (mgmt.OP_SET_SSP, b"\x00"),
        (mgmt.OP_SET_POWERED, b"\x01"),
    ]


def event(code: int, params: bytes) -> bytes:
    return bytes([code, len(params)]) + params


def monitor_packets(*packets: tuple[int, bytes]) -> list[bytes]:
    return [struct.pack("<HHH", op, 0, len(p)) + p for op, p in packets]


class FakeMonitor:
    def __init__(self, packets: list[bytes]) -> None:
        self.packets = packets

    def settimeout(self, _t: float) -> None:
        pass

    def recv(self, _size: int) -> bytes:
        if not self.packets:
            raise TimeoutError
        return self.packets.pop(0)

    def close(self) -> None:
        pass


def acl_signal(code: int, data: bytes) -> bytes:
    signal = struct.pack("<BBH", code, 1, len(data)) + data
    return struct.pack("<HH", 0x0001, len(signal) + 4) + struct.pack("<HH", len(signal), 0x0001) + signal


def test_capture_writes_btsnoop_that_hcilog_reads(monkeypatch: Any) -> None:
    packets = monitor_packets(
        (hcilog.MON_EVENT, event(0x04, bytes(10))),  # Connection Request
        (hcilog.MON_COMMAND, struct.pack("<HB", 0x040B, 22) + bytes(22)),  # Link Key Request Reply
        (hcilog.MON_ACL_RX, acl_signal(0x03, struct.pack("<HHHH", 0x40, 0x41, 0x0003, 0))),  # security block
        (hcilog.MON_EVENT, event(0x05, bytes([0, 1, 0, 0x05]))),  # Disconnection: auth failure
    )
    ticks = iter([0.0, 0.0] + [0.1 * n for n in range(1, 50)] + [99.0] * 10)
    monkeypatch.setattr(mgmt.time, "monotonic", lambda: next(ticks))
    data = mgmt.capture(5, lambda _c: FakeMonitor(packets), clock=lambda: 1_800_000_000.0)
    assert data.startswith(b"btsnoop\x00") and struct.unpack(">II", data[8:16]) == (1, 2001)
    assert len(hcilog.records(data)) == 4
    assert hcilog.signs(data) == {"connect-request", "link-key-reply", "security-block", "auth-failure"}


def test_hcilog_ignores_rubbish() -> None:
    assert hcilog.signs(b"not a capture") == set()
    assert hcilog.records(b"btsnoop\x00" + bytes(8) + bytes(10)) == []


@pytest.mark.parametrize(
    ("hci", "outcome"),
    [
        ({"link-key-negative"}, "O4"),
        ({"connect-request", "security-block", "encrypted"}, "O3"),
        ({"connect-request", "auth-failure"}, "O2"),
        (set(), "O1"),
    ],
)
def test_classify_with_a_capture(hci: set[str], outcome: str) -> None:
    bond = {"Paired": True, "Bonded": True, "UUIDs": 3}
    assert reconnect.classify(bond, [], hci=hci)["outcome"] == outcome


# The helper's interface


class FakeOpener:
    def __init__(self) -> None:
        self.fake = FakeMgmt()

    def __call__(self, _channel: int) -> FakeMgmt:
        return self.fake


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_helper(tmp_path: Any, **kwargs: Any) -> tuple[server.Helper, FakeOpener, Clock]:
    opener, clock = FakeOpener(), Clock()
    helper = server.Helper(
        "0.41.0",
        1000,
        str(tmp_path / "helper" / "state.json"),
        FakeSystemd([]),
        opener=opener,
        bt_root=bt_root(tmp_path),
        clock=clock,
        **kwargs,
    )
    return helper, opener, clock


def req(helper: server.Helper, job: str, **args: Any) -> dict[str, Any]:
    return helper.handle({"token": helper.token, "version": "0.41.0", "job": job, "args": args})


def test_helper_refuses_bad_tokens_versions_and_jobs(tmp_path: Any) -> None:
    helper, _o, _c = make_helper(tmp_path)
    with pytest.raises(server.Refused):
        helper.handle({"token": "wrong", "version": "0.41.0", "job": "ping"})
    assert helper.handle({"token": helper.token, "version": "0.40.0", "job": "ping"}) == {
        "ok": False,
        "error": "version",
        "helper": "0.41.0",
    }
    with pytest.raises(server.Refused):
        req(helper, "shell", command="id")
    assert req(helper, "ping")["version"] == "0.41.0"


def test_helper_ssp_off_needs_a_lease_and_expires(tmp_path: Any) -> None:
    helper, opener, clock = make_helper(tmp_path)
    assert req(helper, "ssp.set", index=0, on=False)["ok"] is False  # no lease
    assert req(helper, "ssp.set", index=0, on=False, lease=600)["ok"] is False  # too long
    assert req(helper, "ssp.set", index=0, on=False, lease=120)["ok"] is True
    assert opener.fake.ssp is False and helper._off() == [0]
    clock.now += 60
    helper.tick()
    assert opener.fake.ssp is False
    assert req(helper, "ssp.renew", lease=120)["ok"]
    clock.now += 121
    helper.tick()
    assert opener.fake.ssp is True and helper._off() == []


def test_helper_restores_ssp_after_a_restart_and_on_release(tmp_path: Any) -> None:
    helper, opener, _clock = make_helper(tmp_path)
    req(helper, "ssp.set", index=0, on=False, lease=120)
    again = server.Helper("0.41.0", 1000, helper.state_path, FakeSystemd([]), opener=opener)
    again.restore_ssp("helper started")
    assert opener.fake.ssp is True and again._off() == []
    req(helper, "ssp.set", index=0, on=False, lease=120)
    assert req(helper, "ssp.release")["ok"] and opener.fake.ssp is True


def test_helper_bt_jobs_validate_their_arguments(tmp_path: Any) -> None:
    helper, _o, _c = make_helper(tmp_path)
    assert req(helper, "bt.state", adapter=ADAPTER, device=CLONE)["linkKey"] is True
    assert req(helper, "bt.install", adapter=ADAPTER, device=CLONE, key="00", type=4)["ok"] is False
    assert req(helper, "bt.install", adapter=ADAPTER, device=CLONE, key=KEY.hex(), type="4")["ok"] is False
    assert req(helper, "bt.install", adapter="../x", device=CLONE, key=KEY.hex(), type=4)["ok"] is False
    assert req(helper, "bt.install", adapter=ADAPTER, device=CLONE, key=KEY.hex(), type=4)["ok"] is True


class FakeConn:
    def __init__(self, request: bytes) -> None:
        self.inbox = request
        self.sent = b""
        self.closed = False

    def settimeout(self, _t: float) -> None:
        pass

    def recv(self, size: int) -> bytes:
        chunk, self.inbox = self.inbox[:size], self.inbox[size:]
        return chunk

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def close(self) -> None:
        self.closed = True


def frame(payload: Any) -> bytes:
    data = json.dumps(payload).encode()
    return struct.pack(">I", len(data)) + data


def unframe(data: bytes) -> dict[str, Any]:
    (length,) = struct.unpack(">I", data[:4])
    found: dict[str, Any] = json.loads(data[4 : 4 + length])
    return found


def test_serve_one_checks_the_peer_and_size(tmp_path: Any) -> None:
    helper, _o, _c = make_helper(tmp_path)
    ok = {"token": helper.token, "version": "0.41.0", "job": "ping"}
    conn = FakeConn(frame(ok))
    server.serve_one(helper, conn, lambda _c: False)
    assert unframe(conn.sent) == {"ok": False, "error": "not authorised"} and conn.closed
    conn = FakeConn(frame(ok))
    server.serve_one(helper, conn, lambda _c: True)
    assert unframe(conn.sent)["version"] == "0.41.0"
    big = {**ok, "args": {"padding": "x" * server.MAX_REQUEST}}  # valid, but too large
    conn = FakeConn(frame(big))
    server.serve_one(helper, conn, lambda _c: True)
    assert unframe(conn.sent) == {"ok": False, "error": "request too large"}


def test_peer_allowed_needs_the_user_and_the_same_executable(monkeypatch: Any) -> None:
    class Sock:
        def __init__(self, uid: int) -> None:
            self.uid = uid

        def getsockopt(self, *_args: Any) -> bytes:
            return struct.pack("3i", 4242, self.uid, 1000)

    exes = {
        "/proc/4242/exe": "/home/user/homebrew/services/PluginLoader",
        "/proc/self/exe": "/home/user/homebrew/services/PluginLoader",
    }
    monkeypatch.setattr(server.os.path, "realpath", lambda p: exes.get(p.replace("\\", "/"), p))
    assert server.peer_allowed(Sock(1000), 1000) is True
    assert server.peer_allowed(Sock(1001), 1000) is False
    exes["/proc/4242/exe"] = "/usr/bin/python3"
    assert server.peer_allowed(Sock(1000), 1000) is False


# Keepsake's client


class ClientSock:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = frame(reply)
        self.sent = b""

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        chunk, self.reply = self.reply[:size], self.reply[size:]
        return chunk

    def close(self) -> None:
        pass


def client(tmp_path: Any, reply: dict[str, Any] | None, token: bool = True) -> tuple[HelperClient, list[ClientSock]]:
    run = tmp_path / "run"
    run.mkdir(parents=True, exist_ok=True)
    if token:
        (run / "token").write_text("t" * 64)
        (run / "helper.sock").write_text("")
    socks: list[ClientSock] = []

    def connect(_path: str, _timeout: float) -> ClientSock:
        if reply is None:
            raise ConnectionRefusedError
        socks.append(ClientSock(reply))
        return socks[-1]

    return HelperClient("0.41.0", str(run), connect), socks


def test_client_sends_token_and_version(tmp_path: Any) -> None:
    c, socks = client(tmp_path, {"ok": True, "version": "0.41.0", "sspOff": []})
    assert c.status() == {"installed": True, "ready": True, "version": "0.41.0", "sspOff": []}
    sent = unframe(socks[0].sent)
    assert sent == {"token": "t" * 64, "version": "0.41.0", "job": "ping", "args": {}}


def test_client_errors(tmp_path: Any) -> None:
    c, _ = client(tmp_path, {"ok": False, "error": "version", "helper": "0.40.0"})
    with pytest.raises(HelperVersion):
        c.call("ping")
    assert c.status()["problem"] == "version"
    c, _ = client(tmp_path, {"ok": False, "error": "bad length"})
    with pytest.raises(HelperError, match="bad length"):
        c.call("bt.state")
    c, _ = client(tmp_path / "x", None, token=False)
    with pytest.raises(HelperMissing):
        c.call("ping")
    assert c.status() == {"installed": False, "ready": False, "problem": "not installed"}


# The SSP gate


class FakeHelper:
    def __init__(self, refuse_powered: bool = False) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.refuse_powered = refuse_powered

    def ssp_set(self, index: int, on: bool, lease: float = 0.0, power_cycle: bool = False) -> dict[str, Any]:
        self.calls.append(("set", (index, on, lease, power_cycle)))
        if not on and self.refuse_powered and not power_cycle:
            return {"ok": False, "needsPowerCycle": True}
        return {"ok": True, "ssp": on}

    def ssp_renew(self, lease: float) -> dict[str, Any]:
        self.calls.append(("renew", lease))
        return {}

    def ssp_release(self) -> dict[str, Any]:
        self.calls.append(("release", None))
        return {}


def test_gate_off_when_idle_on_while_discovering_or_armed() -> None:
    fake, clock = FakeHelper(), Clock()
    gate = SspGate(fake, "/org/bluez/hci0", clock=clock)  # type: ignore[arg-type]
    assert gate.apply(0) == "off"
    assert fake.calls[-1] == ("set", (0, False, 120.0, False))
    gate.discovering = True
    assert gate.apply(0) == "on"
    gate.discovering = False
    gate.arm(60)
    assert gate.wanted() is True
    clock.now += 61
    assert gate.wanted() is False


def test_gate_power_cycles_only_with_nothing_connected_or_consent() -> None:
    fake = FakeHelper(refuse_powered=True)
    gate = SspGate(fake, "/org/bluez/hci0", clock=Clock())  # type: ignore[arg-type]
    assert gate.apply(2) == "needs-confirm"
    assert all(not c[1][3] for c in fake.calls)
    assert gate.apply(2, confirmed=True) == "off"
    assert fake.calls[-1][1][3] is True
    assert gate.apply(0) == "off"


def test_gate_reacts_to_bluetoothd_restarts_and_discovery() -> None:
    gate = SspGate(FakeHelper(), "/org/bluez/hci0", clock=Clock())  # type: ignore[arg-type]
    restart = {"type": 4, "member": "NameOwnerChanged", "body": ["org.bluez", "", ":1.99"]}
    gone = {"type": 4, "member": "NameOwnerChanged", "body": ["org.bluez", ":1.5", ""]}
    discovering = {
        "type": 4,
        "member": "PropertiesChanged",
        "path": "/org/bluez/hci0",
        "body": ["org.bluez.Adapter1", {"Discovering": ("b", True)}, []],
    }
    other = {
        "type": 4,
        "member": "PropertiesChanged",
        "path": "/org/bluez/hci1",
        "body": ["org.bluez.Adapter1", {"Discovering": ("b", True)}, []],
    }
    assert gate.handle(restart) is True
    assert gate.handle(gone) is False
    assert gate.handle(other) is False and gate.discovering is False
    assert gate.handle(discovering) is True and gate.discovering is True


def test_gate_renews_and_releases() -> None:
    fake, clock = FakeHelper(), Clock()
    gate = SspGate(fake, "/org/bluez/hci0", clock=clock)  # type: ignore[arg-type]
    gate.apply(0)
    assert gate.renew_due() is False
    clock.now += 31
    assert gate.renew_due() is True
    gate.renew()
    gate.stop()
    assert ("release", None) in fake.calls and gate.state == "on"


# Cable pairing through the service


class PairHelper:
    """A helper with a DS4 on USB: records writes, and can refuse to take the pairing."""

    def __init__(self, controller: str = CLONE, takes: bool = True, record: bool = True) -> None:
        self.controller = controller
        self.host: str | None = "0A:0B:0C:0D:0E:0F"
        self.takes = takes
        self.record = record
        self.sets: list[bytes] = []
        self.installs: list[tuple[str, str, bytes, int]] = []

    def installed(self) -> bool:
        return True

    def status(self) -> dict[str, Any]:
        return {"installed": True, "ready": True, "version": "0.41.0"}

    def get_feature(self, _node: str, report: int, length: int) -> bytes:
        def le(mac: str) -> bytes:
            return bytes(reversed(bytes.fromhex(mac.replace(":", ""))))

        return bytes([0x12]) + le(self.controller) + bytes(3) + (le(self.host) if self.host else bytes(6))

    def set_feature(self, _node: str, data: bytes) -> None:
        self.sets.append(data)
        if data[0] == 0x13 and self.takes:
            self.host = ":".join(f"{b:02X}" for b in reversed(data[1:7]))

    def bt_state(self, _a: str, _m: str) -> dict[str, Any]:
        return {"record": self.record, "services": self.record, "linkKey": True, "backups": 0}

    def bt_install(self, adapter: str, device: str, key: bytes, key_type: int) -> dict[str, Any]:
        self.installs.append((adapter, device, key, key_type))
        return {"backup": "info.keepsake-x"}


def pair_service(tmp_path: Any, helper: PairHelper, busy: str | None = None) -> ReconnectService:
    folder = tmp_path / "sys" / "class" / "hidraw" / "hidraw0" / "device"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "uevent").write_text("HID_ID=0003:0000054C:000009CC\nHID_UNIQ=\n")
    svc = ReconnectService(
        str(tmp_path / "settings"),
        str(tmp_path / "sys"),
        "/dev",
        connect=lambda: (_ for _ in ()).throw(OSError()),
        journal=lambda since: [],
        helper=helper,  # type: ignore[arg-type]
        busy=lambda: busy,
    )
    svc.rules.enable(ADAPTER, CLONE)
    return svc


def test_cable_pair_writes_controller_then_this_handheld(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr("keepsake.device.reconnect_service.time.sleep", lambda _s: None)
    helper = PairHelper()
    found = asyncio.run(pair_service(tmp_path, helper).cable_pair(ADAPTER, CLONE))
    assert found["state"] == "paired" and found["backup"] == "info.keepsake-x"
    pairing, commit = helper.sets
    assert pairing[0] == 0x13 and commit == bytes([0x14, 0x02]) + bytes(15)
    (adapter, device, key, key_type) = helper.installs[0]
    assert (adapter, device, key_type) == (ADAPTER, CLONE, 4) and key == pairing[7:23]


def test_cable_pair_reversed_order(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr("keepsake.device.reconnect_service.time.sleep", lambda _s: None)
    helper = PairHelper()
    asyncio.run(pair_service(tmp_path, helper).cable_pair(ADAPTER, CLONE, "reversed"))
    assert helper.installs[0][2] == bytes(reversed(helper.sets[0][7:23]))


@pytest.mark.parametrize(
    ("helper", "busy", "message"),
    [
        (PairHelper(controller=GENUINE), None, "different one"),
        (PairHelper(takes=False), None, "did not take"),
        (PairHelper(record=False), None, "services"),
        (PairHelper(), "a game is running", "not now"),
    ],
)
def test_cable_pair_refusals_never_touch_this_handheld(
    tmp_path: Any, helper: PairHelper, busy: str | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        asyncio.run(pair_service(tmp_path, helper, busy).cable_pair(ADAPTER, CLONE))
    assert helper.installs == []
    if message in ("different one", "services", "not now"):
        assert helper.sets == []


def test_cable_pair_dry_run_and_unhelped(tmp_path: Any) -> None:
    helper = PairHelper()
    svc = pair_service(tmp_path, helper)
    svc.rules.set_dry_run(True)
    assert asyncio.run(svc.cable_pair(ADAPTER, CLONE))["state"] == "dry-run"
    assert helper.sets == [] and helper.installs == []
    with pytest.raises(ValueError):
        asyncio.run(svc.cable_pair(ADAPTER, GENUINE))


def test_ssp_gate_needs_the_confirmation(tmp_path: Any) -> None:
    svc = pair_service(tmp_path, PairHelper())
    with pytest.raises(ValueError, match="confirm"):
        asyncio.run(svc.set_ssp_gate(True, ADAPTER, "yes"))
    assert svc.rules.ssp_gate() is None


# Packaging, the updater and the vendored D-Bus client


def test_helper_dbus_is_a_copy_of_keepsakes() -> None:
    with open(os.path.join(ROOT, "py_modules", "keepsake", "desktop", "dbus.py"), "rb") as a:
        with open(os.path.join(ROOT, "helper", "py_modules", "keepsake_helper", "dbus.py"), "rb") as b:
            assert a.read() == b.read()


def test_helper_zip_is_version_locked_and_root_flagged(tmp_path: Any) -> None:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import package

    path = package.build_helper(str(tmp_path))
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        version = archive.read("keepsake-helper/VERSION").decode().strip()
        meta = json.loads(archive.read("keepsake-helper/package.json"))
        plugin = json.loads(archive.read("keepsake-helper/plugin.json"))
    assert version == package.version() == meta["version"]
    assert plugin["flags"] == ["root"] and plugin["name"] == "Keepsake Helper"
    assert "keepsake-helper/py_modules/keepsake_helper/server.py" in names
    assert not any("test" in n or n.endswith(".pyc") for n in names)
    with open(os.path.join(ROOT, "plugin.json"), encoding="utf-8") as handle:
        assert "root" not in json.load(handle)["flags"]  # Keepsake itself never runs as root (P8)


def test_prepare_helper_needs_a_signed_release() -> None:
    from keepsake import update

    release = {
        "tag_name": "v0.41.0",
        "assets": [
            {
                "name": n,
                "browser_download_url": f"https://github.com/breakmylegs/keepsake/releases/download/v0.41.0/{n}",
            }
            for n in ("Keepsake-v0.41.0.zip", "Keepsake-helper-v0.41.0.zip", "SHA256SUMS")
        ],
    }
    parsed = update.parse_releases([release])[0]
    assert parsed.helper_url and parsed.helper_url.endswith("Keepsake-helper-v0.41.0.zip")

    class U(update.Updater):
        def _state(self) -> dict[str, Any]:
            return {"releases": [release]}

    unsigned = U.__new__(U)
    unsigned.public_key = ""
    assert unsigned.prepare_helper("v0.41.0", False) == {"ok": False, "reason": "unsigned-release"}
    assert unsigned.prepare_helper("v0.40.0", False) == {"ok": False, "reason": "unknown-release"}
