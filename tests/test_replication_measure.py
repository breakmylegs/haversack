"""The slice 16 measurement script (ADR-0045), run here over loopback with small sizes."""

import json
import os
import socket
import ssl
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import replication_measure as measure


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_hash_speed_is_measured():
    result = measure.measure_hash(0.01)
    assert result["test"] == "sha256" and result["bytes"] >= 10 * measure.MIB and result["MBps"] > 0


@pytest.mark.parametrize(
    "tls", [False, pytest.param(True, marks=pytest.mark.skipif(not getattr(ssl, "HAS_PSK", False), reason="no PSK"))]
)
def test_send_and_receive_over_loopback_uncompressed(tls, capsys):
    port = free_port()
    ready, stop = threading.Event(), threading.Event()
    server = threading.Thread(target=measure.serve, args=(port, tls, ready, stop), daemon=True)
    server.start()
    assert ready.wait(10)
    sent = measure.send("127.0.0.1", port, tls, 0.01, 256, 2)
    receives, out = [], ""
    for _ in range(100):  # the receiving threads print just after the sender closes
        out += capsys.readouterr().out
        receives = [json.loads(line) for line in out.splitlines() if '"receive"' in line]
        if len(receives) == 2:
            break
        time.sleep(0.05)
    stop.set()
    server.join(5)
    assert sent["streams"] == 2 and sent["bytes"] >= 10 * measure.MIB - 2 * 256 * 1024
    assert sent["compression"] == ["None"] and sent["tls"] is tls
    assert len(receives) == 2 and all(r["compression"] is None for r in receives)
    assert sum(r["bytes"] for r in receives) == sent["bytes"]
