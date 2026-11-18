"""Replication's encrypted link and pairing (slice 17, ADR-0054), over real loopback TLS."""

import asyncio
import contextlib
import hashlib
import os
import ssl

import pytest

from keepsake.replication import link
from keepsake.replication.peers import PeerError, PeerStore
from keepsake.replication.service import Links, ReplicationError, is_overlay, parse_address

pytestmark = pytest.mark.skipif(not link.available(), reason="this OpenSSL has no TLS-PSK")

A = link.Identity("device-aaaa-0001", "Test handheld A")
B = link.Identity("device-bbbb-0002", "Test handheld B")


def stores(tmp_path):
    return PeerStore(str(tmp_path / "a.json")), PeerStore(str(tmp_path / "b.json"))


async def until(condition, timeout=10.0):
    for _ in range(int(timeout / 0.02)):
        if condition():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")


async def start_pair(tmp_path, open_window=True):
    store_a, store_b = stores(tmp_path)
    a = Links(A, store_a, "127.0.0.1", 0)
    b = Links(B, store_b, "127.0.0.1", 0)
    await b.set_listener(True)
    if open_window:
        b.open_pairing()
    address = f"127.0.0.1:{b.listener.bound_port}"
    return a, b, address


def only(pairings):
    assert len(pairings) == 1
    return pairings[0]


async def pair(a, b, address):
    """Pair A with B, both users confirming. Returns both pairings' public views."""
    started = a.pair_with(address)
    await until(lambda: a.initiated[started["id"]].state == "compare" and b.listener.pairings)
    mine = a.initiated[started["id"]]
    theirs = only(list(b.listener.pairings.values()))
    await until(lambda: theirs.state == "compare")
    assert mine.code == theirs.code and len(mine.code) == 6 and mine.code.isdigit()
    a.answer(mine.id, True)
    b.answer(theirs.id, True)
    await until(lambda: mine.state == "paired" and theirs.state == "paired")
    return mine, theirs


def test_two_devices_pair_and_then_connect(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path)
        try:
            mine, theirs = await pair(a, b, address)
            assert mine.peer_name == B.name and theirs.peer_name == A.name
            key_a, key_b = a.store.key(B.device_id), b.store.key(A.device_id)
            assert key_a == key_b and len(key_a) == 32  # one shared key, known to both
            assert key_a != link.PAIR_KEY
            assert not b.listener.pairing_open()  # the window closes once paired
            check = await a.check(B.device_id)
            assert check["ok"] and check["rttMs"] >= 0 and check["overlay"] is False
            # The peer list never carries the key.
            assert all("key" not in p for p in a.status()["peers"] + b.status()["peers"])
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_a_no_on_either_device_pairs_nothing(tmp_path):
    for refuse in ("initiator", "responder"):

        async def scenario(refuse=refuse, folder=tmp_path / refuse):
            folder.mkdir()
            a, b, address = await start_pair(folder)
            try:
                started = a.pair_with(address)
                mine = a.initiated[started["id"]]
                await until(lambda: mine.state == "compare" and b.listener.pairings)
                theirs = only(list(b.listener.pairings.values()))
                await until(lambda: theirs.state == "compare")
                a.answer(mine.id, refuse != "initiator")
                b.answer(theirs.id, refuse != "responder")
                await until(lambda: mine.state == "failed" and theirs.state == "failed")
                assert a.store.list() == [] and b.store.list() == []
            finally:
                await a.close()
                await b.close()

        asyncio.run(scenario())


def test_pairing_needs_the_window_open(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path, open_window=False)
        try:
            started = a.pair_with(address)
            mine = a.initiated[started["id"]]
            await until(lambda: mine.state == "failed")
            assert "pairing window" in mine.reason
            assert b.listener.pairings == {}  # refused in the handshake, before any message
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_the_window_allows_three_attempts_and_then_closes(tmp_path):
    async def scenario():
        a, b, _address = await start_pair(tmp_path)
        port = b.listener.bound_port
        try:
            for _ in range(link.PAIR_ATTEMPTS):
                _, writer = await asyncio.open_connection(
                    "127.0.0.1", port, ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY), server_hostname=None
                )
                writer.close()
            assert not b.listener.pairing_open()
            with pytest.raises((ssl.SSLError, OSError)):
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", port, ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY), server_hostname=None
                )
                await link.read_frame(reader, timeout=2)
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_the_window_times_out(tmp_path):
    store = PeerStore(str(tmp_path / "b.json"))
    now = [100.0]
    listener = link.Listener(B, store, "127.0.0.1", 0, clock=lambda: now[0])
    listener.open_pairing(seconds=120)
    assert listener.pairing_open() and listener.window_seconds_left() == 120
    now[0] += 121
    assert not listener.pairing_open() and listener.window_seconds_left() == 0


def test_an_unpaired_device_is_refused_and_then_blocked(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path, open_window=False)
        port = b.listener.bound_port
        try:
            stranger = link.client_context("device-cccc-0003", os.urandom(32))
            for _ in range(link.FAILURE_LIMIT):
                with pytest.raises((ssl.SSLError, OSError, ConnectionError)):
                    reader, writer = await asyncio.open_connection(
                        "127.0.0.1", port, ssl=stranger, server_hostname=None
                    )
                    await link.send_frame(writer, {"type": "hello", "deviceId": "device-cccc-0003"})
                    await link.read_frame(reader, timeout=2)
            assert b.listener._blocked("127.0.0.1")
            # A paired key from a blocked address is refused too, until the block lapses.
            b.store.add(A.device_id, A.name, b"k" * 32, "")
            a.store.add(B.device_id, B.name, b"k" * 32, address)
            assert (await a.check(B.device_id))["ok"] is False
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_a_wrong_key_for_a_known_device_is_refused(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path, open_window=False)
        try:
            b.store.add(A.device_id, A.name, b"x" * 32, "")
            a.store.add(B.device_id, B.name, b"y" * 32, address)
            result = await a.check(B.device_id)
            assert result["ok"] is False and "pair them again" in result["reason"]
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_a_hello_from_another_identity_is_dropped(tmp_path):
    async def scenario():
        a, b, _address = await start_pair(tmp_path, open_window=False)
        port = b.listener.bound_port
        try:
            b.store.add(A.device_id, A.name, b"k" * 32, "")
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", port, ssl=link.client_context(A.device_id, b"k" * 32), server_hostname=None
            )
            await link.send_frame(writer, {"type": "hello", "deviceId": "device-cccc-0003"})
            with pytest.raises(link.LinkError):
                await link.read_frame(reader, timeout=5)
            writer.close()
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_removing_a_device_stops_it_connecting(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path)
        try:
            await pair(a, b, address)
            connection = await link.connect(A, a.store, B.device_id, "127.0.0.1", b.listener.bound_port)
            await b.remove(A.device_id)
            with pytest.raises(link.LinkError):
                await connection.ping()  # the open connection is closed
            await connection.close()
            result = await a.check(B.device_id)
            assert result["ok"] is False  # and the next handshake is refused
            with pytest.raises(ReplicationError):
                await b.remove(A.device_id)
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_no_socket_while_the_listener_is_off(tmp_path):
    async def scenario():
        store = PeerStore(str(tmp_path / "b.json"))
        links = Links(B, store, "127.0.0.1", 0)
        assert links.listener is None and links.status()["listener"]["on"] is False
        with pytest.raises(ReplicationError, match="listener"):
            links.open_pairing()
        await links.set_listener(True)
        port = links.listener.bound_port
        assert port
        await links.set_listener(False)
        with pytest.raises(OSError):
            await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 2)

    asyncio.run(scenario())


def test_a_reveal_that_breaks_its_commitment_fails(tmp_path):
    """The responder checks the initiator's nonce against what it committed to first."""

    async def scenario():
        store_b = PeerStore(str(tmp_path / "b.json"))
        listener = link.Listener(B, store_b, "127.0.0.1", 0)
        await listener.start()
        listener.open_pairing()
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                listener.bound_port,
                ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY),
                server_hostname=None,
            )
            committed = os.urandom(32)
            await link.send_frame(
                writer,
                {
                    "type": "pair-commit",
                    "v": link.PROTOCOL,
                    "deviceId": A.device_id,
                    "name": A.name,
                    "commit": hashlib.sha256(committed).hexdigest(),
                },
            )
            await link.expect(reader, "pair-nonce")
            await link.send_frame(writer, {"type": "pair-reveal", "nonce": os.urandom(32).hex()})
            await until(lambda: listener.pairings and only(list(listener.pairings.values())).state == "failed")
            pairing = only(list(listener.pairings.values()))
            assert "promised" in pairing.reason and pairing.code is None
            writer.close()
        finally:
            await listener.stop()
        assert store_b.list() == []

    asyncio.run(scenario())


def test_a_key_removed_under_an_open_connection_ends_it(tmp_path):
    """Even without ``drop``, the next request on an open connection finds the key gone."""

    async def scenario():
        a, b, address = await start_pair(tmp_path)
        try:
            await pair(a, b, address)
            connection = await link.connect(A, a.store, B.device_id, "127.0.0.1", b.listener.bound_port)
            await connection.ping()
            b.store.remove(A.device_id)  # the file only, as another process might
            with pytest.raises(link.LinkError):
                await connection.ping()
            await connection.close()
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_the_initiator_refuses_a_responder_using_its_own_identity(tmp_path):
    """A reflecting responder that answers with the initiator's own ID is refused."""

    async def scenario():
        async def reflect(reader, writer):
            await writer.start_tls(link.server_context(lambda _identity: link.PAIR_KEY))
            commit = await link.expect(reader, "pair-commit")
            await link.send_frame(
                writer, {"type": "pair-nonce", "deviceId": commit["deviceId"], "name": "x", "nonce": "00" * 32}
            )
            with contextlib.suppress(Exception):
                await link.read_frame(reader, timeout=5)
            writer.close()

        server = await asyncio.start_server(reflect, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        store = PeerStore(str(tmp_path / "a.json"))
        pairing = link.Pairing("p1", "initiator", f"127.0.0.1:{port}")
        try:
            await link.pair_as_initiator(A, store, pairing, "127.0.0.1", port)
        finally:
            server.close()
        assert pairing.state == "failed" and "itself" in pairing.reason and pairing.code is None
        assert store.list() == []

    asyncio.run(scenario())


def test_the_responder_refuses_an_initiator_using_its_own_identity(tmp_path):
    async def scenario():
        store_b = PeerStore(str(tmp_path / "b.json"))
        listener = link.Listener(B, store_b, "127.0.0.1", 0)
        await listener.start()
        listener.open_pairing()
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                listener.bound_port,
                ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY),
                server_hostname=None,
            )
            commit = {"type": "pair-commit", "v": link.PROTOCOL, "deviceId": B.device_id, "name": "x"}
            await link.send_frame(writer, commit | {"commit": "00" * 32})
            with pytest.raises(link.LinkError, match="itself"):
                await link.read_frame(reader, timeout=5)
            writer.close()
        finally:
            await listener.stop()

    asyncio.run(scenario())


def test_a_device_cannot_pair_with_itself(tmp_path):
    async def scenario():
        store_a, store_b = stores(tmp_path)
        a = Links(B, store_a, "127.0.0.1", 0)  # the same identity on both ends
        b = Links(B, store_b, "127.0.0.1", 0)
        await b.set_listener(True)
        b.open_pairing()
        try:
            started = a.pair_with(f"127.0.0.1:{b.listener.bound_port}")
            await until(lambda: a.initiated[started["id"]].state == "failed")
            assert "itself" in a.initiated[started["id"]].reason
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_the_comparison_code_depends_on_every_input():
    parts = (b"binding-1", b"n" * 32, b"m" * 32, A.device_id, B.device_id)
    code = link.comparison_code(*parts)
    assert len(code) == 6 and code.isdigit()
    for i in range(5):
        changed = list(parts)
        changed[i] = changed[i] + (b"x" if isinstance(changed[i], bytes) else "x")
        assert link.comparison_code(*changed) != code
    # Length prefixes keep a moved byte from producing the same input.
    assert link.comparison_code(b"ab", b"c", *parts[2:]) != link.comparison_code(b"a", b"bc", *parts[2:])


def test_a_frame_too_large_is_refused():
    async def scenario():
        reader = asyncio.StreamReader()
        reader.feed_data((link.MAX_FRAME + 1).to_bytes(4, "big"))
        with pytest.raises(link.LinkError, match="too large"):
            await link.read_frame(reader, timeout=1)
        for body in (b"[1]", b"not json", b'{"no":"type"}'):
            reader = asyncio.StreamReader()
            reader.feed_data(len(body).to_bytes(4, "big") + body)
            with pytest.raises(link.LinkError, match="not valid"):
                await link.read_frame(reader, timeout=1)

    asyncio.run(scenario())


def test_without_tls_psk_replication_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(ssl, "HAS_PSK", False, raising=False)
    assert link.available() is False
    with pytest.raises(link.LinkError, match="TLS-PSK"):
        link.client_context("x", b"k" * 32)
    listener = link.Listener(B, PeerStore(str(tmp_path / "b.json")), "127.0.0.1", 0)
    with pytest.raises(link.LinkError, match="TLS-PSK"):
        asyncio.run(listener.start())
    assert listener._server is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("192.168.1.20", ("192.168.1.20", 47110)),
        ("192.168.1.20:47200", ("192.168.1.20", 47200)),
        ("[fe80::1]:47111", ("fe80::1", 47111)),
        ("fd00::5", ("fd00::5", 47110)),
        ("legion-go.local", ("legion-go.local", 47110)),
        ("my-pc.tailnet-name.ts.net:47110", ("my-pc.tailnet-name.ts.net", 47110)),
    ],
)
def test_addresses_the_user_can_type(text, expected):
    assert parse_address(text) == expected


@pytest.mark.parametrize(
    "text", ["", "http://192.168.1.20", "192.168.1.20/x", "user@host", "host:0", "host:99999", "bad_name!", "[::1"]
)
def test_addresses_that_are_refused(text):
    with pytest.raises(ReplicationError):
        parse_address(text)


def test_tailscale_addresses_are_recognised():
    assert is_overlay("100.101.102.103") and is_overlay("fd7a:115c:a1e0::1") and is_overlay("pc.example.ts.net")
    assert not is_overlay("192.168.1.20") and not is_overlay("legion-go.local")


def test_the_peer_store_keeps_keys_private_and_bounded(tmp_path):
    store = PeerStore(str(tmp_path / "peers.json"))
    peer = store.add("device-dddd-0004", "Name\x00 with control", b"k" * 32, "192.168.1.20:47110")
    assert peer["name"] == "Name with control" and "key" not in peer
    assert store.key("device-dddd-0004") == b"k" * 32
    if os.name == "posix":
        assert os.stat(store.path).st_mode & 0o777 == 0o600
    with pytest.raises(PeerError):
        store.add("bad id", "x", b"k" * 32, "")
    with pytest.raises(PeerError):
        store.add("device-eeee-0005", "x", b"short", "")
    for i in range(15):
        store.add(f"device-ffff-{i:04d}", "x", b"k" * 32, "")
    with pytest.raises(PeerError, match="at most"):
        store.add("device-gggg-0006", "x", b"k" * 32, "")
    store.add("device-dddd-0004", "renamed", b"j" * 32, "")  # pairing again replaces the key
    assert store.key("device-dddd-0004") == b"j" * 32
    assert store.remove("device-dddd-0004") and not store.remove("device-dddd-0004")
    assert store.key("device-dddd-0004") is None and store.key(None) is None


def test_a_damaged_peer_file_is_read_as_no_peers(tmp_path):
    path = tmp_path / "peers.json"
    path.write_text('{"peers": {"device-aaaa-0001": {"key": "zz"}, "bad id": {"key": "' + "00" * 32 + '"}}}')
    assert PeerStore(str(path)).list() == []
    path.write_text("not json")
    assert PeerStore(str(path)).list() == []
