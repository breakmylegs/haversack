"""Slice 16 measurements for Replication (ADR-0045). Standard library only; run on the devices.

    python3 replication_measure.py hash [--gib 2]
    python3 replication_measure.py serve [--port 47111] [--tls]
    python3 replication_measure.py send HOST [--port 47111] [--tls] [--gib 2] [--read-kib 4096] [--streams 1]

``serve`` runs on the receiving device and ``send`` on the other. They print JSON lines,
which are pasted into the slice 16 report. No compression is used anywhere, and TLS
uses TLS-PSK with a fixed test key: this is a measurement, not a secure channel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import ssl
import sys
import threading
import time
from typing import Any

MIB = 1024 * 1024
TEST_KEY = b"keepsake-slice16-measurement-key"  # not a secret: a measurement-only PSK


def contexts() -> tuple[ssl.SSLContext, ssl.SSLContext]:
    if not getattr(ssl, "HAS_PSK", False):
        raise SystemExit("this Python's OpenSSL has no TLS-PSK")
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    for context in (server, client):
        context.options |= ssl.OP_NO_COMPRESSION
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers("PSK-AES128-GCM-SHA256:PSK")
    client.check_hostname = False
    client.verify_mode = ssl.CERT_NONE
    server.set_psk_server_callback(lambda identity: TEST_KEY)
    client.set_psk_client_callback(lambda hint: ("measure", TEST_KEY))
    return server, client


def measure_hash(gib: float, block: int = 4 * MIB) -> dict[str, object]:
    data = os.urandom(block)
    total = int(gib * 1024) * MIB
    digest = hashlib.sha256()
    start = time.perf_counter()
    done = 0
    while done < total:
        digest.update(data)
        done += block
    seconds = time.perf_counter() - start
    return {"test": "sha256", "bytes": done, "seconds": round(seconds, 3), "MBps": round(done / MIB / seconds, 1)}


def _receive(conn: socket.socket, read: int, hashing: bool) -> tuple[int, str]:
    digest = hashlib.sha256() if hashing else None
    received = 0
    while True:
        chunk = conn.recv(read)
        if not chunk:
            break
        received += len(chunk)
        if digest is not None:
            digest.update(chunk)
    return received, digest.hexdigest() if digest else ""


def _serve_one(raw: socket.socket, address: tuple[str, int], server_ctx: ssl.SSLContext | None) -> None:
    try:
        conn = server_ctx.wrap_socket(raw, server_side=True) if server_ctx else raw
        with conn:
            line = conn.recv(256).split(b"\n", 1)[0]
            if not line:
                return  # the sender's round-trip probe: connect and close
            header = json.loads(line)
            conn.sendall(b"ok\n")
            start = time.perf_counter()
            received, digest = _receive(conn, header["read"], header["hash"])
            seconds = time.perf_counter() - start
            compression = conn.compression() if isinstance(conn, ssl.SSLSocket) else None
    except (OSError, ValueError, KeyError):
        return
    print(
        json.dumps(
            {
                "test": "receive",
                "from": address[0],
                "tls": server_ctx is not None,
                "compression": compression,
                "readKiB": header["read"] // 1024,
                "bytes": received,
                "seconds": round(seconds, 3),
                "MBps": round(received / MIB / max(seconds, 1e-9), 1),
                "sha256": digest[:16],
            }
        ),
        flush=True,
    )


def serve(port: int, tls: bool, ready: threading.Event | None = None, stop: threading.Event | None = None) -> None:
    """Accept until stopped, one thread per connection, so parallel streams really run in parallel."""
    server_ctx = contexts()[0] if tls else None
    with socket.create_server(("", port)) as listener:
        listener.settimeout(0.5)
        if ready is not None:
            ready.set()
        while stop is None or not stop.is_set():
            try:
                raw, address = listener.accept()
            except TimeoutError:
                continue
            raw.settimeout(None)
            threading.Thread(target=_serve_one, args=(raw, address, server_ctx), daemon=True).start()


def _send_one(host: str, port: int, tls: bool, total: int, read: int, results: list[dict[str, Any]]) -> None:
    client_ctx = contexts()[1] if tls else None
    raw = socket.create_connection((host, port), timeout=30)
    conn = client_ctx.wrap_socket(raw) if client_ctx else raw
    with conn:
        conn.sendall(json.dumps({"read": read, "hash": True}).encode() + b"\n")
        conn.recv(16)
        block = os.urandom(read)
        start = time.perf_counter()
        sent = 0
        while sent < total:
            conn.sendall(block)
            sent += read
        seconds = time.perf_counter() - start
        compression = conn.compression() if isinstance(conn, ssl.SSLSocket) else None
    results.append({"bytes": sent, "seconds": seconds, "compression": compression})


def send(host: str, port: int, tls: bool, gib: float, read_kib: int, streams: int) -> dict[str, object]:
    total = int(gib * 1024) * MIB // streams
    read = read_kib * 1024
    rtt_start = time.perf_counter()
    socket.create_connection((host, port), timeout=10).close()
    rtt_ms = (time.perf_counter() - rtt_start) * 1000
    results: list[dict[str, Any]] = []
    start = time.perf_counter()
    threads = [threading.Thread(target=_send_one, args=(host, port, tls, total, read, results)) for _ in range(streams)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    seconds = time.perf_counter() - start
    sent = sum(int(r["bytes"]) for r in results)
    return {
        "test": "send",
        "tls": tls,
        "readKiB": read_kib,
        "streams": streams,
        "connectMs": round(rtt_ms, 1),
        "bytes": sent,
        "seconds": round(seconds, 3),
        "MBps": round(sent / MIB / seconds, 1),
        "compression": sorted({str(r["compression"]) for r in results}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    hashing = sub.add_parser("hash")
    hashing.add_argument("--gib", type=float, default=2.0)
    serving = sub.add_parser("serve")
    serving.add_argument("--port", type=int, default=47111)
    serving.add_argument("--tls", action="store_true")
    sending = sub.add_parser("send")
    sending.add_argument("host")
    sending.add_argument("--port", type=int, default=47111)
    sending.add_argument("--tls", action="store_true")
    sending.add_argument("--gib", type=float, default=2.0)
    sending.add_argument("--read-kib", type=int, default=4096)
    sending.add_argument("--streams", type=int, default=1)
    options = parser.parse_args(argv)
    if options.command == "hash":
        print(json.dumps(measure_hash(options.gib)))
    elif options.command == "serve":
        print(json.dumps({"test": "serving", "port": options.port, "tls": options.tls}), flush=True)
        serve(options.port, options.tls)
    else:
        print(json.dumps(send(options.host, options.port, options.tls, options.gib, options.read_kib, options.streams)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
