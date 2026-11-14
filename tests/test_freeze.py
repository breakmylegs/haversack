import json
import os
import subprocess
import sys
import threading
import time

import pytest

from helpers import write_fake_proc
from keepsake.freeze import FROZEN_FILE, SIGCONT, SIGSTOP, Freezer
from keepsake.procs import read_proc


class FakeKill:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on or {}
        self.lock = threading.Lock()

    def __call__(self, pid, sig):
        with self.lock:
            self.calls.append((pid, sig))
        exc = self.fail_on.get((pid, sig))
        if exc:
            raise exc


def procs(root, *pids, starttime=1000):
    out = []
    for pid in pids:
        write_fake_proc(root, pid, 1, f"p{pid}", starttime=starttime)
        out.append(read_proc(pid, root))
    return out


def test_persists_before_stopping(tmp_path):
    proc_root = str(tmp_path / "proc")
    runtime = tmp_path / "rt"
    runtime.mkdir()
    seen_on_disk = []

    def kill(pid, sig):
        seen_on_disk.append(json.loads((runtime / FROZEN_FILE).read_text()))

    freezer = Freezer(str(runtime), proc_root=proc_root, kill=kill)
    freezer.freeze(procs(proc_root, 10, 11))
    assert seen_on_disk[0] == [{"pid": 10, "starttime": 1000}, {"pid": 11, "starttime": 1000}]
    freezer.resume_all()


def test_freeze_then_resume_clears_record(tmp_path):
    proc_root = str(tmp_path / "proc")
    kill = FakeKill()
    freezer = Freezer(str(tmp_path), proc_root=proc_root, kill=kill)
    assert freezer.freeze(procs(proc_root, 10, 11)) == [10, 11]
    assert freezer.resume_all() == [11, 10]
    assert kill.calls == [(10, SIGSTOP), (11, SIGSTOP), (11, SIGCONT), (10, SIGCONT)]
    assert freezer.recorded() == []
    assert freezer.status()["watchdogArmed"] is False


def test_watchdog_releases_without_explicit_resume(tmp_path):
    proc_root = str(tmp_path / "proc")
    kill = FakeKill()
    freezer = Freezer(str(tmp_path), proc_root=proc_root, kill=kill, ceiling=0.2)
    freezer.freeze(procs(proc_root, 10))
    deadline = time.monotonic() + 3
    while (10, SIGCONT) not in kill.calls and time.monotonic() < deadline:
        time.sleep(0.02)
    assert (10, SIGCONT) in kill.calls
    assert freezer.recorded() == []


def test_ceiling_cannot_exceed_hard_limit(tmp_path):
    freezer = Freezer(str(tmp_path), kill=FakeKill(), ceiling=999)
    assert freezer._ceiling == 30.0


def test_reused_pid_is_not_resumed(tmp_path):
    proc_root = str(tmp_path / "proc")
    kill = FakeKill()
    freezer = Freezer(str(tmp_path), proc_root=proc_root, kill=kill)
    freezer.freeze(procs(proc_root, 10, starttime=1000))
    # Process 10 exits and the PID is reused by something else.
    write_fake_proc(proc_root, 10, 1, "unrelated", starttime=5000)
    assert freezer.resume_all() == []
    assert (10, SIGCONT) not in kill.calls


def test_startup_recovery_from_disk(tmp_path):
    proc_root = str(tmp_path / "proc")
    procs(proc_root, 10)
    (tmp_path / FROZEN_FILE).write_text(json.dumps([{"pid": 10, "starttime": 1000}]))
    kill = FakeKill()
    assert Freezer(str(tmp_path), proc_root=proc_root, kill=kill).resume_all("startup") == [10]


def test_corrupt_state_file_still_resumes_from_memory(tmp_path):
    proc_root = str(tmp_path / "proc")
    kill = FakeKill()
    freezer = Freezer(str(tmp_path), proc_root=proc_root, kill=kill)
    freezer.freeze(procs(proc_root, 10))
    (tmp_path / FROZEN_FILE).write_text("{not json")
    assert freezer.resume_all() == [10]


def test_fails_closed_when_state_cannot_be_written(tmp_path, monkeypatch):
    proc_root = str(tmp_path / "proc")
    kill = FakeKill()
    freezer = Freezer(str(tmp_path), proc_root=proc_root, kill=kill)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("keepsake.freeze.atomic_write_json", boom)
    assert freezer.freeze(procs(proc_root, 10)) == []
    assert not [c for c in kill.calls if c[1] == SIGSTOP]


def test_resume_failure_keeps_record_and_rearms(tmp_path):
    proc_root = str(tmp_path / "proc")
    kill = FakeKill(fail_on={(10, SIGCONT): PermissionError()})
    freezer = Freezer(str(tmp_path), proc_root=proc_root, kill=kill, ceiling=5)
    freezer.freeze(procs(proc_root, 10))
    assert freezer.resume_all() == []
    assert freezer.recorded() == [{"pid": 10, "starttime": 1000}]
    assert freezer.status()["watchdogArmed"] is True
    kill.fail_on.clear()
    assert freezer.resume_all() == [10]


def test_vanished_process_is_skipped(tmp_path):
    proc_root = str(tmp_path / "proc")
    kill = FakeKill(fail_on={(10, SIGSTOP): ProcessLookupError()})
    freezer = Freezer(str(tmp_path), proc_root=proc_root, kill=kill)
    assert freezer.freeze(procs(proc_root, 10, 11)) == [11]
    freezer.resume_all()


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs real /proc and signals")
def test_real_process_is_stopped_and_released_by_watchdog(tmp_path):
    child = subprocess.Popen(["sleep", "30"])
    try:
        info = read_proc(child.pid)
        assert info is not None
        freezer = Freezer(str(tmp_path), ceiling=0.5)
        freezer.freeze([info])
        time.sleep(0.1)
        assert _state(child.pid) == "T"
        deadline = time.monotonic() + 5
        while _state(child.pid) == "T" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _state(child.pid) in ("S", "R")
    finally:
        child.kill()
        child.wait()


def _state(pid):
    with open(f"/proc/{pid}/stat") as handle:
        text = handle.read()
    return text[text.rfind(")") + 2]


def test_signal_constants_exist():
    assert SIGSTOP != SIGCONT
    assert os.path.basename(FROZEN_FILE) == FROZEN_FILE
