"""Finding paired and pairable devices on the LAN with mDNS (slice 17b, ADR-0056).

Keepsake answers DNS-SD queries for its own service type, ``_keepsake._tcp.local``, only
while the listener is on. Looking for devices sends one query from a temporary port, which
RFC 6762 section 6.7 answers directly to that port, so browsing never needs port 5353.

Each answer carries only what pairing needs: the protocol version, the random device ID,
the device name and the port. Nothing here is trusted: a found device still has to pass
pairing or its link key before anything is exchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import socket
import struct
import time
from collections.abc import Callable
from typing import Any

from .peers import DEVICE_ID, clean_name

GROUP = "224.0.0.251"
PORT = 5353
SERVICE = "_keepsake._tcp.local."
TYPE_A, TYPE_PTR, TYPE_TXT, TYPE_SRV, TYPE_ANY = 1, 12, 16, 33, 255
CLASS_IN = 1
TTL = 120
MAX_PACKET = 9000
MAX_NAME = 255
ANSWER_GAP = 1.0  # at most one multicast answer a second


class DiscoveryError(Exception):
    pass


def encode_name(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        raw = label.encode("utf-8")
        if not 0 < len(raw) < 64:
            raise DiscoveryError("a name label is empty or too long")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def decode_name(packet: bytes, offset: int) -> tuple[str, int]:
    """Read a name, following compression pointers. Returns (name, offset after it)."""
    labels: list[str] = []
    end = -1
    jumps = 0
    while True:
        if offset >= len(packet):
            raise DiscoveryError("truncated name")
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet) or jumps > 16:
                raise DiscoveryError("bad name pointer")
            if end < 0:
                end = offset + 2
            offset = ((length & 0x3F) << 8) | packet[offset + 1]
            jumps += 1
            continue
        if length & 0xC0:
            raise DiscoveryError("bad label")
        offset += 1
        if length == 0:
            break
        labels.append(packet[offset : offset + length].decode("utf-8", errors="replace"))
        offset += length
        if sum(len(x) + 1 for x in labels) > MAX_NAME:
            raise DiscoveryError("name too long")
    return ".".join(labels) + ".", (end if end >= 0 else offset)


def build_query(query_id: int = 0) -> bytes:
    header = struct.pack(">HHHHHH", query_id, 0, 1, 0, 0, 0)
    return header + encode_name(SERVICE) + struct.pack(">HH", TYPE_PTR, CLASS_IN)


def _record(name: str, rtype: int, data: bytes, flush: bool = False) -> bytes:
    rclass = CLASS_IN | (0x8000 if flush else 0)
    return encode_name(name) + struct.pack(">HHIH", rtype, rclass, TTL, len(data)) + data


def _txt(values: dict[str, str]) -> bytes:
    out = b""
    for key, value in values.items():
        item = f"{key}={value}".encode()[:255]
        out += bytes([len(item)]) + item
    return out


def instance_name(device_id: str) -> str:
    return f"Keepsake-{device_id.replace('-', '')[:12]}.{SERVICE}"


def build_answer(query_id: int, device_id: str, name: str, port: int) -> bytes:
    """PTR, SRV and TXT for this device. The address is the packet's own source."""
    instance = instance_name(device_id)
    host = f"{instance.split('.')[0]}.local."
    records = [
        _record(SERVICE, TYPE_PTR, encode_name(instance)),
        _record(instance, TYPE_SRV, struct.pack(">HHH", 0, 0, port) + encode_name(host), flush=True),
        _record(instance, TYPE_TXT, _txt({"v": "1", "id": device_id, "name": clean_name(name)}), flush=True),
    ]
    header = struct.pack(">HHHHHH", query_id, 0x8400, 0, len(records), 0, 0)
    return header + b"".join(records)


def parse(packet: bytes) -> dict[str, Any]:
    """Questions and answers of a DNS message, as far as discovery needs them."""
    if len(packet) < 12 or len(packet) > MAX_PACKET:
        raise DiscoveryError("not a DNS message")
    query_id, flags, qdcount, ancount, nscount, arcount = struct.unpack(">HHHHHH", packet[:12])
    offset = 12
    questions = []
    for _ in range(min(qdcount, 32)):
        name, offset = decode_name(packet, offset)
        if offset + 4 > len(packet):
            raise DiscoveryError("truncated question")
        qtype, _qclass = struct.unpack(">HH", packet[offset : offset + 4])
        offset += 4
        questions.append((name.lower(), qtype))
    records = []
    for _ in range(min(ancount + nscount + arcount, 64)):
        name, offset = decode_name(packet, offset)
        if offset + 10 > len(packet):
            raise DiscoveryError("truncated record")
        rtype, _rclass, _ttl, length = struct.unpack(">HHIH", packet[offset : offset + 10])
        offset += 10
        start, offset = offset, offset + length
        if offset > len(packet):
            raise DiscoveryError("truncated record data")
        records.append((name.lower(), rtype, start, length))
    return {"id": query_id, "response": bool(flags & 0x8000), "questions": questions, "records": records}


def _read_txt(packet: bytes, start: int, length: int) -> dict[str, str]:
    values: dict[str, str] = {}
    offset, end = start, start + length
    while offset < end:
        size = packet[offset]
        item = packet[offset + 1 : offset + 1 + size].decode("utf-8", errors="replace")
        offset += 1 + size
        key, _, value = item.partition("=")
        values.setdefault(key.lower(), value)
    return values


def found_device(packet: bytes, source: str) -> dict[str, Any] | None:
    """A Keepsake device from an answer, or None. The address is where the answer came from."""
    try:
        message = parse(packet)
    except DiscoveryError:
        return None
    if not message["response"]:
        return None
    port = 0
    txt: dict[str, str] = {}
    for name, rtype, start, length in message["records"]:
        if not name.endswith(SERVICE.lower()):
            continue
        if rtype == TYPE_SRV and length >= 6:
            port = struct.unpack(">H", packet[start + 4 : start + 6])[0]
        elif rtype == TYPE_TXT:
            txt = _read_txt(packet, start, length)
    device_id = txt.get("id", "")
    if txt.get("v") != "1" or not DEVICE_ID.match(device_id) or not 0 < port < 65536:
        return None
    return {"id": device_id, "name": clean_name(txt.get("name")), "address": source, "port": port}


def asks_for_us(packet: bytes) -> int | None:
    """The query ID if the packet asks for Keepsake devices."""
    try:
        message = parse(packet)
    except DiscoveryError:
        return None
    if message["response"]:
        return None
    for name, qtype in message["questions"]:
        if name == SERVICE.lower() and qtype in (TYPE_PTR, TYPE_ANY):
            return int(message["id"])
    return None


class Responder(asyncio.DatagramProtocol):
    """Answers queries for Keepsake while the listener is on."""

    def __init__(self, device_id: str, name: Callable[[], str], port: int, clock: Callable[[], float] = time.monotonic):
        self.device_id = device_id
        self.name = name
        self.port = port
        self.clock = clock
        self.transport: asyncio.DatagramTransport | None = None
        self._last_multicast = -ANSWER_GAP

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        query_id = asks_for_us(data)
        if query_id is None or self.transport is None:
            return
        if addr[1] != PORT:
            # A one-shot query from a temporary port: answer it directly (RFC 6762 6.7).
            self.transport.sendto(build_answer(query_id, self.device_id, self.name(), self.port), addr)
            return
        now = self.clock()
        if now - self._last_multicast < ANSWER_GAP:
            return
        self._last_multicast = now
        self.transport.sendto(build_answer(0, self.device_id, self.name(), self.port), (GROUP, PORT))


def _responder_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # beside avahi-daemon
    sock.bind(("", PORT))
    membership = struct.pack("=4sl", socket.inet_aton(GROUP), socket.INADDR_ANY)  # on every interface
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    sock.setblocking(False)
    return sock


async def start_responder(device_id: str, name: Callable[[], str], port: int) -> asyncio.DatagramTransport:
    """Join the mDNS group. Raises OSError when the port or group is not available."""
    loop = asyncio.get_running_loop()
    sock = _responder_socket()
    transport, _ = await loop.create_datagram_endpoint(lambda: Responder(device_id, name, port), sock=sock)
    return transport


class _Collector(asyncio.DatagramProtocol):
    def __init__(self, own_id: str) -> None:
        self.own_id = own_id
        self.found: dict[str, dict[str, Any]] = {}

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        device = found_device(data, str(addr[0]))
        if device and device["id"] != self.own_id:
            self.found[device["id"]] = device


async def browse(own_id: str, seconds: float = 2.0, target: tuple[str, int] = (GROUP, PORT)) -> list[dict[str, Any]]:
    """Ask once for Keepsake devices and collect the answers for ``seconds``."""
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    sock.bind(("", 0))
    sock.setblocking(False)
    transport, protocol = await loop.create_datagram_endpoint(lambda: _Collector(own_id), sock=sock)
    try:
        transport.sendto(build_query(int.from_bytes(secrets.token_bytes(2), "big")), target)
        await asyncio.sleep(seconds)
    finally:
        transport.close()
    return sorted(protocol.found.values(), key=lambda d: d["name"])
