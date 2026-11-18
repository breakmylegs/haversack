"""Replication's transfer engine (slice 18a, ADR-0057), with the fault injection ADR-0045 asks for.

Synthetic folders only. Most tests use an in-process connection to the sending side; one
runs the whole path over real loopback TLS.
"""

import asyncio
import hashlib
import os
import stat

import pytest

from keepsake.replication import link, transfer
from keepsake.replication import manifest as mf
from keepsake.replication.link import LinkError, Refused, ServeError, Session
from keepsake.replication.peers import PeerStore
from keepsake.replication.source import Shares

PEER = "device-bbbb-0002"
posix = pytest.mark.skipif(os.name != "posix", reason="links and modes need POSIX")


def make_source(root, big=True):
    """A synthetic game folder: nested files, an empty file, a sparse-like file, a big one."""
    (root / "bin").mkdir(parents=True)
    (root / "data" / "levels").mkdir(parents=True)
    (root / "bin" / "game.exe").write_bytes(b"MZ" + bytes(range(256)) * 40)
    (root / "data" / "levels" / "one.pak").write_bytes(os.urandom(5000))
    (root / "data" / "empty.cfg").write_bytes(b"")
    if big:
        # Over two chunks, with an all-zero chunk in the middle: it is neither sent nor written.
        (root / "data" / "big.bin").write_bytes(os.urandom(mf.CHUNK) + bytes(mf.CHUNK) + os.urandom(1000))
    os.utime(root / "bin" / "game.exe", ns=(1_600_000_000_000_000_000, 1_600_000_000_123_456_789))
    return root


def tree_of(root):
    """Everything that must match after a copy: paths, types, bytes, sizes and mtimes."""
    out = {}
    for folder, dirs, files in os.walk(root):
        for name in dirs + files:
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            info = os.lstat(full)
            if stat.S_ISLNK(info.st_mode):
                out[rel] = ("link", os.readlink(full))
            elif stat.S_ISDIR(info.st_mode):
                out[rel] = ("dir", info.st_mtime_ns)
            else:
                with open(full, "rb") as handle:
                    digest = hashlib.sha256(handle.read()).hexdigest()
                mode = stat.S_IMODE(info.st_mode) if os.name == "posix" else None
                out[rel] = ("file", info.st_size, digest, info.st_mtime_ns, mode)
    return out


class FakeConnection:
    """The sending side's handlers, called in process, with faults on demand."""

    def __init__(self, shares, faults=None):
        self.shares = shares
        self.faults = faults or {}
        self.calls = []
        self.closed = False

    async def request_blob(self, message, max_size=link.MAX_BLOB, timeout=30):
        self.calls.append(message)
        fault = self.faults.get(len(self.calls))
        if fault == "drop":
            raise LinkError("the connection to the other device dropped")
        session = Session(PEER, "127.0.0.1", None, None)
        handler = self.shares.handlers()[message["type"]]
        try:
            header, data = await handler(session, message)
        except ServeError as exc:
            raise Refused(str(exc)) from exc
        if fault == "corrupt":
            data = bytes([data[0] ^ 1]) + data[1:]
        return header, data

    async def close(self):
        self.closed = True


def offer(tmp_path, source=None, **share_args):
    source = source or make_source(tmp_path / "source")
    shares = Shares()
    built = mf.build(str(source))
    share = shares.add(str(source), built, {PEER, *share_args.get("peers", ())})
    return source, shares, share


def job_for(share, target, **kw):
    return transfer.Job(
        id=kw.pop("id", "job1"), peer_id=PEER, share=share.id, root=share.manifest["root"], target=str(target), **kw
    )


async def no_sleep(_seconds):
    return None


def receive(job, shares, faults=None, **kw):
    connections = []

    async def connect():
        connection = FakeConnection(shares, faults if not connections else None)
        connections.append(connection)
        return connection

    receiver = transfer.Receiver(job, connect, sleep=no_sleep, **kw)
    return asyncio.run(receiver.run()), connections


# A whole copy


def test_a_folder_arrives_exactly_and_staging_is_gone(tmp_path):
    source, shares, share = offer(tmp_path)
    target = tmp_path / "library" / "Game"
    target.parent.mkdir()
    job, connections = receive(job_for(share, target), shares)
    assert job.state == "done", job.reason
    assert tree_of(target) == tree_of(source)
    assert not os.path.exists(transfer.staging_for(str(target), "job1"))
    # The all-zero chunk was never asked for.
    asked = [(c["path"], c.get("index")) for c in connections[0].calls if c["type"] == "chunk"]
    assert ("data/big.bin", 1) not in asked and ("data/big.bin", 0) in asked and ("data/big.bin", 2) in asked
    assert connections[0].closed


@posix
def test_links_modes_and_folder_times_arrive_as_they_were(tmp_path):
    source = make_source(tmp_path / "source", big=False)
    os.chmod(source / "bin" / "game.exe", 0o755)
    os.symlink("levels/one.pak", source / "data" / "current.pak")
    os.utime(source / "data" / "levels", ns=(1_500_000_000_000_000_000, 1_500_000_000_000_000_000))
    source, shares, share = offer(tmp_path, source)
    target = tmp_path / "Game"
    job, _ = receive(job_for(share, target), shares)
    assert job.state == "done", job.reason
    assert tree_of(target) == tree_of(source)
    assert os.stat(target / "bin" / "game.exe").st_mode & 0o777 == 0o755


@posix
def test_a_zero_chunk_stays_a_hole(tmp_path):
    _source, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    job, _ = receive(job_for(share, target), shares)
    assert job.state == "done"
    blocks = os.stat(target / "data" / "big.bin").st_blocks * 512
    assert blocks < os.path.getsize(target / "data" / "big.bin") - mf.CHUNK // 2  # the zero chunk is not allocated


def test_an_existing_target_is_replaced_and_its_old_copy_removed(tmp_path):
    source, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    (target / "old").mkdir(parents=True)
    (target / "old" / "stale.dat").write_bytes(b"old version")
    job, _ = receive(job_for(share, target), shares)
    assert job.state == "done"
    assert tree_of(target) == tree_of(source)
    assert not os.path.exists(transfer.staging_for(str(target), "job1"))


def test_the_whole_path_over_real_tls(tmp_path):
    if not link.available():
        pytest.skip("this OpenSSL has no TLS-PSK")
    source, shares, share = offer(tmp_path)
    me_a, me_b = link.Identity("device-aaaa-0001", "A"), link.Identity(PEER, "B")
    store_a, store_b = PeerStore(str(tmp_path / "a.json")), PeerStore(str(tmp_path / "b.json"))
    key = os.urandom(32)
    store_a.add(PEER, "B", key, "")
    store_b.add(me_a.device_id, "A", key, "")
    share.peers = {PEER}
    target = tmp_path / "Game"

    async def scenario():
        listener = link.Listener(me_a, store_a, "127.0.0.1", 0, handlers=shares.handlers())
        await listener.start()
        try:
            port = listener.bound_port

            async def connect():
                return await link.connect(me_b, store_b, me_a.device_id, "127.0.0.1", port)

            return await transfer.Receiver(job_for(share, target), connect, retries=0).run()
        finally:
            await listener.stop()

    job = asyncio.run(scenario())
    assert job.state == "done", job.reason
    assert tree_of(target) == tree_of(source)


# Fault injection (ADR-0045 rule 8)


def test_a_kill_mid_chunk_resumes_and_only_rechecks_what_might_be_incomplete(tmp_path, monkeypatch):
    source, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    real_write = transfer._write_at
    writes = []

    def dying_write(path, offset, data):
        writes.append(offset)
        if len(writes) == 3:
            real_write(path, offset, data[: len(data) // 2])  # half a chunk on disk, then the process dies
            raise asyncio.CancelledError
        real_write(path, offset, data)

    monkeypatch.setattr(transfer, "JOURNAL_EVERY_CHUNKS", 1)  # each chunk journaled once written
    monkeypatch.setattr(transfer, "_write_at", dying_write)
    with pytest.raises(asyncio.CancelledError):
        receive(job_for(share, target), shares)
    monkeypatch.setattr(transfer, "_write_at", real_write)
    staging = transfer.staging_for(str(target), "job1")
    job = transfer.recover(staging)
    assert job.state == "paused" and "restarted" in job.reason
    journaled = sum(len(v) for v in job.done.values())
    assert journaled == 2  # the two chunks before the one cut in half
    rehashed = []
    real_read = transfer._read_at
    monkeypatch.setattr(transfer, "_read_at", lambda p, o, s: rehashed.append(o) or real_read(p, o, s))
    done, _connections = receive(job, shares)
    assert done.state == "done", done.reason
    assert tree_of(target) == tree_of(source)
    assert len(rehashed) == 4 - journaled  # only the chunks the journal did not list were hashed again


def test_power_loss_with_unsynced_writes_is_caught_before_promote(tmp_path, monkeypatch):
    """Chunks written but not journaled may be garbage after power loss: they are checked and fetched again."""
    source, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    monkeypatch.setattr(transfer, "JOURNAL_EVERY_CHUNKS", 2)  # the first two chunks are journaled, then power goes
    monkeypatch.setattr(transfer, "JOURNAL_EVERY_SECONDS", 1000.0)
    calls = []
    real_commit = transfer.Receiver._commit

    def no_commit_after_first(self, paths, listed=None):
        calls.append(paths)
        if len(calls) == 1:
            return real_commit(self, paths, listed)
        raise asyncio.CancelledError  # power is lost before the data is made durable

    job = job_for(share, target)
    monkeypatch.setattr(transfer.Receiver, "_commit", no_commit_after_first)
    with pytest.raises(asyncio.CancelledError):
        receive(job, shares)
    monkeypatch.setattr(transfer.Receiver, "_commit", real_commit)
    staged = os.path.join(transfer.staging_for(str(target), "job1"), "tree", "data", "big.bin")
    with open(staged, "r+b") as handle:  # what the disk held after the power cut: chunk 2 never reached it
        handle.seek(2 * mf.CHUNK)
        handle.write(b"\xee" * 1000)
    job = transfer.recover(transfer.staging_for(str(target), "job1"))
    done, _ = receive(job, shares)
    assert done.state == "done", done.reason
    assert tree_of(target) == tree_of(source)


def test_a_damaged_journaled_chunk_is_caught_by_the_final_check(tmp_path, monkeypatch):
    source, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    real_finish = transfer.Receiver._finish
    damaged = []

    async def damage_then_finish(self):
        if not damaged:
            path = self._staged("data/levels/one.pak")
            with open(path, "r+b") as handle:
                handle.write(b"\x00\x01\x02")
            damaged.append(path)
        return await real_finish(self)

    monkeypatch.setattr(transfer.Receiver, "_finish", damage_then_finish)
    job, connections = receive(job_for(share, target), shares)
    assert job.state == "done", job.reason
    assert tree_of(target) == tree_of(source)
    asked = [c["path"] for conn in connections for c in conn.calls if c["type"] == "chunk"]
    assert asked.count("data/levels/one.pak") == 2  # fetched again after the whole-file check failed


def test_a_network_drop_is_retried_with_backoff(tmp_path):
    source, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    slept = []

    async def record(seconds):
        slept.append(seconds)

    connections = []

    async def connect():
        connection = FakeConnection(shares, {3: "drop"} if len(connections) < 2 else None)
        connections.append(connection)
        return connection

    job = asyncio.run(transfer.Receiver(job_for(share, target), connect, sleep=record).run())
    assert job.state == "done", job.reason
    assert slept == [1.0, 2.0] and len(connections) == 3
    assert tree_of(target) == tree_of(source)


def test_a_device_that_stays_away_fails_after_the_retries_allowed(tmp_path):
    _, _shares, share = offer(tmp_path)

    async def connect():
        raise LinkError("could not reach 127.0.0.1:47110")

    job = asyncio.run(transfer.Receiver(job_for(share, tmp_path / "Game"), connect, retries=2, sleep=no_sleep).run())
    assert job.state == "failed" and "could not be reached" in job.reason
    assert not (tmp_path / "Game").exists()


def test_a_corrupt_chunk_is_fetched_again_and_repeated_damage_fails(tmp_path):
    source, shares, share = offer(tmp_path)
    job, _ = receive(job_for(share, tmp_path / "Game"), shares, faults={2: "corrupt"})
    assert job.state == "done" and tree_of(tmp_path / "Game") == tree_of(source)

    class AlwaysCorrupt(FakeConnection):
        async def request_blob(self, message, max_size=link.MAX_BLOB, timeout=30):
            header, data = await super().request_blob(message, max_size, timeout)
            return header, (data if message["type"] == "manifest" else b"x" + data[1:])

    async def connect():
        return AlwaysCorrupt(shares)

    failed = asyncio.run(
        transfer.Receiver(job_for(share, tmp_path / "Other", id="job2"), connect, sleep=no_sleep).run()
    )
    assert failed.state == "failed" and "damaged" in failed.reason
    assert not (tmp_path / "Other").exists()


def test_a_full_disk_pauses_with_the_reason(tmp_path, monkeypatch):
    _, shares, share = offer(tmp_path)

    def full(*_args):
        raise transfer.DiskFull("the disk is full")

    monkeypatch.setattr(transfer, "_write_at", full)
    job, _ = receive(job_for(share, tmp_path / "Game"), shares)
    assert job.state == "paused" and "disk is full" in job.reason


def test_too_little_space_is_refused_before_anything_is_fetched(tmp_path, monkeypatch):
    _, shares, share = offer(tmp_path)
    monkeypatch.setattr(transfer.shutil, "disk_usage", lambda _p: type("U", (), {"free": 1024})())
    job, connections = receive(job_for(share, tmp_path / "Game"), shares)
    assert job.state == "paused" and "not enough space" in job.reason
    assert [c["type"] for c in connections[0].calls] == ["manifest"]


def test_a_source_that_changed_since_the_offer_fails_rather_than_sending_wrong_bytes(tmp_path):
    source, shares, share = offer(tmp_path)
    (source / "data" / "levels" / "one.pak").write_bytes(os.urandom(5000))
    job, _ = receive(job_for(share, tmp_path / "Game"), shares)
    assert job.state == "failed" and "changed on the other device" in job.reason


def test_a_manifest_that_does_not_match_the_offer_is_refused(tmp_path):
    _, shares, share = offer(tmp_path)
    job = job_for(share, tmp_path / "Game")
    job.root = "0" * 64
    done, _ = receive(job, shares)
    assert done.state == "failed" and "does not match what was offered" in done.reason
    assert not os.path.exists(os.path.join(job.staging, "manifest.json"))  # never kept, so a retry fetches it again


def test_a_device_not_offered_the_folder_is_refused(tmp_path):
    _, shares, share = offer(tmp_path)
    share.peers = {"device-cccc-0003"}
    job, _ = receive(job_for(share, tmp_path / "Game"), shares)
    assert job.state == "failed" and "not offered to this device" in job.reason


# Stop and remove, and recovery at startup


@pytest.mark.parametrize("phase", ["running", "paused", "waiting", "verifying"])
def test_stop_and_remove_leaves_nothing_at_every_phase(tmp_path, monkeypatch, phase):
    _, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    seen = []
    real_save = transfer.save_journal

    def stop_at_phase(job, done=None):
        real_save(job, done)
        if job.state == phase and not seen:
            seen.append(phase)
            raise asyncio.CancelledError

    monkeypatch.setattr(transfer, "save_journal", stop_at_phase)
    job = job_for(share, target)
    if phase == "paused":
        monkeypatch.setattr(
            transfer, "_write_at", lambda *a: (_ for _ in ()).throw(transfer.DiskFull("the disk is full"))
        )
        with pytest.raises(asyncio.CancelledError):
            receive(job, shares)
    elif phase == "waiting":

        async def connect():
            raise LinkError("gone")

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(transfer.Receiver(job, connect, sleep=no_sleep).run())
    else:
        with pytest.raises(asyncio.CancelledError):
            receive(job, shares)
    assert seen == [phase]
    monkeypatch.setattr(transfer, "save_journal", real_save)
    transfer.stop_and_remove(job)
    assert not os.path.exists(job.staging) and not target.exists()
    assert sorted(os.listdir(tmp_path)) == ["source"]  # nothing else was made


def test_a_crash_between_the_two_promote_renames_puts_the_old_target_back(tmp_path, monkeypatch):
    source, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    target.mkdir()
    (target / "keep.txt").write_bytes(b"the version before")
    real_replace = os.replace
    calls = []

    def crash_on_second(src, dst):
        calls.append((src, dst))
        if len(calls) == 2:
            raise asyncio.CancelledError  # power lost after the old target moved aside
        return real_replace(src, dst)

    monkeypatch.setattr(transfer, "_rename", crash_on_second)
    with pytest.raises(asyncio.CancelledError):
        receive(job_for(share, target), shares)
    monkeypatch.setattr(transfer, "_rename", real_replace)
    assert not target.exists()
    job = transfer.recover(transfer.staging_for(str(target), "job1"))
    assert (target / "keep.txt").read_bytes() == b"the version before" and job.state == "paused"
    done, _ = receive(job, shares)  # and the job can still finish
    assert done.state == "done" and tree_of(target) == tree_of(source)


def test_a_promote_that_failed_cleanly_keeps_the_old_target(tmp_path, monkeypatch):
    _, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    target.mkdir()
    (target / "keep.txt").write_bytes(b"old")
    real_replace = os.replace
    count = []

    def fail_second(src, dst):
        count.append(1)
        if len(count) == 2:
            raise OSError(5, "Input/output error")  # not a passing Windows sharing violation: never retried
        return real_replace(src, dst)

    monkeypatch.setattr(transfer, "_rename", fail_second)
    job, _ = receive(job_for(share, target), shares)
    assert job.state == "failed" and "could not put the copy in place" in job.reason
    assert (target / "keep.txt").read_bytes() == b"old"


def test_recovery_at_startup(tmp_path):
    _, _shares, share = offer(tmp_path)
    finished = tmp_path / "Finished"
    job = job_for(share, finished, id="job-done")
    os.makedirs(job.staging)
    job.state = "promoting"
    transfer.save_journal(job)  # the copy was renamed into place, but clean-up was cut short
    finished.mkdir()
    assert transfer.recover(job.staging).state == "done" and not os.path.exists(job.staging)
    stopped = job_for(share, tmp_path / "Stopped", id="job-stopped")
    os.makedirs(stopped.staging)
    stopped.state = "stopped"
    transfer.save_journal(stopped)
    assert transfer.recover(stopped.staging) is None and not os.path.exists(stopped.staging)
    assert transfer.recover(str(tmp_path / f"{transfer.STAGING_PREFIX}missing")) is None


def test_only_staging_folders_are_ever_removed(tmp_path):
    with pytest.raises(transfer.TransferError, match="not Keepsake staging"):
        transfer.remove_staging(str(tmp_path))
    assert tmp_path.exists()


def test_the_rate_cap_paces_bytes():
    now = [0.0]
    slept = []

    async def scenario():
        pace = transfer.RateLimit(1000, clock=lambda: now[0])
        original = asyncio.sleep

        async def fake(seconds):
            slept.append(round(seconds, 3))
            now[0] += seconds

        transfer.asyncio.sleep = fake
        try:
            await pace.take(500)
            await pace.take(1500)
        finally:
            transfer.asyncio.sleep = original

    asyncio.run(scenario())
    assert slept == [0.5, 1.5]
    asyncio.run(transfer.RateLimit(0).take(10**9))  # no cap: no wait


# Manifests


def test_manifest_records_zero_chunks_exclusions_and_never_follows_links(tmp_path):
    source = make_source(tmp_path / "source")
    (source / "logs").mkdir()
    (source / "logs" / "crash.log").write_bytes(b"x")
    built = mf.build(str(source), exclude=lambda rel: rel == "logs")
    paths = [e["path"] for e in built["entries"]]
    assert "logs" not in paths and "logs/crash.log" not in paths
    big = next(e for e in built["entries"] if e["path"] == "data/big.bin")
    assert [mf.is_zero_chunk(h, s) for h, s in zip(big["chunks"], mf.chunk_sizes(big["size"]), strict=True)] == [
        False,
        True,
        False,
    ]
    assert built["root"] == mf.root_hash(built) and mf.validate(built, built["root"]) is built
    assert mf.total_bytes(built) == sum(e.get("size", 0) for e in built["entries"])


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda m: m["entries"].append({**m["entries"][0], "path": m["entries"][0]["path"].upper()}), "case"),
        (lambda m: m["entries"].append({"path": "../escape", "type": "dir", "mode": 0, "mtime": 0}), "clean path"),
        (lambda m: m["entries"].append({"path": "/abs", "type": "dir", "mode": 0, "mtime": 0}), "relative"),
        (lambda m: m["entries"].append({"path": "C:/x", "type": "dir", "mode": 0, "mtime": 0}), "relative"),
        (lambda m: m["entries"].append({"path": "lonely/file", "type": "dir", "mode": 0, "mtime": 0}), "parent"),
        (
            lambda m: m["entries"].append({"path": "out", "type": "link", "target": "../../x", "mode": 0, "mtime": 0}),
            "outside",
        ),
        (
            lambda m: m["entries"].append({"path": "abs", "type": "link", "target": "/etc", "mode": 0, "mtime": 0}),
            "outside",
        ),
        (lambda m: m["entries"].append({"path": "dev", "type": "fifo", "mode": 0, "mtime": 0}), "not valid"),
        (
            lambda m: m["entries"][0].update(size=10**9)
            if m["entries"][0]["type"] == "file"
            else m["entries"].append(
                {"path": "f", "type": "file", "size": 9 * mf.CHUNK, "chunks": [], "mode": 0, "mtime": 0}
            ),
            "chunk list",
        ),
    ],
)
def test_manifest_validation_refuses(tmp_path, change, message):
    built = mf.build(str(make_source(tmp_path / "source", big=False)))
    change(built)
    with pytest.raises(mf.ManifestError, match=message):
        mf.validate(built, mf.root_hash(built))


def test_manifest_entries_under_a_link_are_refused(tmp_path):
    built = mf.build(str(make_source(tmp_path / "source", big=False)))
    built["entries"] += [
        {"path": "data/link", "type": "link", "target": "levels", "mode": 0, "mtime": 0},
        {"path": "data/link/inner", "type": "dir", "mode": 0, "mtime": 0},
    ]
    with pytest.raises(mf.ManifestError, match="under a link"):
        mf.validate(built, mf.root_hash(built))


def test_names_windows_cannot_store_are_refused_for_a_windows_target(tmp_path):
    for name in ("CON", "aux.txt", "a:b", "trailing.", "q?"):
        with pytest.raises(mf.ManifestError, match="Windows"):
            mf.check_path(f"data/{name}", windows=True)
    assert mf.check_path("data/fine.txt", windows=True) == "data/fine.txt"
    assert mf.check_path("data/aux.txt") == "data/aux.txt"  # fine on Linux


def test_the_journal_round_trips_and_ignores_damage(tmp_path):
    job = transfer.Job("j", PEER, "s", "r" * 64, str(tmp_path / "T"), done={"a": [2, 0, 2]}, rate_limit=5)
    again = transfer.Job.from_journal(job.journal())
    assert again.done == {"a": [0, 2]} and again.rate_limit == 5 and again.target == job.target
    os.makedirs(job.staging)
    with open(os.path.join(job.staging, "journal.json"), "w") as handle:
        handle.write("{broken")
    assert transfer.load_journal(job.staging) is None


def test_data_is_made_durable_before_the_journal_lists_it(tmp_path, monkeypatch):
    _, shares, share = offer(tmp_path)
    flushed = set()
    listed = {}
    checked = []
    real_fsync, real_save = transfer._fsync, transfer.save_journal

    def fsync(path):
        flushed.add(os.path.basename(path))
        real_fsync(path)

    def save(job, done=None):
        for rel, chunks in (job.done if done is None else done).items():
            if len(chunks) > listed.get(rel, 0):  # this journal lists new chunks of rel ...
                assert rel.rsplit("/", 1)[-1] in flushed, f"{rel} journaled before it was flushed"
                checked.append(rel)
            listed[rel] = len(chunks)
        flushed.clear()  # ... and each journal needs its own flushes
        real_save(job, done)

    monkeypatch.setattr(transfer, "_fsync", fsync)
    monkeypatch.setattr(transfer, "save_journal", save)
    monkeypatch.setattr(transfer, "JOURNAL_EVERY_CHUNKS", 1)
    job, _ = receive(job_for(share, tmp_path / "Game"), shares)
    assert job.state == "done" and set(checked) == {"bin/game.exe", "data/big.bin", "data/levels/one.pak"}


def test_stop_and_remove_after_a_cut_promote_puts_the_old_target_back(tmp_path, monkeypatch):
    _, shares, share = offer(tmp_path)
    target = tmp_path / "Game"
    target.mkdir()
    (target / "keep.txt").write_bytes(b"the version before")
    real_replace = os.replace
    calls = []

    def crash_on_second(src, dst):
        calls.append(1)
        if len(calls) == 2:
            raise asyncio.CancelledError
        return real_replace(src, dst)

    monkeypatch.setattr(transfer, "_rename", crash_on_second)
    job = job_for(share, target)
    with pytest.raises(asyncio.CancelledError):
        receive(job, shares)
    assert not target.exists()  # the old copy is only under staging now
    transfer.stop_and_remove(job)
    assert (target / "keep.txt").read_bytes() == b"the version before"
    assert not os.path.exists(job.staging)


def test_a_manifest_is_checked_against_the_offered_root(tmp_path):
    built = mf.build(str(make_source(tmp_path / "source", big=False)))
    with pytest.raises(mf.ManifestError, match="does not match"):
        mf.validate(built, "0" * 64)


def test_an_error_frame_is_a_refusal_not_a_dropped_connection():
    async def scenario():
        reader = asyncio.StreamReader()
        body = b'{"type":"error","reason":"that folder is not offered to this device"}'
        reader.feed_data(len(body).to_bytes(4, "big") + body)
        with pytest.raises(Refused, match="not offered"):
            await link.read_frame(reader, timeout=1)

    asyncio.run(scenario())


def test_promote_waits_out_a_brief_windows_sharing_violation(tmp_path, monkeypatch):
    calls = []

    def busy_twice(src, dst):
        calls.append(src)
        if len(calls) <= 2:
            raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(transfer, "_rename", busy_twice)
    monkeypatch.setattr(transfer, "RENAME_PAUSE", 0.0)
    monkeypatch.setattr(transfer.os, "name", "nt")
    transfer._rename_settled("a", "b")
    assert len(calls) == 3
    calls.clear()
    monkeypatch.setattr(transfer.os, "name", "posix")  # elsewhere a refusal is real: no waiting
    with pytest.raises(PermissionError):
        transfer._rename_settled("a", "b")
    assert len(calls) == 1
