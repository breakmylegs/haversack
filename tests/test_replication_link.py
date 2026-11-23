"""Replication's encrypted link and pairing (slice 17, ADR-0054; pairing by code, ADR-0070), over real loopback TLS."""

import asyncio
import contextlib
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


async def start_pair(tmp_path, open_window=None):
    """A sends, B receives. B takes requests whenever its listener is on (ADR-0070)."""
    store_a, store_b = stores(tmp_path)
    a = Links(A, store_a, "127.0.0.1", 0)
    b = Links(B, store_b, "127.0.0.1", 0)
    await b.set_listener(True)
    address = f"127.0.0.1:{b.listener.bound_port}"
    return a, b, address


def only(pairings):
    assert len(pairings) == 1
    return pairings[0]


async def requested(a, b, address):
    """A sends a request; returns A's pairing and B's, with B's waiting for Accept or Decline."""
    started = a.pair_with(address)
    mine = a.initiated[started["id"]]
    await until(lambda: mine.state == "waiting-accept" and b.listener.pairings)
    theirs = only(list(b.listener.pairings.values()))
    await until(lambda: theirs.state == "request")
    return mine, theirs


async def pair(a, b, address, typed=None):
    """Pair A with B: B accepts and shows a code, the user types it on A. Returns both pairings."""
    mine, theirs = await requested(a, b, address)
    assert theirs.peer_name == A.name and theirs.address.startswith("127.0.0.1")
    b.answer(theirs.id, True)
    await until(lambda: theirs.state == "show-code" and mine.state == "enter-code")
    assert len(theirs.code) == 6 and theirs.code.isdigit()
    assert mine.code is None and mine.public()["code"] is None  # the requester never has the code
    assert theirs.public()["code"] == theirs.code
    a.enter_code(mine.id, typed if typed is not None else theirs.code)
    await until(lambda: mine.state in ("paired", "failed") and theirs.state in ("paired", "failed"))
    return mine, theirs


def test_two_devices_pair_and_then_connect(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path)
        try:
            mine, theirs = await pair(a, b, address)
            assert mine.state == "paired" and theirs.state == "paired"
            assert mine.peer_name == B.name and theirs.peer_name == A.name
            key_a, key_b = a.store.key(B.device_id), b.store.key(A.device_id)
            assert key_a == key_b and len(key_a) == 32  # one shared key, known to both
            assert key_a != link.PAIR_KEY
            assert theirs.public()["code"] is None  # the code is not shown once paired
            check = await a.check(B.device_id)
            assert check["ok"] and check["rttMs"] >= 0 and check["overlay"] is False
            # The peer list never carries the key.
            assert all("key" not in p for p in a.status()["peers"] + b.status()["peers"])
            assert b.status()["listener"]["acceptsRequests"] is True
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_a_wrong_code_ends_the_attempt_on_both_devices(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path)
        try:
            mine, theirs = await requested(a, b, address)
            b.answer(theirs.id, True)
            await until(lambda: theirs.state == "show-code" and mine.state == "enter-code")
            value = int(theirs.code)  # differs only from bit 10 up: every round must be checked
            wrong = f"{value - 1024 if value >= 1024 else value + 1024:06d}"
            a.enter_code(mine.id, wrong)
            with pytest.raises(ReplicationError, match="not waiting"):
                a.enter_code(mine.id, theirs.code)  # one entry per attempt
            await until(lambda: mine.state == "failed" and theirs.state == "failed")
            assert "code was wrong" in mine.reason and "code was wrong" in theirs.reason
            assert a.store.list() == [] and b.store.list() == []
            assert len(b.listener._pair_failures["address:127.0.0.1"]) == 1
            assert len(b.listener._pair_failures[f"device:{A.device_id}"]) == 1
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_decline_and_no_answer_pair_nothing(tmp_path):
    for case in ("decline", "timeout"):

        async def scenario(case=case, folder=tmp_path / case):
            folder.mkdir()
            a, b, address = await start_pair(folder)
            b.listener.confirm_timeout = 0.3
            try:
                mine, theirs = await requested(a, b, address)
                if case == "decline":
                    b.answer(theirs.id, False)
                    with pytest.raises(ReplicationError, match="not waiting"):
                        b.answer(theirs.id, True)  # answered once
                await until(lambda: mine.state == "declined" and theirs.state == "declined")
                assert len(b.listener._pair_failures["address:127.0.0.1"]) == 1  # counts towards the lockout
                expected = "declined" if case == "decline" else "did not answer in time"
                assert expected in mine.reason
                assert a.store.list() == [] and b.store.list() == []
            finally:
                await a.close()
                await b.close()

        asyncio.run(scenario())


def test_no_code_typed_in_time_ends_both(tmp_path):
    async def scenario():
        store_a, store_b = stores(tmp_path)
        b = Links(B, store_b, "127.0.0.1", 0)
        await b.set_listener(True)
        b.listener.confirm_timeout = 5.0
        try:
            pairing = link.Pairing("p1", "initiator", "x")
            task = asyncio.create_task(
                link.pair_as_initiator(A, store_a, pairing, "127.0.0.1", b.listener.bound_port, confirm_timeout=0.4)
            )
            await until(lambda: b.listener.pairings and only(list(b.listener.pairings.values())).state == "request")
            theirs = only(list(b.listener.pairings.values()))
            b.answer(theirs.id, True)
            await task
            assert pairing.state == "failed" and "no code was entered in time" in pairing.reason
            await until(lambda: theirs.state == "failed")
            assert store_a.list() == [] and store_b.list() == []
        finally:
            await b.close()

    asyncio.run(scenario())


def test_cancelling_a_waiting_request_on_the_requester(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path)
        try:
            mine, theirs = await requested(a, b, address)
            with pytest.raises(ReplicationError, match="already under way"):
                a.pair_with(address)
            b.answer(theirs.id, True)
            await until(lambda: mine.state == "enter-code")
            a.cancel(mine.id)
            await until(lambda: theirs.state == "failed")
            assert mine.state == "cancelled" and a.store.list() == [] and b.store.list() == []
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_at_most_three_requests_in_two_minutes(tmp_path):
    async def scenario():
        a, b, _address = await start_pair(tmp_path)
        now = [1000.0]
        b.listener.clock = lambda: now[0]
        port = b.listener.bound_port
        context = link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY)
        try:
            for _ in range(link.REQUEST_LIMIT):
                _, writer = await asyncio.open_connection("127.0.0.1", port, ssl=context, server_hostname=None)
                writer.close()
            with pytest.raises((ssl.SSLError, OSError, ConnectionError)):
                reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=context, server_hostname=None)
                await link.read_frame(reader, timeout=2)
            now[0] += link.REQUEST_WINDOW + 1
            assert b.listener._take_request("10.0.0.9")  # two minutes later: taken again
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_five_failures_lock_an_address_or_a_device_out_for_ten_minutes(tmp_path):
    store = PeerStore(str(tmp_path / "b.json"))
    now = [5000.0]
    listener = link.Listener(B, store, "127.0.0.1", 0, clock=lambda: now[0])
    for _ in range(link.LOCKOUT_FAILURES - 1):
        listener._pair_failed("10.0.0.5", A.device_id)
    assert not listener.locked("address:10.0.0.5") and listener._take_request("10.0.0.5")
    listener._pair_failed("10.0.0.5", A.device_id)
    assert listener.locked("address:10.0.0.5") and listener.locked(f"device:{A.device_id}")
    assert not listener._take_request("10.0.0.5")
    assert not listener.locked("address:10.0.0.6")
    now[0] += link.LOCKOUT_SECONDS + 1
    assert not listener.locked("address:10.0.0.5") and not listener.locked(f"device:{A.device_id}")


def test_a_locked_out_device_id_is_refused_from_any_address(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path)
        try:
            for _ in range(link.LOCKOUT_FAILURES):
                b.listener._pair_failures.setdefault(f"device:{A.device_id}", []).append(b.listener.clock())
            started = a.pair_with(address)
            mine = a.initiated[started["id"]]
            await until(lambda: mine.state == "failed")
            assert "wait ten minutes" in mine.reason
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_a_device_in_the_middle_cannot_pair_with_either(tmp_path):
    """A relay between two TLS sessions: commitments are bound to each session, so both sides fail."""

    async def scenario():
        store_a, store_b = stores(tmp_path)
        b = Links(B, store_b, "127.0.0.1", 0)
        await b.set_listener(True)
        relayed = []

        async def middle(reader_a, writer_a):
            await writer_a.start_tls(link.server_context(lambda _identity: link.PAIR_KEY))
            reader_b, writer_b = await asyncio.open_connection(
                "127.0.0.1",
                b.listener.bound_port,
                ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY),
                server_hostname=None,
            )

            async def pump(src, dst):
                with contextlib.suppress(Exception):
                    while True:
                        frame = await link.read_frame(src, timeout=10)
                        relayed.append(frame["type"])
                        await link.send_frame(dst, frame)

            await asyncio.gather(pump(reader_a, writer_b), pump(reader_b, writer_a))
            writer_a.close()
            writer_b.close()

        server = await asyncio.start_server(middle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        pairing = link.Pairing("p1", "initiator", f"127.0.0.1:{port}")
        task = asyncio.create_task(link.pair_as_initiator(A, store_a, pairing, "127.0.0.1", port))
        try:
            await until(lambda: b.listener.pairings and only(list(b.listener.pairings.values())).state == "request")
            theirs = only(list(b.listener.pairings.values()))
            b.answer(theirs.id, True)  # the user accepts what looks like their own device
            await until(lambda: pairing.state == "enter-code" and theirs.state == "show-code")
            link.enter_code(pairing, theirs.code)  # and types the right code
            await task
            await until(lambda: theirs.state == "failed")
        finally:
            server.close()
            await b.close()
        assert pairing.state == "failed" and "code was wrong" in (pairing.reason + theirs.reason)
        assert store_a.list() == [] and store_b.list() == []
        assert "pair-key" not in relayed  # the key was never sent

    asyncio.run(scenario())


def test_an_unpaired_device_is_refused_and_then_blocked(tmp_path):
    async def scenario():
        a, b, address = await start_pair(tmp_path)
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
        a, b, address = await start_pair(tmp_path)
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
        a, b, _address = await start_pair(tmp_path)
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
        assert links.status()["listener"]["acceptsRequests"] is False  # no requests while it is off
        await links.set_listener(True)
        port = links.listener.bound_port
        assert port
        await links.set_listener(False)
        with pytest.raises(OSError):
            await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 2)

    asyncio.run(scenario())


def test_a_reveal_that_breaks_its_commitment_fails(tmp_path):
    """The receiver checks the requester's nonce against the commitment it sent first."""

    async def scenario():
        store_b = PeerStore(str(tmp_path / "b.json"))
        listener = link.Listener(B, store_b, "127.0.0.1", 0)
        await listener.start()
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                listener.bound_port,
                ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY),
                server_hostname=None,
            )
            await link.send_frame(
                writer, {"type": "pair-request", "v": link.PAIR_PROTOCOL, "deviceId": A.device_id, "name": A.name}
            )
            await until(lambda: listener.pairings and only(list(listener.pairings.values())).state == "request")
            pairing = only(list(listener.pairings.values()))
            link.answer(pairing, True)
            await link.expect(reader, "pair-accepted")
            await link.send_frame(writer, {"type": "pair-c", "i": 0, "c": os.urandom(32).hex()})
            await link.expect(reader, "pair-c")
            await link.send_frame(writer, {"type": "pair-n", "i": 0, "n": os.urandom(16).hex()})
            await until(lambda: pairing.state == "failed")
            assert "code was wrong" in pairing.reason and pairing.public()["code"] is None
            writer.close()
            # A round out of order is refused, whatever it holds.
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                listener.bound_port,
                ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY),
                server_hostname=None,
            )
            await link.send_frame(
                writer, {"type": "pair-request", "v": link.PAIR_PROTOCOL, "deviceId": A.device_id, "name": A.name}
            )
            await until(lambda: any(p.state == "request" for p in listener.pairings.values()))
            second = next(p for p in listener.pairings.values() if p.state == "request")
            link.answer(second, True)
            await link.expect(reader, "pair-accepted")
            await link.send_frame(writer, {"type": "pair-c", "i": 1, "c": os.urandom(32).hex()})
            await link.expect(reader, "pair-c")
            await link.send_frame(writer, {"type": "pair-n", "i": 1, "n": os.urandom(16).hex()})
            await until(lambda: second.state == "failed")
            assert "out of order" in second.reason
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
    """A reflecting receiver that accepts with the requester's own ID is refused."""

    async def scenario():
        async def reflect(reader, writer):
            await writer.start_tls(link.server_context(lambda _identity: link.PAIR_KEY))
            request = await link.expect(reader, "pair-request")
            await link.send_frame(writer, {"type": "pair-accepted", "deviceId": request["deviceId"], "name": "x"})
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
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                listener.bound_port,
                ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY),
                server_hostname=None,
            )
            await link.send_frame(
                writer, {"type": "pair-request", "v": link.PAIR_PROTOCOL, "deviceId": B.device_id, "name": "x"}
            )
            with pytest.raises(link.LinkError, match="itself"):
                await link.read_frame(reader, timeout=5)
            writer.close()
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                listener.bound_port,
                ssl=link.client_context(link.PAIR_IDENTITY, link.PAIR_KEY),
                server_hostname=None,
            )
            await link.send_frame(writer, {"type": "pair-request", "v": 1, "deviceId": A.device_id, "name": "x"})
            with pytest.raises(link.LinkError, match="different Haversack version"):
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
        try:
            started = a.pair_with(f"127.0.0.1:{b.listener.bound_port}")
            await until(lambda: a.initiated[started["id"]].state == "failed")
            assert "itself" in a.initiated[started["id"]].reason
        finally:
            await a.close()
            await b.close()

    asyncio.run(scenario())


def test_the_commitment_depends_on_every_input():
    parts = (b"n" * 16, b"binding-1", A.device_id, B.device_id, "req", 3, 1)
    mac = link.commitment(*parts)
    assert len(mac) == 32
    for i in range(len(parts)):
        changed = list(parts)
        value = changed[i]
        changed[i] = value + (b"x" if isinstance(value, bytes) else "x" if isinstance(value, str) else 1)
        if i == 6:
            changed[i] = 0
        assert link.commitment(*changed) != mac
    # Length prefixes keep a moved byte from producing the same input.
    assert link.commitment(b"n" * 16, b"ab", "c", *parts[3:]) != link.commitment(b"n" * 16, b"a", "bc", *parts[3:])


def test_codes_are_six_random_digits():
    codes = {link.new_code() for _ in range(200)}
    assert all(len(c) == 6 and c.isdigit() for c in codes) and len(codes) > 150
    assert link.check_code(" 012 345 ") == "012345"
    for bad in ("12345", "1234567", "12a456", None):
        with pytest.raises(link.LinkError):
            link.check_code(bad)
    assert 10**6 <= 2**link.CODE_BITS  # every code fits the rounds


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


def test_device_check_the_other_handheld_can_be_seen(monkeypatch):
    from keepsake import devicechecks

    class Links_:
        me = A

    answers = []

    async def browse(own_id, seconds):
        assert own_id == A.device_id
        return answers

    monkeypatch.setattr(devicechecks.discovery, "browse", browse)
    ctx = devicechecks.Context("", "", "", "", {}, "", links=Links_())
    assert asyncio.run(devicechecks.run("see-other", ctx))["status"] == "fail"
    answers.append({"id": B.device_id, "name": B.name})  # seen, paired or not
    found = asyncio.run(devicechecks.run("see-other", ctx))
    assert found["status"] == "pass" and found["title"] == "The other handheld can be seen"
    assert B.name not in found["found"]  # no device names in findings
    assert asyncio.run(devicechecks.run("see-other", devicechecks.Context("", "", "", "", {}, "")))["status"] == "skip"
