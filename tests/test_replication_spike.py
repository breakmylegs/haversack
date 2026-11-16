"""The slice 16 measurement kit works locally before it is run on the devices."""

import os
import secrets
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import replication_spike as spike

needs_psk = pytest.mark.skipif(not spike.has_psk(), reason="this Python has no TLS-PSK")


def test_probe_reports_what_the_adr_needs():
    result = spike.probe()
    assert {"python", "openssl", "tls13", "psk", "binaries", "os", "cpus", "battery"} <= set(result)
    assert set(result["binaries"]) == set(spike.BINARIES)


@needs_psk
def test_tls_psk_transfer_is_verified_end_to_end():
    psk = secrets.token_bytes(32)
    port, ready, holder = spike._free_port(), threading.Event(), {}
    thread = threading.Thread(target=lambda: holder.update(spike.serve("127.0.0.1", port, psk, ready)))
    thread.start()
    assert ready.wait(10)
    sent = spike.send("127.0.0.1", port, psk, 8)
    thread.join(30)
    assert sent["verified"] is True and sent["bytes"] == 8 * 1024 * 1024
    assert "PSK" in sent["cipher"]
    assert holder["bytes"] == sent["bytes"]


@needs_psk
def test_a_client_without_the_key_is_refused():
    port, ready, errors = spike._free_port(), threading.Event(), []

    def server():
        try:
            spike.serve("127.0.0.1", port, secrets.token_bytes(32), ready)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=server)
    thread.start()
    assert ready.wait(10)
    with pytest.raises(Exception):  # noqa: B017 - any TLS failure is the right outcome
        spike.send("127.0.0.1", port, secrets.token_bytes(32), 1)
    thread.join(30)
    assert errors


def test_serve_refuses_every_interface(capsys):
    with pytest.raises(SystemExit):
        spike.main(["serve", "--bind", "0.0.0.0"])


def test_bench_reports_hash_speed():
    result = spike.bench(8)
    assert result["sha256_mb_per_s"] > 0
    if spike.has_psk():
        assert result["tls_psk_loopback"]["verified"] is True
