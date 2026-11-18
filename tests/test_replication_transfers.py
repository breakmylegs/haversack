"""Replication 18b (ADR-0058): streams and sources, holds, the sleep guard, and the transfers manager."""

import asyncio
import os
import socket
import struct

import pytest

from keepsake import power
from keepsake.replication import jobs, sleepguard, transfer
from keepsake.replication import manifest as mf
from keepsake.replication.link import LinkError
from test_replication_devices import make_app  # noqa: F401 - the app fixture
from test_replication_transfer import PEER, FakeConnection, job_for, make_source, offer, tree_of

OTHER = "device-cccc-0003"


@pytest.fixture
def small_chunks(monkeypatch):
    """64 KiB chunks so a few hundred kilobytes make many chunks (no zero chunks are used)."""
    monkeypatch.setattr(mf, "CHUNK", 64 * 1024)


def many_chunks(tmp_path, count=24):
    root = tmp_path / "source"
    (root / "data").mkdir(parents=True)
    (root / "data" / "pack.bin").write_bytes(os.urandom(64 * 1024 * count))
    return root


async def no_sleep(_seconds):
    return None


# Battery and games


def test_battery_state_from_sysfs(tmp_path):
    base = tmp_path / "sys" / "class" / "power_supply"
    (base / "BAT0").mkdir(parents=True)
    (base / "BAT0" / "type").write_text("Battery\n")
    (base / "BAT0" / "capacity").write_text("27\n")
    (base / "BAT0" / "status").write_text("Discharging\n")
    (base / "A-pad").mkdir()  # sorts before BAT0: its scope must keep it out
    (base / "A-pad" / "type").write_text("Battery\n")
    (base / "A-pad" / "scope").write_text("Device\n")  # a controller's battery does not count
    (base / "A-pad" / "capacity").write_text("90\n")
    assert power.linux_battery_state(str(tmp_path)) == (27, False)
    (base / "ACAD").mkdir()
    (base / "ACAD" / "type").write_text("Mains\n")
    (base / "ACAD" / "online").write_text("1\n")
    assert power.linux_battery_state(str(tmp_path)) == (27, True)
    assert power.linux_battery_state(str(tmp_path / "none")) == (None, None)


@pytest.mark.parametrize(
    ("percent", "mains", "game", "waits"),
    [
        (29, False, False, "battery"),
        (30, False, False, None),
        (10, True, False, None),
        (10, None, False, None),  # cannot tell: do not hold a copy hostage
        (None, False, False, None),
        (90, True, True, "game"),
    ],
)
def test_the_hold_rule(percent, mains, game, waits):
    reason = jobs.hold_reason(percent, mains, game)
    assert (reason is None) == (waits is None)
    if waits:
        assert waits in reason


# D-Bus messages for the sleep guard


def test_a_method_call_is_laid_out_as_d_bus_expects():
    message = sleepguard.method_call(
        7, "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "Inhibit",
        ["sleep", "Keepsake", "Copying", "delay"],
    )  # fmt: skip
    assert message[:4] == b"l\x01\x00\x01"
    body_len, serial, fields_len = struct.unpack("<III", message[4:16])
    assert serial == 7
    body_start = 16 + fields_len + (-(16 + fields_len) % 8)
    assert len(message) == body_start + body_len
    body = message[body_start:]
    assert body[:4] == struct.pack("<I", 5) and body[4:10] == b"sleep\x00"
    header = sleepguard.parse_header(message)
    assert header["type"] == 1 and header["serial"] == 7 and header["length"] == len(message)
    assert b"Inhibit\x00" in message and b"\x04ssss\x00" in message  # the signature field


def test_a_reply_header_is_read_with_its_serial_error_and_descriptors():
    fields = bytearray()
    for code, sig, value in ((5, "u", struct.pack("<I", 7)), (9, "u", struct.pack("<I", 1))):
        fields.extend(b"\x00" * (-len(fields) % 8))
        fields.extend(bytes([code, 1]) + sig.encode() + b"\x00")
        fields.extend(b"\x00" * (-(16 + len(fields)) % 4))
        fields.extend(value)
    header = b"l\x02\x00\x01" + struct.pack("<III", 4, 1, len(fields)) + bytes(fields)
    message = header + b"\x00" * (-len(header) % 8) + struct.pack("<I", 0)
    parsed = sleepguard.parse_header(message)
    assert parsed["type"] == 2 and parsed["replySerial"] == 7 and parsed["fdCount"] == 1
    with pytest.raises(sleepguard.SleepGuardError):
        sleepguard.parse_header(b"B" + message[1:])  # big-endian is not spoken
    with pytest.raises(sleepguard.SleepGuardError):
        sleepguard.parse_header(message[:20])


def test_without_a_bus_the_guard_reports_and_the_transfer_carries_on(tmp_path):
    guard = sleepguard.SleepGuard(bus_path=str(tmp_path / "no-bus"), platform="linux")
    assert guard.acquire() is False and "may sleep" in guard.problem
    guard.release()
    assert not guard.held


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX") or os.name != "posix", reason="needs a Unix socket")
def test_the_guard_holds_the_descriptors_logind_hands_back(tmp_path):
    """A fake system bus: it accepts the handshake and answers Hello and both Inhibit calls."""
    path = str(tmp_path / "bus")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    pipes = [os.pipe() for _ in range(2)]
    import threading

    def reply(serial, with_fd):
        fields = bytearray()
        items = [(5, struct.pack("<I", serial))] + ([(9, struct.pack("<I", 1))] if with_fd else [])
        for code, value in items:
            fields.extend(b"\x00" * (-len(fields) % 8))
            fields.extend(bytes([code, 1]) + b"u\x00")
            fields.extend(value)
        head = b"l\x02\x00\x01" + struct.pack("<III", 4, 99, len(fields)) + bytes(fields)
        return head + b"\x00" * (-len(head) % 8) + struct.pack("<I", 0)

    def serve():
        conn, _ = server.accept()
        data = b""
        while b"BEGIN\r\n" not in data:
            data += conn.recv(4096)
            if b"AUTH" in data and b"OK" not in data:
                conn.sendall(b"OK 0123456789abcdef\r\n")
                data += b"OK"
            if b"NEGOTIATE_UNIX_FD" in data and b"AGREED" not in data:
                conn.sendall(b"AGREE_UNIX_FD\r\n")
                data += b"AGREED"
        for serial, fd in ((1, None), (2, pipes[0][0]), (3, pipes[1][0])):
            conn.recv(4096)
            message = reply(serial, fd is not None)
            ancillary = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack("i", fd))] if fd is not None else []
            conn.sendmsg([message], ancillary)
        conn.close()

    thread = threading.Thread(target=serve)
    thread.start()
    guard = sleepguard.SleepGuard(bus_path=path, platform="linux")
    assert guard.acquire() is True and len(guard.fds) == 2, guard.problem
    guard.release()
    thread.join(5)
    server.close()
    for read, write in pipes:  # the guard received copies; these originals are the test's own
        os.close(read)
        os.close(write)


# Streams and sources


def test_chunks_come_from_every_source_and_streams_grow_while_speed_rises(tmp_path, monkeypatch, small_chunks):
    source = many_chunks(tmp_path)
    source, shares, share = offer(tmp_path, source)
    monkeypatch.setattr(transfer, "ADD_STREAM_GAIN", 0.0)  # treat every window as faster: grow to the limit
    made = {"a": [], "b": []}

    def maker(name):
        async def connect():
            await asyncio.sleep(0)
            connection = FakeConnection(shares)
            original = connection.request_blob

            async def slow(message, max_size=1 << 26, timeout=30):
                await asyncio.sleep(0.005)  # so streams overlap
                return await original(message, max_size, timeout)

            connection.request_blob = slow
            made[name].append(connection)
            return connection

        return connect

    job = job_for(share, tmp_path / "Game")
    receiver = transfer.Receiver(job, [maker("a"), maker("b")], sleep=no_sleep, max_streams=4, adapt_seconds=0.01)
    done = asyncio.run(receiver.run())
    assert done.state == "done", done.reason
    assert tree_of(tmp_path / "Game") == tree_of(source)
    chunk_calls = {name: sum(1 for c in conns for m in c.calls if m["type"] == "chunk") for name, conns in made.items()}
    assert chunk_calls["a"] > 0 and chunk_calls["b"] > 0
    assert len(made["a"]) + len(made["b"]) <= 4 + 1  # never more streams than allowed (plus the manifest one)


def test_streams_stop_growing_when_another_does_not_help(tmp_path, monkeypatch, small_chunks):
    source = many_chunks(tmp_path)
    _source, shares, share = offer(tmp_path, source)
    monkeypatch.setattr(transfer, "ADD_STREAM_GAIN", 1e9)  # no window is ever fast enough
    count = []

    async def connect():
        count.append(1)
        return FakeConnection(shares)

    job = job_for(share, tmp_path / "Game")
    done = asyncio.run(transfer.Receiver(job, connect, sleep=no_sleep, adapt_seconds=0.0).run())
    assert done.state == "done"
    assert len(count) <= 2  # the first stream, and one trial stream after the first window


def test_a_source_that_fails_is_dropped_and_the_others_finish(tmp_path, small_chunks):
    source = many_chunks(tmp_path, 8)
    source, shares, share = offer(tmp_path, source)

    async def gone():
        raise LinkError("could not reach the second device")

    async def good():
        return FakeConnection(shares)

    job = job_for(share, tmp_path / "Game")
    done = asyncio.run(transfer.Receiver(job, [good, gone], sleep=no_sleep, adapt_seconds=0.0, retries=0).run())
    assert done.state == "done", done.reason
    assert tree_of(tmp_path / "Game") == tree_of(source)


def test_a_hold_pauses_the_job_as_held(tmp_path, small_chunks):
    source = many_chunks(tmp_path, 8)
    _source, shares, share = offer(tmp_path, source)

    async def connect():
        return FakeConnection(shares)

    job = job_for(share, tmp_path / "Game")
    receiver = transfer.Receiver(
        job, connect, sleep=no_sleep, adapt_seconds=0.0, hold=lambda: "waiting while a game runs on this device"
    )
    done = asyncio.run(receiver.run())
    assert done.state == "paused" and done.held is True and "game" in done.reason
    assert transfer.load_journal(job.staging).held is True


def test_progress_reports_speed_and_time_left():
    job = transfer.Job("j", PEER, "s", "r", "/x/Game", total=10_000_000, received=4_000_000, rate=2_000_000.0)
    job.state = "running"
    view = job.public()
    assert view["megabytesPerSecond"] == 2.0 and view["secondsLeft"] == 3 and view["target"] == "Game"
    job.state = "paused"
    assert job.public()["secondsLeft"] is None


# The transfers manager


def make_manager(tmp_path, shares, conditions=lambda: None):
    async def connect_any():
        return FakeConnection(shares)

    guard = sleepguard.SleepGuard(bus_path=str(tmp_path / "no-bus"), platform="linux")
    return jobs.Transfers(
        str(tmp_path / "jobs.json"), lambda _peer: connect_any, conditions=conditions, guard=guard, retries=0
    )


def test_a_transfer_runs_to_the_end_and_is_forgotten(tmp_path):
    source, shares, share = offer(tmp_path)

    async def scenario():
        manager = make_manager(tmp_path, shares)
        manager.start(job_for(share, tmp_path / "Game"))
        assert "job1" in manager._registry()
        await asyncio.gather(*manager.tasks.values())
        await asyncio.sleep(0)
        return manager

    manager = asyncio.run(scenario())
    assert manager.jobs == {} and manager._registry() == {}
    assert tree_of(tmp_path / "Game") == tree_of(source)


def test_pause_resume_and_stop(tmp_path, small_chunks):
    source = many_chunks(tmp_path)
    source, shares, share = offer(tmp_path, source)

    async def scenario():
        manager = make_manager(tmp_path, shares)
        manager.start(job_for(share, tmp_path / "Game"))
        await asyncio.sleep(0.01)
        paused = await manager.pause("job1")
        assert paused["state"] == "paused" and "job1" not in manager.tasks
        assert transfer.load_journal(manager.jobs["job1"].staging).by_user is True
        await manager.resume("job1")
        await asyncio.gather(*manager.tasks.values())
        await asyncio.sleep(0)
        assert tree_of(tmp_path / "Game") == tree_of(source)
        manager.start(job_for(share, tmp_path / "Other", id="job2"))
        await asyncio.sleep(0.01)
        staging = manager.jobs["job2"].staging
        await manager.stop("job2")
        assert not os.path.exists(staging) and not (tmp_path / "Other").exists() and "job2" not in manager._registry()
        with pytest.raises(transfer.TransferError):
            await manager.resume("job2")

    asyncio.run(scenario())


def test_after_a_restart_only_jobs_the_user_did_not_pause_resume(tmp_path):
    _source, shares, share = offer(tmp_path)
    auto = job_for(share, tmp_path / "Auto", id="job-auto")
    mine = job_for(share, tmp_path / "Mine", id="job-mine")
    for job, state, by_user in ((auto, "running", False), (mine, "paused", True)):
        os.makedirs(job.staging)
        job.state, job.by_user = state, by_user
        transfer.save_journal(job)

    async def scenario():
        manager = make_manager(tmp_path, shares)
        manager._save_registry(
            {auto.id: auto.staging, mine.id: mine.staging, "gone": str(tmp_path / ".keepsake-incoming-gone")}
        )
        resumed = await manager.start_up()
        assert resumed == ["job-auto"] and set(manager.jobs) == {"job-auto", "job-mine"}
        assert "gone" not in manager._registry()
        await asyncio.gather(*manager.tasks.values())
        await manager.shut_down()

    asyncio.run(scenario())
    assert (tmp_path / "Auto").exists() and not (tmp_path / "Mine").exists()


def test_held_jobs_resume_once_the_reason_has_gone(tmp_path, small_chunks):
    source = many_chunks(tmp_path, 8)
    source, shares, share = offer(tmp_path, source)
    reason = ["waiting while a game runs on this device"]

    async def scenario():
        manager = make_manager(tmp_path, shares, conditions=lambda: reason[0])
        manager.start(job_for(share, tmp_path / "Game"))
        await asyncio.gather(*manager.tasks.values())
        assert manager.jobs["job1"].held and manager.status()["waitingFor"] == reason[0]
        assert manager.check_holds() == []  # still waiting
        reason[0] = None
        assert manager.check_holds() == ["job1"]
        await asyncio.gather(*manager.tasks.values())
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert tree_of(tmp_path / "Game") == tree_of(source)


def test_the_number_of_kept_transfers_is_bounded(tmp_path, monkeypatch):
    _source, shares, share = offer(tmp_path)
    monkeypatch.setattr(jobs, "MAX_JOBS", 1)
    manager = make_manager(tmp_path, shares)
    manager._save_registry({"other": str(tmp_path / ".keepsake-incoming-other")})
    with pytest.raises(transfer.TransferError, match="at most 1"):
        manager._remember(job_for(share, tmp_path / "Game"))


def test_make_source_is_synthetic(tmp_path):
    root = make_source(tmp_path / "s", big=False)
    assert sorted(os.listdir(root)) == ["bin", "data"]


def test_the_app_holds_transfers_while_a_game_runs(make_app, tmp_path):  # noqa: F811
    async def scenario():
        app = make_app("a")
        app.power_root = str(tmp_path / "no-power")
        await app.start()
        await app.set_module_enabled("replication", True)
        try:
            status = await app.replication_transfers()
            assert status["jobs"] == [] and status["waitingFor"] is None
            await app.bus.publish("game_started", {"gameKey": "k", "appid": 4000001})
            assert "game runs" in (await app.replication_transfers())["waitingFor"]
            await app.bus.publish("game_exited", {"gameKey": "k", "appid": 4000001})
            assert (await app.replication_transfers())["waitingFor"] is None
            for call in (app.replication_pause, app.replication_resume, app.replication_stop):
                with pytest.raises(ValueError, match="ended"):
                    await call("no-such-job")
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_an_error_reply_names_the_error():
    fields = bytearray()
    name = b"org.freedesktop.DBus.Error.AccessDenied"
    fields.extend(bytes([4, 1]) + b"s\x00" + struct.pack("<I", len(name)) + name + b"\x00")
    fields.extend(b"\x00" * (-len(fields) % 8))
    fields.extend(bytes([5, 1]) + b"u\x00" + struct.pack("<I", 3))
    message = b"l\x03\x00\x01" + struct.pack("<III", 0, 1, len(fields)) + bytes(fields)
    parsed = sleepguard.parse_header(message + b"\x00" * (-len(message) % 8))
    assert parsed["type"] == 3 and parsed["error"] == name.decode() and parsed["replySerial"] == 3


def test_never_more_streams_than_allowed(tmp_path, monkeypatch, small_chunks):
    source = many_chunks(tmp_path, 48)
    _source, shares, share = offer(tmp_path, source)
    monkeypatch.setattr(
        transfer, "ADD_STREAM_GAIN", -1.0
    )  # even an empty window counts as faster: only the limit stops growth
    made = []

    async def connect():
        connection = FakeConnection(shares)
        original = connection.request_blob

        async def slow(message, max_size=1 << 26, timeout=30):
            await asyncio.sleep(0.003)
            return await original(message, max_size, timeout)

        connection.request_blob = slow
        made.append(connection)
        return connection

    job = job_for(share, tmp_path / "Game")
    done = asyncio.run(transfer.Receiver(job, connect, sleep=no_sleep, max_streams=2, adapt_seconds=0.001).run())
    assert done.state == "done"
    assert len(made) == 2  # the manifest connection becomes the first stream; one more, and no others


def test_a_chunk_in_flight_on_a_dropped_stream_goes_to_another(tmp_path, monkeypatch, small_chunks):
    source = many_chunks(tmp_path, 8)
    source, shares, share = offer(tmp_path, source)
    connections = []
    verified = []
    real_verify = transfer.Receiver._verify
    monkeypatch.setattr(transfer.Receiver, "_verify", lambda self, m: verified.append(1) or real_verify(self, m))

    async def first():
        connection = FakeConnection(shares, {3: "drop"})  # drops while fetching a chunk
        connections.append(connection)
        return connection

    async def second():
        connection = FakeConnection(shares)
        connections.append(connection)
        return connection

    job = job_for(share, tmp_path / "Game")
    done = asyncio.run(transfer.Receiver(job, [first, second], sleep=no_sleep, adapt_seconds=0.0, retries=0).run())
    assert done.state == "done" and tree_of(tmp_path / "Game") == tree_of(source)
    asked = [m["index"] for c in connections for m in c.calls if m["type"] == "chunk"]
    assert len(asked) == 8 + 1 and len(set(asked)) == 8  # the dropped chunk once more, nothing fetched twice besides
    assert verified == [1]  # the chunk went straight to another stream, not left for the final check to find


def test_a_commit_records_only_what_was_flushed(tmp_path, monkeypatch):
    _source, shares, share = offer(tmp_path)
    job = job_for(share, tmp_path / "Game")
    os.makedirs(os.path.join(job.staging, "tree", "data"))
    (tmp_path / "Game").mkdir()
    staged = os.path.join(job.staging, "tree", "data", "big.bin")
    with open(staged, "wb") as handle:
        handle.write(b"x")

    async def connect():
        return FakeConnection(shares)

    receiver = transfer.Receiver(job, connect)
    job.done = {"data/big.bin": [0]}

    def flush_while_another_stream_writes(path):
        job.done["data/big.bin"].append(2)  # written by another stream during this flush

    monkeypatch.setattr(transfer, "_fsync", flush_while_another_stream_writes)
    shared = transfer._Pull([], 0)
    shared.pending = {"data/big.bin"}
    asyncio.run(receiver._commit_now(shared))
    assert transfer.load_journal(job.staging).done == {"data/big.bin": [0]}


def test_a_job_the_user_paused_is_not_resumed_by_the_hold_check(tmp_path, small_chunks):
    source = many_chunks(tmp_path)
    _source, shares, share = offer(tmp_path, source)

    async def scenario():
        manager = make_manager(tmp_path, shares)
        manager.start(job_for(share, tmp_path / "Game"))
        await asyncio.sleep(0.01)
        await manager.pause("job1")
        assert manager.check_holds() == [] and "job1" not in manager.tasks
        await manager.shut_down()

    asyncio.run(scenario())
