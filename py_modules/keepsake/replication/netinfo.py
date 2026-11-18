"""This device's addresses, the listener's bind choice, and Wake-on-LAN (slice 17b, ADR-0056).

The listener binds only to private LAN and VPN overlay addresses (ADR-0016): by default all of
them, or the one the user chose. Public and loopback addresses are never offered.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import uuid
from typing import Any

OVERLAY = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
MAX_MACS = 4
WAKE_PORT = 9


def kind(address: str) -> str:
    """ "lan", "overlay", "loopback", "link-local" or "public"."""
    ip = ipaddress.ip_address(address)
    if any(ip in network for network in OVERLAY):
        return "overlay"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_private:
        return "lan"
    return "public"


def _fib_trie(text: str) -> set[str]:
    """IPv4 addresses that are this host's own (``/32 host LOCAL``) in /proc/net/fib_trie."""
    found: set[str] = set()
    last = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|--") or stripped.startswith("+--"):
            last = stripped[3:].strip().split(" ")[0]
        elif "/32 host LOCAL" in stripped and last:
            found.add(last)
    return found


def _if_inet6(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if parts and len(parts[0]) == 32:
            found.add(str(ipaddress.ip_address(bytes.fromhex(parts[0]))))
    return found


def local_addresses(proc_root: str = "/proc") -> list[dict[str, str]]:
    """This device's LAN and overlay addresses, the only ones the listener may bind."""
    found: set[str] = set()
    for name, reader in (("net/fib_trie", _fib_trie), ("net/if_inet6", _if_inet6)):
        try:
            with open(os.path.join(proc_root, name), encoding="utf-8", errors="replace") as handle:
                found |= reader(handle.read())
        except OSError:
            pass
    if not found:  # Windows, or no /proc: the addresses the host name resolves to
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                found.add(str(info[4][0]).split("%")[0])
        except OSError:
            pass
    out = []
    for address in found:
        try:
            k = kind(address)
        except ValueError:
            continue
        if k in ("lan", "overlay"):
            out.append({"address": address, "kind": k})
    return sorted(out, key=lambda a: (a["kind"] != "lan", ":" in a["address"], a["address"]))


def bind_hosts(choice: str, addresses: list[dict[str, str]]) -> list[str]:
    """Where the listener binds: the chosen address if it is still here, or every LAN and overlay one."""
    available = [a["address"] for a in addresses]
    if choice:
        return [choice] if choice in available else []
    return available


def own_macs(sys_root: str = "/sys") -> list[str]:
    """Hardware addresses of this device's physical network adapters, for Wake-on-LAN."""
    base = os.path.join(sys_root, "class", "net")
    macs: list[str] = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        names = []
    for name in names:
        if not os.path.exists(os.path.join(base, name, "device")):
            continue  # virtual adapters (bridges, tunnels, VPNs) have no device
        try:
            with open(os.path.join(base, name, "address"), encoding="ascii") as handle:
                mac = handle.read().strip().lower()
        except OSError:
            continue
        if MAC.match(mac) and mac != "00:00:00:00:00:00":
            macs.append(mac)
    if not macs and not names:
        node = uuid.getnode()
        if not node & (1 << 40):  # the multicast bit marks a random number, not a real adapter
            macs.append(":".join(f"{(node >> s) & 0xFF:02x}" for s in range(40, -8, -8)))
    return macs[:MAX_MACS]


def clean_macs(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).lower() for v in values if MAC.match(str(v).lower())][:MAX_MACS]


def magic_packet(mac: str) -> bytes:
    if not MAC.match(mac):
        raise ValueError("not a hardware address")
    return b"\xff" * 6 + bytes.fromhex(mac.replace(":", "")) * 16


def wake(macs: list[str], send: Any = None) -> int:
    """Broadcast a magic packet for each address. Returns how many were sent."""
    packets = [magic_packet(m) for m in clean_macs(macs)]
    if not packets:
        return 0
    if send is None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for packet in packets:
                sock.sendto(packet, ("255.255.255.255", WAKE_PORT))
    else:
        for packet in packets:
            send(packet, ("255.255.255.255", WAKE_PORT))
    return len(packets)
