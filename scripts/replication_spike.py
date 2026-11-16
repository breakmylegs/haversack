"""Replication spike measurement kit (v2 spec slice 16). Development tool, stdlib only.

Run on each handheld (copy over SSH, or ``python scripts/test_on_device.py`` for
the tests) and paste the JSON into ``docs/slices/16-report.md``:

    python3 replication_spike.py probe              # versions, TLS-PSK, system binaries
    python3 replication_spike.py bench --mb 256     # SHA-256 and TLS-PSK loopback throughput, CPU
    python3 replication_spike.py mdns               # can a user process join mDNS multicast?
    python3 replication_spike.py serve --bind <lan ip>          # on device A, prints a one-off key
    python3 replication_spike.py send <A's ip> --psk <key> --mb 1024   # on device B

``serve`` listens only while it runs, on the address given, for one transfer,
and only accepts a client holding the printed key (TLS 1.2 ECDHE-PSK, forward
secret). It is not part of the plugin (P17 applies to the plugin's listener).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import platform
import secrets
import shutil
import socket
import ssl
import struct
import sys
import threading
import time
from typing import Any

PORT = 47110
CIPHERS = "ECDHE-PSK-CHACHA20-POLY1305:ECDHE-PSK-AES256-CBC-SHA384:ECDHE-PSK-AES128-CBC-SHA256"
CHUNK = 4 * 1024 * 1024
BINARIES = ("openssl", "systemd-inhibit", "firewall-cmd", "udisksctl", "avahi-browse")


def has_psk() -> bool:
    return hasattr(ssl.SSLContext, "set_psk_client_callback") and bool(getattr(ssl, "HAS_PSK", True))


def os_release() -> dict[str, str]:
    out = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.strip().partition("=")
                if key in ("ID", "VERSION_ID", "PRETTY_NAME"):
                    out[key] = value.strip('"')
    except OSError:
        pass
    return out


def battery() -> dict[str, Any]:
    for folder in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        values = {}
        for name in ("energy_now", "charge_now", "capacity", "status", "power_now"):
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    values[name] = handle.read().strip()
            except OSError:
                pass
        if values:
            return values
    return {}


def probe() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "openssl": ssl.OPENSSL_VERSION,
        "tls13": ssl.HAS_TLSv1_3,
        "psk": has_psk(),
        "binaries": {name: shutil.which(name) for name in BINARIES},
        "os": os_release() or {"system": platform.system()},
        "cpus": os.cpu_count(),
        "battery": battery(),
    }


def server_context(psk: bytes) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers(CIPHERS)
    ctx.set_psk_server_callback(lambda identity: psk if identity == "keepsake-spike" else b"")
    return ctx


def client_context(psk: bytes) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # authentication is the pre-shared key
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers(CIPHERS)
    ctx.set_psk_client_callback(lambda hint: ("keepsake-spike", psk))
    return ctx


def recv_exact(conn: ssl.SSLSocket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        part = conn.recv(size - len(data))  # TLS sockets take no recv flags, so loop
        if not part:
            raise ConnectionError("the connection closed early")
        data += part
    return data


def receive(conn: ssl.SSLSocket) -> dict[str, Any]:
    size = struct.unpack("!Q", recv_exact(conn, 8))[0]
    digest = hashlib.sha256()
    got = 0
    start, cpu = time.perf_counter(), time.process_time()
    while got < size:
        data = conn.recv(min(CHUNK, size - got))
        if not data:
            break
        digest.update(data)
        got += len(data)
    seconds = time.perf_counter() - start
    conn.sendall(digest.digest())
    return {
        "bytes": got,
        "seconds": round(seconds, 3),
        "mb_per_s": round(got / 1e6 / seconds, 1) if seconds else None,
        "cpu_seconds": round(time.process_time() - cpu, 3),
        "sha256": digest.hexdigest(),
    }


def send_stream(conn: ssl.SSLSocket, total: int) -> dict[str, Any]:
    block = os.urandom(CHUNK)
    digest = hashlib.sha256()
    conn.sendall(struct.pack("!Q", total))
    start, cpu = time.perf_counter(), time.process_time()
    sent = 0
    while sent < total:
        part = block[: min(CHUNK, total - sent)]
        conn.sendall(part)
        digest.update(part)
        sent += len(part)
    echoed = recv_exact(conn, 32)
    seconds = time.perf_counter() - start
    return {
        "bytes": sent,
        "seconds": round(seconds, 3),
        "mb_per_s": round(sent / 1e6 / seconds, 1) if seconds else None,
        "cpu_seconds": round(time.process_time() - cpu, 3),
        "verified": echoed == digest.digest(),
    }


def serve(bind: str, port: int, psk: bytes, ready: threading.Event | None = None) -> dict[str, Any]:
    with socket.create_server((bind, port)) as listener:
        listener.settimeout(600)
        if ready:
            ready.set()
        raw, peer = listener.accept()
        with server_context(psk).wrap_socket(raw, server_side=True) as conn:
            result = receive(conn)
    return {"peer": peer[0], **result}


def send(host: str, port: int, psk: bytes, mb: int) -> dict[str, Any]:
    before = battery()
    with socket.create_connection((host, port), timeout=60) as raw:
        with client_context(psk).wrap_socket(raw) as conn:
            cipher = conn.cipher()
            result = send_stream(conn, mb * 1024 * 1024)
    return {"cipher": cipher[0] if cipher else None, "batteryBefore": before, "batteryAfter": battery(), **result}


def bench(mb: int) -> dict[str, Any]:
    data = os.urandom(min(mb, 64) * 1024 * 1024)
    rounds = max(1, mb // 64)
    start = time.perf_counter()
    for _ in range(rounds):
        hashlib.sha256(data).digest()
    sha_seconds = time.perf_counter() - start
    out: dict[str, Any] = {"sha256_mb_per_s": round(len(data) * rounds / 1e6 / sha_seconds, 1)}
    if has_psk():
        psk, ready, holder = secrets.token_bytes(32), threading.Event(), {}
        port = _free_port()
        thread = threading.Thread(target=lambda: holder.update(serve("127.0.0.1", port, psk, ready)))
        thread.start()
        ready.wait(10)
        out["tls_psk_loopback"] = send("127.0.0.1", port, psk, mb)
        thread.join(30)
        out["tls_psk_receiver"] = holder
    return out


def _free_port() -> int:
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        return int(probe_socket.getsockname()[1])


def mdns(seconds: float = 3.0) -> dict[str, Any]:
    """Join 224.0.0.251:5353, send a DNS-SD service enumeration query and count replies."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", 5353))
        # Multicast membership on the default interface, not a listening bind.
        default_interface = socket.inet_aton("0.0.0.0")  # noqa: S104
        sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton("224.0.0.251") + default_interface
        )
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    name = b"".join(bytes([len(p)]) + p for p in (b"_services", b"_dns-sd", b"_udp", b"local")) + b"\x00"
    query = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0) + name + struct.pack("!HH", 12, 1)
    replies = 0
    with sock:
        sock.sendto(query, ("224.0.0.251", 5353))
        sock.settimeout(0.5)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                data, _ = sock.recvfrom(9000)
            except TimeoutError:
                continue
            if len(data) >= 12 and data[2] & 0x80:
                replies += 1
    return {"ok": True, "replies": replies}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="replication_spike")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("probe")
    b = sub.add_parser("bench")
    b.add_argument("--mb", type=int, default=256)
    sub.add_parser("mdns")
    s = sub.add_parser("serve")
    s.add_argument("--bind", required=True, help="this device's LAN address (never 0.0.0.0)")
    s.add_argument("--port", type=int, default=PORT)
    c = sub.add_parser("send")
    c.add_argument("host")
    c.add_argument("--psk", required=True)
    c.add_argument("--port", type=int, default=PORT)
    c.add_argument("--mb", type=int, default=1024)
    args = parser.parse_args(argv)
    if args.command == "probe":
        result: dict[str, Any] = probe()
    elif args.command == "bench":
        result = bench(args.mb)
    elif args.command == "mdns":
        result = mdns()
    elif args.command == "serve":
        if args.bind in ("0.0.0.0", "", "::"):  # noqa: S104 - this refuses every-interface binds
            parser.error("give this device's LAN address, not every interface")
        key = secrets.token_hex(32)
        print(f"one-off key: {key}", flush=True)
        result = serve(args.bind, args.port, bytes.fromhex(key))
    else:
        result = send(args.host, args.port, bytes.fromhex(args.psk), args.mb)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
