"""The setup wizard's dry run and the conflict modal's details (slice 9).

Every plan must match what the real decision table then does, and must not
change any state.
"""

import os

from keepsake.snapshot import FileEntry
from keepsake.sync import changed_files
from sim import GAME, make_pair


def state_bytes(device):
    path = os.path.join(os.path.dirname(device.sync._staging), "sync-state.json")
    return open(path, "rb").read() if os.path.exists(path) else None


def plan(device):
    before = state_bytes(device)
    result = device.sync.plan(device.ctx)
    assert state_bytes(device) == before  # a dry run never writes state
    return result


def play(device, changes):
    device.launch()
    device.write(changes)
    return device.exit()


def test_first_device_with_and_without_files(tmp_path):
    a, _, _ = make_pair(tmp_path)
    assert plan(a) == {"action": "nothing"}
    a.write({"s.sav": b"a1"})
    assert plan(a)["action"] == "push"
    a.launch()
    assert a.exit()["status"] == "published"


def test_second_device_pull_adopt_or_conflict(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"a1"})
    assert plan(b) == {"action": "pull", "reason": "no-local-files"}
    b.write({"s.sav": b"a1"})
    assert plan(b)["action"] == "adopt"
    assert b.launch()["reason"] == "adopted"


def test_second_device_with_different_files_plans_a_conflict(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"a1"})
    b.write({"s.sav": b"b1"})
    assert plan(b) == {"action": "conflict", "reason": "adoption"}
    assert b.launch()["action"] == "conflict"
    assert plan(b) == {"action": "conflict", "reason": "open-conflict"}


def test_synced_devices_pull_push_up_to_date_converged_and_both_changed(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    b.launch()
    b.exit()
    assert plan(b)["action"] == "up-to-date"
    b.write({"s.sav": b"b-only"})
    assert plan(b)["action"] == "push"
    b.write({"s.sav": b"v1"})
    play(a, {"s.sav": b"a2"})
    assert plan(b)["action"] == "pull"
    b.write({"s.sav": b"a2"})
    assert plan(b) == {"action": "adopt", "reason": "converged"}
    b.write({"s.sav": b"b2"})
    assert plan(b) == {"action": "conflict", "reason": "both-changed"}
    assert b.launch()["conflict"]["kind"] == "both-changed"


def test_offline_plan(tmp_path):
    a, _, _ = make_pair(tmp_path)
    a.online = False
    assert plan(a) == {"action": "offline"}


def test_conflict_details_counts_changes_since_the_base(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1", "keep.sav": b"same"})
    b.launch()
    b.exit()
    play(a, {"s.sav": b"a2"})  # one file changed on A
    b.write({"s.sav": b"b2", "new.sav": b"b"})  # one changed and one added on B
    b.launch()
    details = b.sync.conflict_details(b.ctx)
    assert details["hasBase"] is True and details["conflict"]["kind"] == "both-changed"
    local, cloud = details["sides"]
    assert local["side"] == "local" and local["files"] == 3 and local["changedFiles"] == 2
    assert cloud["side"] == "cloud" and cloud["files"] == 2 and cloud["changedFiles"] == 1
    assert cloud["device"] == "aaaaaa" and cloud["created"]


def test_conflict_details_without_a_conflict(tmp_path):
    a, _, _ = make_pair(tmp_path)
    assert a.sync.conflict_details(a.ctx) == {"conflict": None}
    assert a.sync.status(GAME).get("conflict") is None


def test_changed_files_counts_added_removed_and_changed():
    before = [FileEntry("r", "a", 1, "x"), FileEntry("r", "b", 1, "y"), FileEntry("r", "c", 1, "z")]
    after = [FileEntry("r", "a", 1, "x"), FileEntry("r", "b", 2, "y2"), FileEntry("r", "d", 1, "w")]
    assert changed_files(before, after) == 3  # b changed, c removed, d added
    assert changed_files([], after) == 3
    assert changed_files(before, before) == 0
