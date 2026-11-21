"""The Replication protocol is frozen (slice 18b, ADR-0058, docs/protocol.md).

These values pin what goes on the wire. A change that breaks one of them breaks devices that
run another version, so it needs a new protocol version and an ADR, not an edited constant.
"""

import asyncio
import hashlib

from keepsake.replication import discovery, link
from keepsake.replication import manifest as mf
from keepsake.replication.source import Shares


def test_the_transport_constants():
    assert link.PROTOCOL == 1
    assert link.DEFAULT_PORT == 47110
    assert link.CIPHERS == "ECDHE-PSK-CHACHA20-POLY1305"
    # Pairing by code (ADR-0070) replaced pairing v1: its own identity and key, so old devices refuse it cleanly.
    assert link.PAIR_IDENTITY == "keepsake-pair/2" and link.PAIR_PROTOCOL == 2
    assert link.PAIR_KEY.hex() == "c5ff742ed08423d07bcea36ee85791db04618a2caac6f0a4cf78c36e16b72bca"
    assert link.CODE_BITS == 20 and link.REQUEST_LIMIT == 3 and link.REQUEST_WINDOW == 120.0
    assert link.LOCKOUT_FAILURES == 5 and link.LOCKOUT_SECONDS == 600.0
    assert link.MAX_FRAME == 64 * 1024 and link.MAX_BLOB == 64 * 1024 * 1024


def test_the_pairing_commitment():
    mac = link.commitment(b"\x02" * 16, b"\x01" * 12, "device-aaaa-0001", "device-bbbb-0002", "req", 0, 1)
    assert mac.hex() == "8995242a1aa009cdcf2f216f24c035e7d0c62c35afc6ee767ff46a1a5df29ae4"


def test_the_manifest_format_and_root_hash():
    digest = hashlib.sha256(b"abc").hexdigest()
    manifest = {
        "version": 1,
        "chunk": mf.CHUNK,
        "entries": [
            {"path": "bin", "type": "dir", "mode": 493, "mtime": 1600000000000000000},
            {
                "path": "bin/game.exe",
                "type": "file",
                "mode": 420,
                "mtime": 1600000000123456789,
                "size": 3,
                "sha256": digest,
                "chunks": [digest],
            },
            {"path": "bin/current", "type": "link", "mode": 511, "mtime": 0, "target": "game.exe"},
        ],
    }
    assert mf.VERSION == 1 and mf.CHUNK == 4 * 1024 * 1024
    assert mf.root_hash(manifest) == "4265afd1ab170b1b1d1c18317ff7a4529829e07835d73b0791af1f6f1dae19e2"


def test_the_frame_layout():
    class Writer:
        def __init__(self):
            self.data = b""

        def write(self, data):
            self.data += data

        async def drain(self):
            return None

    writer = Writer()
    asyncio.run(link.send_frame(writer, {"type": "ping"}))
    assert writer.data == b"\x00\x00\x00\x0f" + b'{"type":"ping"}'


def test_the_request_names_and_the_discovery_query():
    assert set(Shares().handlers()) == {"manifest", "chunk"}
    assert discovery.SERVICE == "_keepsake._tcp.local."
    assert hashlib.sha256(discovery.build_query(0)).hexdigest() == (
        "230809dc1101ae7ffac304a842c3aff267a518fea31f27c9a74aa08d50ede123"
    )


def test_the_offer_is_an_addition_and_changes_nothing_else():
    """ADR-0059: new request types may be added under version 1; existing ones stay as they are."""
    from keepsake.replication import offers

    assert set(Shares().handlers()) == {"manifest", "chunk"}
    assert offers.SCOPES == ("install", "prefix", "tool", "art")
    assert link.PROTOCOL == 1
