"""Find Windows shares (SMB servers) on the local network, with no binary and no root (ADR-0066).

Three ways, each a few UDP packets from the Python standard library, run together for a couple
of seconds, only after the user presses "Find shares on my network":
- **mDNS** (RFC 6762): a ``PTR`` question for ``_smb._tcp.local`` to 224.0.0.251:5353, sent from
  an ordinary port so responders answer straight back (legacy unicast, section 6.7). NAS boxes,
  Macs and Linux servers with Avahi answer.
- **NetBIOS** (RFC 1002): a node status question for ``*`` broadcast to UDP 137. Windows PCs and
  Samba answer with their names; the file server name has suffix 0x20.
- **WS-Discovery**: a ``Probe`` for ``wsdp:Device pub:Computer`` to 239.255.255.250:3702. Windows
  10 and 11 answer even with NetBIOS off; their name is then asked by NetBIOS directly.

A server's address is always the source address of its answer, never an address written inside
it, and only local addresses are kept (the same list as ADR-0033). Nothing is sent to a server
until the user picks it; then the existing SMB code lists its shares (ADR-0034). Read only.
"""

from __future__ import annotations

import re
import secrets
import socket
import struct
import threading
import time
from collections.abc import Callable
from typing import Any

from .remote import host_is_private

MDNS = ("224.0.0.251", 5353)
WSD = ("239.255.255.250", 3702)
NETBIOS_PORT = 137
SMB_SERVICE = "_smb._tcp.local"
MAX_PACKET = 9000
MAX_SERVERS = 64
_NAME = re.compile(r"^[\w .()'&+-]{1,63}$")

SocketFactory = Callable[[], Any]


def _udp() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)  # never past the local network
    sock.bind(("", 0))
    return sock


def _clean_name(name: str) -> str | None:
    name = " ".join(str(name).split())
    return name if _NAME.match(name) else None


# mDNS


def _encode_name(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


def mdns_query() -> bytes:
    """One PTR question for the SMB service, asking for a unicast answer (the QU bit)."""
    return struct.pack("!6H", 0, 0, 1, 0, 0, 0) + _encode_name(SMB_SERVICE) + struct.pack("!2H", 12, 0x8001)


def _read_name(data: bytes, offset: int, depth: int = 0) -> tuple[str, int]:
    labels: list[str] = []
    while True:
        if offset >= len(data) or depth > 10:
            raise ValueError("bad name")
        length = data[offset]
        if length == 0:
            return ".".join(labels), offset + 1
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise ValueError("bad pointer")
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            rest, _ = _read_name(data, pointer, depth + 1)  # the depth limit stops loops
            return ".".join([*labels, rest] if rest else labels), offset + 2
        if length > 63 or offset + 1 + length > len(data):
            raise ValueError("bad label")
        labels.append(data[offset + 1 : offset + 1 + length].decode("utf-8", "replace"))
        offset += 1 + length


def parse_mdns(data: bytes) -> list[str]:
    """SMB service instance names in one mDNS answer (``Office NAS`` from ``Office NAS._smb._tcp.local``)."""
    if len(data) < 12:
        return []
    _id, flags, qd, an, ns, ar = struct.unpack("!6H", data[:12])
    if not flags & 0x8000:
        return []  # a question, not an answer
    offset = 12
    try:
        for _ in range(qd):
            _name, offset = _read_name(data, offset)
            offset += 4
        found = []
        for _ in range(an + ns + ar):
            owner, offset = _read_name(data, offset)
            if offset + 10 > len(data):
                break
            rtype, _cls, _ttl, length = struct.unpack("!HHIH", data[offset : offset + 10])
            offset += 10
            if rtype == 12 and owner.lower() == SMB_SERVICE:
                target, _ = _read_name(data, offset)
                suffix = "." + SMB_SERVICE
                if target.lower().endswith(suffix):
                    found.append(target[: -len(suffix)])
            offset += length
    except (ValueError, struct.error):
        return []
    return found


# NetBIOS


def netbios_query() -> bytes:
    """A node status question (NBSTAT) for the wildcard name ``*``."""
    raw = b"*" + b"\x00" * 15
    encoded = bytes(c for b in raw for c in (0x41 + (b >> 4), 0x41 + (b & 0x0F)))
    tid = secrets.randbits(16)
    return struct.pack("!6H", tid, 0, 1, 0, 0, 0) + b"\x20" + encoded + b"\x00" + struct.pack("!2H", 0x21, 1)


def parse_netbios(data: bytes) -> str | None:
    """The file server name in a node status answer: the unique name with suffix 0x20."""
    try:
        if len(data) < 12 or not struct.unpack("!H", data[2:4])[0] & 0x8000:
            return None
        offset = 12
        if data[offset] & 0xC0 == 0xC0:
            offset += 2
        else:
            _name, offset = _read_name(data, offset)
        rtype = struct.unpack("!H", data[offset : offset + 2])[0]
        if rtype != 0x21:
            return None
        offset += 10  # type, class, ttl, length
        count = data[offset]
        offset += 1
        fallback = None
        for i in range(count):
            entry = data[offset + 18 * i : offset + 18 * (i + 1)]
            if len(entry) < 18:
                break
            name = entry[:15].decode("ascii", "replace").strip()
            suffix, flags = entry[15], struct.unpack("!H", entry[16:18])[0]
            if flags & 0x8000:
                continue  # a group name, such as the workgroup
            if suffix == 0x20:
                return _clean_name(name)
            if suffix == 0x00 and fallback is None:
                fallback = _clean_name(name)
        return fallback
    except (IndexError, ValueError, struct.error):
        return None


# WS-Discovery

_WSD_PROBE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
    'xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
    'xmlns:wsdp="http://schemas.xmlsoap.org/ws/2006/02/devprof" '
    'xmlns:pub="http://schemas.microsoft.com/windows/pub/2005/07">'
    "<soap:Header><wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>"
    "<wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>"
    "<wsa:MessageID>urn:uuid:{uuid}</wsa:MessageID></soap:Header>"
    "<soap:Body><wsd:Probe><wsd:Types>wsdp:Device pub:Computer</wsd:Types></wsd:Probe></soap:Body>"
    "</soap:Envelope>"
)


def wsd_probe() -> bytes:
    raw = secrets.token_hex(16)
    uuid = f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return _WSD_PROBE.format(uuid=uuid).encode()


def parse_wsd(data: bytes) -> bool:
    """Whether a WS-Discovery answer is a computer's ProbeMatch (read with a pattern: no XML parser needed)."""
    text = data[:MAX_PACKET].decode("utf-8", "replace")
    return "ProbeMatch" in text and re.search(r"<[^>]*Types[^>]*>[^<]*\bComputer\b", text) is not None


# Running them


def _collect(
    send: Callable[[Any], None],
    parse: Callable[[bytes, str], None],
    seconds: float,
    sockets: SocketFactory,
) -> None:
    sock = sockets()
    try:
        send(sock)
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            sock.settimeout(left)
            try:
                data, source = sock.recvfrom(MAX_PACKET)
            except TimeoutError:
                break
            parse(data, str(source[0]))
    finally:
        sock.close()


def netbios_name(address: str, seconds: float = 0.6, sockets: SocketFactory = _udp) -> str | None:
    """Ask one server its name directly (for WS-Discovery answers)."""
    found: list[str] = []

    def parse(data: bytes, source: str) -> None:
        name = parse_netbios(data) if source == address else None
        if name:
            found.append(name)

    try:
        _collect(lambda s: s.sendto(netbios_query(), (address, NETBIOS_PORT)), parse, seconds, sockets)
    except OSError:
        return None
    return found[0] if found else None


def find_servers(
    seconds: float = 2.5,
    sockets: SocketFactory = _udp,
    is_local: Callable[[str], bool] = host_is_private,
    name_of: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """SMB servers answering on the local network: ``{"servers": [...], "methods": {...}}``.

    Each server is ``{name, address, url, via}``. Each method reports how many answered, or why
    it could not run (``"error: ..."``), so the Device check can say which ones work.
    """
    servers: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    lock = threading.Lock()
    name_of = name_of or (lambda address: netbios_name(address, sockets=sockets))

    def add(address: str, name: str | None, via: str) -> None:
        if not is_local(address):
            return
        with lock:
            if address not in servers and len(servers) >= MAX_SERVERS:
                return
            entry = servers.setdefault(address, {"address": address, "names": {}, "via": []})
            if name and via not in entry["names"]:
                entry["names"][via] = name
            if via not in entry["via"]:
                entry["via"].append(via)

    def mdns(data: bytes, source: str) -> None:
        for instance in parse_mdns(data):
            add(source, _clean_name(instance), "mdns")

    def netbios(data: bytes, source: str) -> None:
        name = parse_netbios(data)
        if name:
            add(source, name, "netbios")

    wsd_sources: list[str] = []

    def wsd(data: bytes, source: str) -> None:
        if parse_wsd(data) and source not in wsd_sources:
            wsd_sources.append(source)

    plans = {
        "mdns": (lambda s: s.sendto(mdns_query(), MDNS), mdns),
        "netbios": (lambda s: s.sendto(netbios_query(), ("255.255.255.255", NETBIOS_PORT)), netbios),
        "wsd": (lambda s: s.sendto(wsd_probe(), WSD), wsd),
    }

    def run(via: str) -> None:
        send, parse = plans[via]
        try:
            _collect(send, parse, seconds, sockets)
        except OSError as exc:
            with lock:
                errors[via] = f"error: {exc.strerror or type(exc).__name__}"

    threads = [threading.Thread(target=run, args=(via,), daemon=True) for via in plans]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(seconds + 2)
    for address in wsd_sources:
        add(address, name_of(address) if address not in servers else None, "wsd")
    out = []
    for entry in servers.values():
        names = entry["names"]
        name = names.get("mdns") or names.get("netbios") or names.get("wsd") or entry["address"]
        out.append(
            {"name": name, "address": entry["address"], "url": f"smb://{entry['address']}/", "via": entry["via"]}
        )
    out.sort(key=lambda s: (s["name"].casefold(), s["address"]))
    counts = {via: errors.get(via) or sum(via in s["via"] for s in out) for via in plans}
    return {"servers": out, "methods": counts}
