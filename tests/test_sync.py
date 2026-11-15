import pytest

from keepsake.snapshot import SnapshotError
from sim import GAME, make_pair


def play(device, changes):
    device.launch()
    device.write(changes)
    return device.exit()


def test_first_push_then_other_device_adopts_by_restoring(tmp_path):
    a, b, _ = make_pair(tmp_path)
    assert a.launch()["reason"] == "no-cloud-snapshots"
    a.write({"slot1.sav": b"a1"})
    assert a.exit()["status"] == "published"
    assert b.launch()["action"] == "restored"  # B had no files: adopt by restoring
    assert b.files() == {"slot1.sav": b"a1"}
    assert b.exit()["status"] == "no-change"
    assert b.launch()["reason"] == "up-to-date"


def test_pull_and_push_between_devices_with_skewed_clocks(tmp_path):
    a, b, clock = make_pair(tmp_path)
    play(a, {"slot1.sav": b"a1"})
    b.launch()
    b.exit()
    clock.tick()
    assert play(b, {"slot1.sav": b"b2"})["status"] == "published"  # B's clock is days behind; hashes decide
    assert a.launch()["action"] == "restored"
    assert a.files() == {"slot1.sav": b"b2"}
    a.write({"slot1.sav": b"a3"})
    a.exit()
    assert b.launch()["action"] == "restored" and b.files() == {"slot1.sav": b"a3"}


def test_adoption_with_equal_files_is_silent(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"same"})
    b.write({"s.sav": b"same"})
    assert b.launch() == {"action": "launch", "reason": "adopted"}
    assert b.sync.status(GAME)["base"] == a.sync.status(GAME)["base"]


def test_adoption_with_different_files_is_a_conflict(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"from a"})
    b.write({"s.sav": b"from b"})
    result = b.launch()
    assert result["action"] == "conflict" and result["conflict"]["kind"] == "adoption"
    assert b.files() == {"s.sav": b"from b"}  # nothing overwritten


def test_both_changed_conflict_use_cloud_keeps_local_pinned(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    b.launch()
    b.exit()
    play(a, {"s.sav": b"a2"})
    b.write({"s.sav": b"b2"})  # B changed offline from the game, not via a session
    conflict = b.launch()
    assert conflict["conflict"]["kind"] == "both-changed"
    b.running = False
    result = b.sync.resolve(b.ctx, "use-cloud")
    assert b.files() == {"s.sav": b"a2"}
    pins = {p["snapId"] for p in b.engine.pins(GAME)}
    assert result["keptLocal"] in pins
    kept = b.engine.get_meta(GAME, result["keptLocal"])
    assert kept["flags"] == ["conflict-loser"]
    assert b.sync.status(GAME)["conflict"] is None
    # The kept copy made a second head; the merge closes it so the next launches are clean.
    assert b.launch()["reason"] == "up-to-date"
    assert a.launch()["action"] in ("launch", "restored") and a.files() == {"s.sav": b"a2"}


def test_use_cloud_never_loses_an_unsynced_local_edit(tmp_path):
    import hashlib
    import json

    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    b.launch()
    b.exit()
    play(a, {"s.sav": b"a2"})
    b.write({"s.sav": b"b2"})
    b.launch()  # both changed: conflict
    b.running = False
    b.write({"s.sav": b"b3 unsynced"})  # more progress before choosing
    b.sync.resolve(b.ctx, "use-cloud")
    wanted = hashlib.sha256(b"b3 unsynced").hexdigest()
    in_cloud = any(
        f["sha256"] == wanted
        for info in b.engine.store.inner.list(f"games/{GAME}/snapshots/")
        for f in json.loads(b.engine.store.inner.get(info.key))["files"]
    )
    in_prerestore = any(f["sha256"] == wanted for r in b.engine.prerestore.list(GAME) for f in r["meta"]["files"])
    assert in_cloud and in_prerestore  # kept twice: pinned in the cloud and locally before the restore


def test_both_changed_use_local_makes_merge_with_all_heads_and_pins_losers(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    b.launch()
    b.exit()
    play(a, {"s.sav": b"a2"})
    a_head = a.sync.status(GAME)["base"]
    b.write({"s.sav": b"b2"})
    b.launch()
    b.running = False
    result = b.sync.resolve(b.ctx, "use-local")
    merge = b.engine.get_meta(GAME, result["used"])
    assert merge["kind"] == "merge" and merge["parents"] == [a_head]
    assert a_head in {p["snapId"] for p in b.engine.pins(GAME)}
    assert a.launch()["action"] == "restored" and a.files() == {"s.sav": b"b2"}


def test_fork_when_both_devices_play_from_the_same_base(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    play(b, {})
    a.launch()
    b.launch()
    a.write({"s.sav": b"a2"})
    b.write({"s.sav": b"b2"})
    assert a.exit()["status"] == "published"
    assert b.exit()["status"] == "published-fork"
    assert b.sync.status(GAME)["conflict"]["kind"] == "fork"
    assert len(b.sync.status(GAME)["conflict"]["heads"]) == 2
    # A now sees the fork too.
    assert a.launch()["conflict"]["kind"] == "fork"
    a.running = False
    a_heads = [h["snapId"] for h in a.sync.status(GAME)["conflict"]["heads"]]
    b_head = b.sync.status(GAME)["base"]
    a.sync.resolve(a.ctx, "use-cloud", head=b_head)
    assert a.files() == {"s.sav": b"b2"}
    pinned = {p["snapId"] for p in a.engine.pins(GAME)}
    assert all(h in pinned for h in a_heads if h != b_head)  # the losing head is kept
    # The fork is closed: one head, and both devices launch without a conflict.
    assert a.launch()["reason"] == "up-to-date"
    assert b.sync.resolve(b.ctx, "decide-later")["status"] == "deferred"
    b.sync.state.update(GAME, conflict=None)
    b.running = False
    assert b.launch()["action"] in ("launch", "restored")


def test_decide_later_plays_local_and_pushes_a_fork(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"a"})
    b.write({"s.sav": b"b"})
    b.launch()  # adoption conflict
    b.exit()
    assert b.sync.resolve(b.ctx, "decide-later")["status"] == "deferred"
    again = b.launch()
    assert again["action"] == "launch" and "conflict" in again  # auto-pull stays off
    b.write({"s.sav": b"b more"})
    assert b.exit()["status"] in ("published", "published-fork")
    assert b.files() == {"s.sav": b"b more"}
    assert b.sync.status(GAME)["conflict"] is not None


def test_offline_launch_then_reconcile(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    play(b, {})
    b.online = False
    assert b.launch() == {"action": "launch", "pending": True}
    b.write({"s.sav": b"b offline"})
    assert b.exit()["status"] == "pending"
    b.online = True
    result = b.sync.idle(b.ctx)
    assert result["status"] == "ok" and result["push"] == "published"
    assert a.launch()["action"] == "restored" and a.files() == {"s.sav": b"b offline"}


def test_offline_reconcile_raises_conflict_when_cloud_also_moved(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    play(b, {})
    b.online = False
    b.launch()
    b.write({"s.sav": b"b offline"})
    b.exit()
    play(a, {"s.sav": b"a online"})
    b.online = True
    assert b.sync.idle(b.ctx)["status"] == "conflict"
    assert b.files() == {"s.sav": b"b offline"}


def test_push_racing_pull_loses_nothing(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    play(b, {})
    b.write({"s.sav": b"b2"})
    a.write({"s.sav": b"a2"})

    def a_pushes():
        a.sync.push(a.ctx)

    b.store.before_list = a_pushes  # A publishes while B is checking heads before its own push
    result = b.sync.push(b.ctx)
    assert result["status"] == "published-fork"
    versions = {f["sha256"] for m in b.engine.list_metas(GAME) for f in m["files"]}
    import hashlib

    assert {hashlib.sha256(b"a2").hexdigest(), hashlib.sha256(b"b2").hexdigest()} <= versions


def test_cloud_newer_while_game_already_running_is_not_restored(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    play(b, {})
    play(a, {"s.sav": b"v2"})
    b.running = True  # could not be frozen in time
    result = b.sync.pull(b.ctx)
    assert result["reason"] == "cloud-newer-game-running" and b.files() == {"s.sav": b"v1"}


def test_crash_recovery_pushes_open_session(tmp_path):
    a, _, _ = make_pair(tmp_path)
    a.launch()
    a.write({"s.sav": b"progress"})
    a.running = False  # Steam was killed: no exit event
    result = a.sync.recover_session(a.ctx)
    assert result["status"] == "published"
    meta = a.engine.get_meta(GAME, result["snapId"])
    assert meta["kind"] == "auto-recovered"
    assert a.sync.recover_session(a.ctx) is None


def test_prefetch_makes_launch_restore_local(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    play(b, {})
    play(a, {"s.sav": b"v2"})
    assert len(b.sync.prefetch(b.ctx)) == 1
    downloads = b.downloads
    assert b.launch()["action"] == "restored"
    assert b.downloads == downloads  # restored from staging
    assert b.files() == {"s.sav": b"v2"}


def test_resolve_needs_the_game_closed(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"a"})
    b.write({"s.sav": b"b"})
    b.launch()
    with pytest.raises(SnapshotError, match="quit"):
        b.sync.resolve(b.ctx, "use-local")


def test_bases_published_and_protected_by_retention(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    b.launch()
    b.exit()
    bases = a.engine.cloud_bases(GAME)
    assert set(bases.values()) == {a.sync.status(GAME)["base"]}
    assert len(bases) == 2
