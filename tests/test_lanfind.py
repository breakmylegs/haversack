"""Find shares on my network (ADR-0066): mDNS, NetBIOS and WS-Discovery answers. Synthetic packets only."""

from __future__ import annotations

import asyncio
import struct

import pytest

from keepsake import devicechecks
from keepsake.installer import lanfind


def _name(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


def mdns_answer(instance: str) -> bytes:
    """A PTR answer for _smb._tcp.local pointing at '<instance>._smb._tcp.local' (with a compression pointer)."""
    owner = _name("_smb._tcp.local")
    rdata = bytes([len(instance)]) + instance.encode() + b"\xc0\x0c"  # the rest: the owner name at offset 12
    record = owner + struct.pack("!HHIH", 12, 1, 120, len(rdata)) + rdata
    return struct.pack("!6H", 0, 0x8400, 0, 1, 0, 0) + record


def netbios_answer(names: list[tuple[str, int, bool]]) -> bytes:
    """A node status answer: (name, suffix, group) entries."""
    encoded = b"\x20" + b"CK" + b"AA" * 15 + b"\x00"
    body = bytes([len(names)])
    for name, suffix, group in names:
        body += name.encode().ljust(15)[:15] + bytes([suffix]) + struct.pack("!H", 0x8000 if group else 0x0400)
    body += b"\x00" * 46  # statistics
    return struct.pack("!6H", 7, 0x8400, 0, 1, 0, 0) + encoded + struct.pack("!HHIH", 0x21, 1, 0, len(body)) + body


def wsd_answer(types: str = "wsdp:Device pub:Computer") -> bytes:
    return (
        '<?xml version="1.0"?><soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body>'
        f"<wsd:ProbeMatches><wsd:ProbeMatch><wsd:Types>{types}</wsd:Types>"
        "<wsd:XAddrs>http://203.0.113.9:5357/x</wsd:XAddrs></wsd:ProbeMatch></wsd:ProbeMatches>"
        "</soap:Body></soap:Envelope>"
    ).encode()


class FakeSocket:
    """Answers by where the question went: mDNS group, NetBIOS port, WS-Discovery group or one host."""

    def __init__(self, answers: dict, fail: set):
        self.answers, self.fail, self.queue, self.sent = answers, fail, [], []

    def sendto(self, data, dest):
        self.sent.append((data, dest))
        kind = "mdns" if dest == lanfind.MDNS else "wsd" if dest == lanfind.WSD else "netbios"
        if dest[1] == lanfind.NETBIOS_PORT and dest[0] != "255.255.255.255":
            kind = f"netbios:{dest[0]}"
        if kind.split(":")[0] in self.fail:
            raise OSError(101, "Network is unreachable")
        self.queue = list(self.answers.get(kind, []))

    def settimeout(self, _seconds):
        pass

    def recvfrom(self, _size):
        if not self.queue:
            raise TimeoutError
        return self.queue.pop(0)

    def close(self):
        pass


def factory(answers=None, fail=()):
    made = []

    def make():
        sock = FakeSocket(answers or {}, set(fail))
        made.append(sock)
        return sock

    make.made = made
    return make


ANSWERS = {
    "mdns": [
        (mdns_answer("Office NAS"), ("192.168.1.10", 5353)),
        (mdns_answer("Far Away"), ("8.8.8.8", 5353)),  # not a local address: dropped
        (b"\x00" * 5, ("192.168.1.11", 5353)),  # junk: ignored
    ],
    "netbios": [
        (
            netbios_answer([("WORKGROUP", 0x00, True), ("DESKPC", 0x00, False), ("DESKPC", 0x20, False)]),
            ("192.168.1.20", 137),
        ),
        (netbios_answer([("NASBOX", 0x20, False)]), ("192.168.1.10", 137)),
    ],
    "wsd": [
        (wsd_answer(), ("192.168.1.30", 3702)),
        (wsd_answer(), ("192.168.1.20", 3702)),
        (wsd_answer("wsdp:Device wprt:PrintDeviceType"), ("192.168.1.40", 3702)),  # a printer, not a computer
    ],
    "netbios:192.168.1.30": [
        (netbios_answer([("OTHER", 0x20, False)]), ("192.168.1.99", 137)),  # wrong source: ignored
        (netbios_answer([("WINPC", 0x20, False)]), ("192.168.1.30", 137)),
    ],
}


def test_find_servers_merges_the_three_ways_by_address():
    sockets = factory(ANSWERS)
    found = lanfind.find_servers(0.05, sockets)
    by_address = {s["address"]: s for s in found["servers"]}
    assert set(by_address) == {"192.168.1.10", "192.168.1.20", "192.168.1.30"}
    assert by_address["192.168.1.10"]["name"] == "Office NAS"  # mDNS's name wins over NetBIOS's
    assert sorted(by_address["192.168.1.10"]["via"]) == ["mdns", "netbios"]
    assert by_address["192.168.1.20"]["name"] == "DESKPC" and sorted(by_address["192.168.1.20"]["via"]) == [
        "netbios",
        "wsd",
    ]
    assert by_address["192.168.1.30"] == {
        "name": "WINPC",
        "address": "192.168.1.30",
        "url": "smb://192.168.1.30/",
        "via": ["wsd"],
    }
    assert found["methods"] == {"mdns": 1, "netbios": 2, "wsd": 2}
    sent = {dest for sock in sockets.made for _data, dest in sock.sent}
    assert sent == {lanfind.MDNS, ("255.255.255.255", 137), lanfind.WSD, ("192.168.1.30", 137)}  # nothing else


def test_sorted_by_name():
    names = [s["name"] for s in lanfind.find_servers(0.05, factory(ANSWERS))["servers"]]
    assert names == sorted(names, key=str.casefold)


def test_a_way_that_cannot_run_is_reported_and_the_others_still_work():
    found = lanfind.find_servers(0.05, factory(ANSWERS, fail={"netbios"}), name_of=lambda a: None)
    assert found["methods"]["netbios"] == "error: Network is unreachable"
    assert found["methods"]["mdns"] == 1
    assert {s["address"]: s["name"] for s in found["servers"]}["192.168.1.30"] == "192.168.1.30"  # no name: address


def test_only_local_addresses_are_kept():
    found = lanfind.find_servers(0.05, factory(ANSWERS), is_local=lambda a: a == "192.168.1.10", name_of=lambda a: None)
    assert [s["address"] for s in found["servers"]] == ["192.168.1.10"]


def test_queries_are_well_formed():
    query = lanfind.mdns_query()
    assert query[:12] == struct.pack("!6H", 0, 0, 1, 0, 0, 0)
    assert _name("_smb._tcp.local") in query and query.endswith(struct.pack("!2H", 12, 0x8001))
    nb = lanfind.netbios_query()
    assert nb[12:46] == b"\x20CK" + b"AA" * 15 + b"\x00" and nb.endswith(struct.pack("!2H", 0x21, 1))
    probe = lanfind.wsd_probe().decode()
    assert "<wsd:Probe>" in probe and "pub:Computer" in probe and probe != lanfind.wsd_probe().decode()


def test_mdns_parsing_refuses_questions_junk_and_loops():
    assert lanfind.parse_mdns(mdns_answer("Office NAS")) == ["Office NAS"]
    question = lanfind.mdns_query()
    assert lanfind.parse_mdns(question) == []
    assert lanfind.parse_mdns(b"\x00\x00\x84\x00") == []
    looped = struct.pack("!6H", 0, 0x8400, 0, 1, 0, 0) + b"\xc0\x0c"  # a pointer to itself
    assert lanfind.parse_mdns(looped) == []
    other = mdns_answer("Office NAS").replace(b"_smb", b"_ipp")
    assert lanfind.parse_mdns(other) == []
    long_label = struct.pack("!6H", 0, 0x8400, 0, 1, 0, 0) + bytes([64]) + b"x" * 64 + b"\x00"
    assert lanfind.parse_mdns(long_label) == []


def test_netbios_parsing():
    assert lanfind.parse_netbios(netbios_answer([("WORKGROUP", 0x00, True), ("PC", 0x20, False)])) == "PC"
    assert lanfind.parse_netbios(netbios_answer([("WORKGROUP", 0x20, True), ("PC", 0x00, False)])) == "PC"
    assert lanfind.parse_netbios(netbios_answer([("WORKGROUP", 0x20, True)])) is None
    assert lanfind.parse_netbios(netbios_answer([("BAD<NAME>", 0x20, False)])) is None
    assert lanfind.parse_netbios(lanfind.netbios_query()) is None  # a question
    assert lanfind.parse_netbios(b"\x00" * 3) is None
    wrong_type = netbios_answer([("PC", 0x20, False)]).replace(
        struct.pack("!HHIH", 0x21, 1, 0, 1 + 18 + 46), b"\x00\x20" + b"\x00" * 8
    )
    assert lanfind.parse_netbios(wrong_type) is None


def test_wsd_parsing():
    assert lanfind.parse_wsd(wsd_answer()) is True
    assert lanfind.parse_wsd(wsd_answer("wsdp:Device wprt:PrintDeviceType")) is False
    assert lanfind.parse_wsd(lanfind.wsd_probe()) is False  # our own probe, echoed back


def test_netbios_name_only_from_that_server():
    assert lanfind.netbios_name("192.168.1.30", 0.05, factory(ANSWERS)) == "WINPC"
    assert lanfind.netbios_name("192.168.1.31", 0.05, factory(ANSWERS)) is None
    assert lanfind.netbios_name("192.168.1.30", 0.05, factory(ANSWERS, fail={"netbios"})) is None


@pytest.mark.parametrize(
    ("answers", "fail", "status"),
    [(ANSWERS, (), "pass"), ({}, (), "warn"), ({}, ("mdns", "netbios", "wsd"), "fail")],
)
def test_device_check(answers, fail, status):
    sockets = factory(answers, fail)
    ctx = devicechecks.Context(
        "", "", "", "", {}, "", probes={"smb-find": lambda: asyncio.to_thread(lanfind.find_servers, 0.05, sockets)}
    )
    outcome = asyncio.run(devicechecks.run("smb-find", ctx))
    assert outcome["status"] == status and outcome["title"] == "Find shares on my network"
    assert "DESKPC" not in outcome["found"] and "192.168" not in outcome["found"]  # no names or addresses
    if status == "pass":
        assert outcome["details"] == {"servers": 3, "mdns": 1, "netbios": 2, "wsd": 2}
    bare = asyncio.run(devicechecks.run("smb-find", devicechecks.Context("", "", "", "", {}, "")))
    assert bare["status"] == "skip"


def _record(owner: str, rtype: int, rdata: bytes, flags: int = 0x8400) -> bytes:
    return (
        struct.pack("!6H", 0, flags, 0, 1, 0, 0)
        + _name(owner)
        + struct.pack("!HHIH", rtype, 1, 120, len(rdata))
        + rdata
    )


def test_mdns_takes_only_smb_ptr_answers():
    good = _name("Office NAS._smb._tcp.local")
    assert lanfind.parse_mdns(_record("_smb._tcp.local", 12, good)) == ["Office NAS"]
    assert lanfind.parse_mdns(_record("_smb._tcp.local", 12, good, flags=0)) == []  # a question, not an answer
    assert lanfind.parse_mdns(_record("_smb._tcp.local", 16, good)) == []  # not a PTR record
    assert lanfind.parse_mdns(_record("_other._tcp.local", 12, good)) == []  # someone else's service
    assert lanfind.parse_mdns(_record("_smb._tcp.local", 12, _name("Weird.local"))) == []  # not one of ours
    long_instance = bytes([64]) + b"x" * 64 + _name("_smb._tcp.local")
    assert lanfind.parse_mdns(_record("_smb._tcp.local", 12, long_instance)) == []  # labels are at most 63


def test_netbios_needs_an_answer_with_a_file_server_or_workstation_name():
    answer = netbios_answer([("PC", 0x20, False)])
    question_flags = answer[:2] + b"\x00\x00" + answer[4:]
    assert lanfind.parse_netbios(question_flags) is None
    assert lanfind.parse_netbios(netbios_answer([("PC", 0x03, False)])) is None  # the messenger name only
