"""Replication 17b (ADR-0056): mDNS discovery, addresses, Wake-on-LAN, and the module in the app."""

import asyncio
import socket
import struct

import pytest

from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths
from keepsake.replication import discovery, link, netinfo, service
from keepsake.settings import SettingsError, SettingsStore

ID_A = "device-aaaa-0001"
ID_B = "11111111-2222-3333-4444-555555555555"

needs_psk = pytest.mark.skipif(not link.available(), reason="this OpenSSL has no TLS-PSK")


# mDNS messages


def test_an_answer_round_trips_to_a_found_device():
    packet = discovery.build_answer(7, ID_B, "Test handheld\x00 B", 47110)
    assert struct.unpack(">H", packet[:2])[0] == 7
    device = discovery.found_device(packet, "192.168.1.30")
    assert device == {"id": ID_B, "name": "Test handheld B", "address": "192.168.1.30", "port": 47110}


def test_only_our_own_query_is_answered():
    assert discovery.asks_for_us(discovery.build_query(42)) == 42
    header = struct.pack(">HHHHHH", 1, 0, 1, 0, 0, 0)
    other = header + discovery.encode_name("_http._tcp.local.") + struct.pack(">HH", 12, 1)
    assert discovery.asks_for_us(other) is None
    assert discovery.asks_for_us(discovery.build_answer(0, ID_B, "x", 1)) is None  # answers are not questions
    any_type = discovery.build_query(3)[:-4] + struct.pack(">HH", discovery.TYPE_ANY, 1)
    assert discovery.asks_for_us(any_type) == 3


def test_compressed_names_are_read_and_loops_refused():
    # A question whose name points back at an earlier copy of the service name.
    header = struct.pack(">HHHHHH", 5, 0, 2, 0, 0, 0)
    first = discovery.encode_name(discovery.SERVICE) + struct.pack(">HH", 1, 1)
    pointer = b"\xc0\x0c" + struct.pack(">HH", 12, 1)
    assert discovery.asks_for_us(header + first + pointer) == 5
    looping = struct.pack(">HHHHHH", 5, 0, 1, 0, 0, 0) + b"\xc0\x0c" + struct.pack(">HH", 12, 1)
    assert discovery.asks_for_us(looping) is None


@pytest.mark.parametrize(
    "packet",
    [
        b"",
        b"\x00" * 11,
        struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\x05abc",  # truncated name
        struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 0) + discovery.encode_name("a.local.") + b"\x00\x10",
    ],
)
def test_broken_packets_find_nothing(packet):
    assert discovery.found_device(packet, "192.168.1.30") is None
    assert discovery.asks_for_us(packet) is None


def test_answers_without_a_valid_identity_or_version_are_ignored():
    good = discovery.build_answer(0, ID_B, "x", 47110)
    assert discovery.found_device(good.replace(b"v=1", b"v=9"), "h") is None
    assert discovery.found_device(discovery.build_answer(0, "bad id!", "x", 47110), "h") is None
    assert discovery.found_device(discovery.build_answer(0, ID_B, "x", 0), "h") is None


class FakeTransport:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))


def test_the_responder_answers_directly_or_by_multicast_at_most_once_a_second():
    now = [10.0]
    responder = discovery.Responder(ID_A, lambda: "A", 47110, clock=lambda: now[0])
    transport = FakeTransport()
    responder.connection_made(transport)
    query = discovery.build_query(9)
    responder.datagram_received(query, ("192.168.1.40", 50000))  # a one-shot query: answered to its port
    responder.datagram_received(query, ("192.168.1.40", 5353))
    responder.datagram_received(query, ("192.168.1.41", 5353))  # within a second: not again
    now[0] += 1.5
    responder.datagram_received(query, ("192.168.1.41", 5353))
    responder.datagram_received(b"junk", ("192.168.1.42", 5353))
    targets = [addr for _, addr in transport.sent]
    assert targets == [("192.168.1.40", 50000), (discovery.GROUP, 5353), (discovery.GROUP, 5353)]
    assert struct.unpack(">H", transport.sent[0][0][:2])[0] == 9  # the direct answer echoes the query ID
    assert discovery.found_device(transport.sent[1][0], "x")["id"] == ID_A


def test_browsing_collects_answers_and_skips_itself():
    async def scenario():
        loop = asyncio.get_running_loop()
        answers = []

        class Fake(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                answers.append(discovery.asks_for_us(data))
                for device_id in (ID_A, ID_B):
                    self.transport.sendto(discovery.build_answer(0, device_id, "x", 47110), addr)

        transport, _ = await loop.create_datagram_endpoint(Fake, local_addr=("127.0.0.1", 0))
        port = transport.get_extra_info("sockname")[1]
        try:
            found = await discovery.browse(ID_A, 0.5, target=("127.0.0.1", port))
        finally:
            transport.close()
        return answers, found

    answers, found = asyncio.run(scenario())
    assert answers and answers[0] is not None
    assert [d["id"] for d in found] == [ID_B] and found[0]["address"] == "127.0.0.1"


# Addresses and Wake-on-LAN

FIB_TRIE = """Main:
  +-- 0.0.0.0/0 3 0 5
     |-- 0.0.0.0
        /0 universe UNICAST
     +-- 127.0.0.0/8 2 0 2
        |-- 127.0.0.1
           /32 host LOCAL
     |-- 192.168.1.0
        /24 link UNICAST
     |-- 192.168.1.20
        /32 host LOCAL
     |-- 100.101.102.103
        /32 host LOCAL
     |-- 81.2.69.160
        /32 host LOCAL
Local:
  +-- 0.0.0.0/0 3 0 5
"""
IF_INET6 = (
    "00000000000000000000000000000001 01 80 10 80       lo\n"
    "fd7a115ca1e0000000000000000000aa 05 80 00 80  tailscale0\n"
    "fe800000000000000000000000000001 02 40 20 80    wlan0\n"
)


def test_only_lan_and_vpn_addresses_are_offered(tmp_path):
    (tmp_path / "net").mkdir()
    (tmp_path / "net" / "fib_trie").write_text(FIB_TRIE)
    (tmp_path / "net" / "if_inet6").write_text(IF_INET6)
    addresses = netinfo.local_addresses(str(tmp_path))
    assert addresses == [
        {"address": "192.168.1.20", "kind": "lan"},
        {"address": "100.101.102.103", "kind": "overlay"},
        {"address": "fd7a:115c:a1e0::aa", "kind": "overlay"},
    ]
    assert netinfo.bind_hosts("", addresses) == ["192.168.1.20", "100.101.102.103", "fd7a:115c:a1e0::aa"]
    assert netinfo.bind_hosts("100.101.102.103", addresses) == ["100.101.102.103"]
    assert netinfo.bind_hosts("192.168.9.9", addresses) == []  # a chosen address that has gone binds nothing


def test_hardware_addresses_come_from_physical_adapters(tmp_path):
    net = tmp_path / "class" / "net"
    for name, mac, physical in (
        ("wlan0", "AA:BB:CC:DD:EE:01\n", True),
        ("eth0", "00:00:00:00:00:00\n", True),
        ("tailscale0", "aa:bb:cc:dd:ee:02\n", False),
        ("lo", "00:00:00:00:00:00\n", False),
    ):
        (net / name).mkdir(parents=True)
        (net / name / "address").write_text(mac)
        if physical:
            (net / name / "device").mkdir()
    assert netinfo.own_macs(str(tmp_path)) == ["aa:bb:cc:dd:ee:01"]


def test_a_magic_packet_is_six_ff_then_the_address_sixteen_times():
    packet = netinfo.magic_packet("aa:bb:cc:dd:ee:01")
    assert len(packet) == 102 and packet[:6] == b"\xff" * 6 and packet[6:12] == bytes.fromhex("aabbccddee01")
    assert packet[6:] == bytes.fromhex("aabbccddee01") * 16
    sent = []
    assert netinfo.wake(["aa:bb:cc:dd:ee:01", "not a mac", "AA:BB:CC:DD:EE:02"], send=lambda p, a: sent.append(a)) == 2
    assert sent == [("255.255.255.255", 9)] * 2
    assert netinfo.wake([], send=lambda p, a: sent.append(a)) == 0
    with pytest.raises(ValueError):
        netinfo.magic_packet("zz")


def test_firewall_advice_names_the_ports(tmp_path):
    (tmp_path / "123").mkdir()
    (tmp_path / "123" / "comm").write_text("firewalld\n")
    assert "Bazzite" in service.firewall_advice("linux", str(tmp_path))
    assert "TCP 47110 and UDP 5353" in service.firewall_advice("windows", str(tmp_path))
    assert "No firewall" in service.firewall_advice("linux", str(tmp_path / "none"))


def test_the_listening_address_setting(tmp_path):
    store = SettingsStore(str(tmp_path))
    assert store.get("replicationListener") is False and store.get("replicationAddress") == ""
    assert store.set("replicationAddress", " 192.168.1.20 ")["replicationAddress"] == "192.168.1.20"
    assert store.set("replicationAddress", "")["replicationAddress"] == ""
    for bad in ("not an address", "192.168.1.20:47110", 5):
        with pytest.raises(SettingsError):
            store.set("replicationAddress", bad)
    with pytest.raises(SettingsError):
        store.set("replicationListener", "yes")


# The module in the app


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    monkeypatch.setattr(netinfo, "local_addresses", lambda proc_root="/proc": [{"address": "127.0.0.1", "kind": "lan"}])

    async def no_responder(*args, **kwargs):
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(discovery, "start_responder", no_responder)
    apps = []

    def make(name):
        root = tmp_path / name
        paths = PluginPaths(*(str(root / n) for n in ("settings", "runtime", "logs", "plugin")))
        app = KeepsakeApp(paths, proc_root=str(root / "proc"), version="0.9.0", auto_refresh_manifest=False)
        app.replication_port = 0
        adapter = root / "sys" / "class" / "net" / "wlan0"
        (adapter / "device").mkdir(parents=True, exist_ok=True)
        (adapter / "address").write_text(f"aa:bb:cc:dd:ee:{len(apps) + 1:02x}\n")  # synthetic
        app.sys_root = str(root / "sys")
        apps.append(app)
        return app

    return make


@needs_psk
def test_two_apps_pair_through_their_callables(make_app, monkeypatch):
    async def scenario():
        a, b = make_app("a"), make_app("b")
        events = []

        async def emit(event, *args):
            events.append((event, args))

        b.emit = emit
        for app, name in ((a, "Test device A"), (b, "Test device B")):
            await app.start()
            await app.set_setting("deviceName", name)
            await app.set_module_enabled("replication", True)
        try:
            off = await b.replication_status()
            assert off["listener"]["on"] is False and off["available"] is True
            status = await b.replication_set_listener(True)
            assert b.settings.get("replicationListener") is True
            assert status["listener"]["addresses"] == ["127.0.0.1"]
            assert status["discovery"]["on"] is False and "automatically" in status["discovery"]["problem"]
            port = b.links.listener.bound_port
            started = await a.replication_pair(f"127.0.0.1:{port}")  # no window to open first (ADR-0070)
            for _ in range(250):
                theirs = [p for p in (await b.replication_status())["pairings"] if p["state"] == "request"]
                if theirs:
                    break
                await asyncio.sleep(0.02)
            assert theirs[0]["peerName"] == "Test device A" and theirs[0]["address"].startswith("127.0.0.1")
            requests = [args[0] for e, args in events if e == "keepsake_pair_request"]
            assert requests == [{"id": theirs[0]["id"], "name": "Test device A", "address": theirs[0]["address"]}]
            await b.replication_answer(theirs[0]["id"], True)  # Accept
            for _ in range(250):
                shown = [p for p in (await b.replication_status())["pairings"] if p["state"] == "show-code"]
                mine = [p for p in (await a.replication_status())["pairings"] if p["state"] == "enter-code"]
                if shown and mine:
                    break
                await asyncio.sleep(0.02)
            assert mine[0]["code"] is None and len(shown[0]["code"]) == 6
            await a.replication_enter_code(started["id"], shown[0]["code"])
            for _ in range(250):
                if (await a.replication_status())["peers"] and (await b.replication_status())["peers"]:
                    break
                await asyncio.sleep(0.02)
            peer = (await a.replication_status())["peers"][0]
            assert peer["name"] == "Test device B"
            check = await a.replication_check(peer["id"])
            assert check["ok"] is True
            assert peer["canWake"] is False  # learnt on the first connection, not at pairing
            peer = (await a.replication_status())["peers"][0]
            assert peer["canWake"] is True
            assert (await b.replication_status())["peers"][0]["canWake"] is True  # the listener learnt A's too
            woken = []
            monkeypatch.setattr(netinfo, "wake", lambda macs: woken.append(macs) or len(macs))
            assert await a.replication_wake(peer["id"]) == {"sent": 1}
            assert woken == [["aa:bb:cc:dd:ee:02"]]  # B's adapter, learnt from its hello
            await a.replication_remove(peer["id"])
            assert (await a.replication_status())["peers"] == []
            with pytest.raises(ValueError, match="not paired"):
                await a.replication_wake(peer["id"])
        finally:
            await a.stop()
            await b.stop()

    asyncio.run(scenario())


@needs_psk
def test_the_listener_comes_back_after_a_restart_only_if_it_was_on(make_app):
    async def scenario():
        app = make_app("a")
        await app.start()
        await app.set_module_enabled("replication", True)
        assert app.links.listener is None  # off by default (P17)
        await app.replication_set_listener(True)
        await app.stop()
        again = make_app("a")
        again.paths = app.paths
        await again.start()
        try:
            assert again.registry.running("replication") and again.links.listener is not None
            await again.replication_set_listener(False)
            assert again.links.listener is None and again.settings.get("replicationListener") is False
        finally:
            await again.stop()

    asyncio.run(scenario())


def test_calls_fail_plainly_while_the_module_is_off(make_app):
    async def scenario():
        app = make_app("a")
        await app.start()
        try:
            assert app.registry.running("replication") is True  # on by default since the strip (ADR-0098)
            await app.set_module_enabled("replication", False)
            with pytest.raises(ValueError, match="Replication is off"):
                await app.replication_status()
        finally:
            await app.stop()

    asyncio.run(scenario())


@needs_psk
def test_an_address_that_is_not_this_devices_is_refused(make_app):
    async def scenario():
        app = make_app("a")
        await app.start()
        await app.set_module_enabled("replication", True)
        try:
            with pytest.raises(ValueError, match="not one of this device"):
                await app.replication_set_address("192.168.77.77")
            status = await app.replication_set_address("127.0.0.1")
            assert status["addressChoice"] == "127.0.0.1"
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_health_reports_link_listener_and_firewall(tmp_path):
    store = service.PeerStore(str(tmp_path / "p.json"))
    links = service.Links(link.Identity(ID_A, "A"), store, "127.0.0.1", 0)
    checks = service.health_checks(links, "windows", str(tmp_path))
    ids = [c["id"] for c in checks]
    if link.available():
        assert ids == ["replication-link", "replication-listener", "replication-firewall", "replication-peers"]
        assert checks[1]["status"] == "info" and "Off" in checks[1]["detail"]
    else:
        assert ids == ["replication-link"] and checks[0]["status"] == "fail"


def test_no_responder_socket_is_made_until_asked(monkeypatch):
    made = []
    monkeypatch.setattr(socket, "socket", lambda *a, **k: made.append(a) or pytest.fail("a socket was made"))
    links = service.Links(link.Identity(ID_A, "A"), service.PeerStore("unused.json"), "127.0.0.1", 0, discovery=True)
    links.status()
    assert made == []


def test_responses_are_never_taken_for_questions_or_questions_for_answers():
    query = discovery.build_query(4)
    echoed = query[:2] + struct.pack(">H", 0x8400) + query[4:]  # a response that repeats our question
    assert discovery.asks_for_us(echoed) is None
    answer = discovery.build_answer(0, ID_B, "x", 47110)
    as_query = answer[:2] + struct.pack(">H", 0) + answer[4:]  # the same records without the response flag
    assert discovery.found_device(as_query, "h") is None


def test_no_listener_without_an_address_to_bind(tmp_path):
    links = service.Links(link.Identity(ID_A, "A"), service.PeerStore(str(tmp_path / "p.json")), lambda: [], 0)
    with pytest.raises(service.ReplicationError, match="no home network"):
        asyncio.run(links.set_listener(True))
    assert links.listener is None


@needs_psk
def test_discovery_answers_only_when_asked_to(tmp_path, monkeypatch):
    started = []

    async def fake_responder(device_id, name, port):
        started.append(port)
        return FakeTransport()

    FakeTransport.close = lambda self: None
    monkeypatch.setattr(discovery, "start_responder", fake_responder)

    async def scenario(with_discovery):
        links = service.Links(
            link.Identity(ID_A, "A"),
            service.PeerStore(str(tmp_path / "p.json")),
            "127.0.0.1",
            0,
            discovery=with_discovery,
        )
        status = await links.set_listener(True)
        await links.close()
        return status["discovery"]["on"]

    assert asyncio.run(scenario(False)) is False and started == []
    assert asyncio.run(scenario(True)) is True and len(started) == 1
