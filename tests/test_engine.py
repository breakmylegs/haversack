import json
import os

import pytest

from helpers import files_in, tree_state, write_tree
from keepsake import engine as engine_mod
from keepsake.engine import SnapshotEngine, blob_key, pin_key, pruned_key, snapshot_key
from keepsake.snapshot import NewerSchemaError, SnapshotError
from keepsake.store import LocalFolderStore

GAME = "example-game"
DEVICE = "abc12300-0000-0000-0000-000000000000"


class Clock:
    def __init__(self):
        self.now = 2_000_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    roots = {"winLocalAppData": str(tmp_path / "roots" / "local"), "base": str(tmp_path / "roots" / "base")}
    for path in roots.values():
        os.makedirs(path)
    store = LocalFolderStore(str(tmp_path / "cloud"))
    clock = Clock()
    eng = SnapshotEngine(
        store, str(tmp_path / "rt"), str(tmp_path / "settings"), DEVICE, "Handheld", "0.5.0", clock=clock
    )
    os.makedirs(tmp_path / "settings", exist_ok=True)
    return eng, store, roots, clock


def take(eng, roots, base=None, kind="auto-exit"):
    return eng.take(GAME, files_in(roots), roots, kind, base)


def test_take_publishes_blob_then_meta_and_detects_no_change(setup):
    eng, store, roots, _ = setup
    write_tree(roots, {("winLocalAppData", "Game/s1.sav"): b"one"})
    first = take(eng, roots)
    assert first["status"] == "published"
    snap_id = first["snapId"]
    assert snap_id.startswith("000001-abc123-")
    keys = [o.key for o in store.list()]
    assert blob_key(GAME, snap_id) in keys and snapshot_key(GAME, snap_id) in keys
    assert take(eng, roots, base=first["meta"])["status"] == "no-change"
    write_tree(roots, {("winLocalAppData", "Game/s2.sav"): b"two"})
    second = take(eng, roots, base=first["meta"])
    assert second["meta"]["parents"] == [snap_id]
    assert [m["snapId"] for m in eng.list_metas(GAME)] == [snap_id, second["snapId"]]


def test_nothing_to_save_without_base(setup):
    eng, _, roots, _ = setup
    assert take(eng, roots)["status"] == "nothing-to-save"


def test_gate_refusal_quarantines_and_never_uploads(setup):
    eng, store, roots, _ = setup
    write_tree(roots, {("base", f"s{i}.sav"): b"x" for i in range(4)})
    base = take(eng, roots)["meta"]
    for i in range(3):
        os.unlink(os.path.join(roots["base"], f"s{i}.sav"))
    refused = take(eng, roots, base=base)
    assert refused["status"] == "quarantined" and "removes 3 of 4" in refused["reasons"][0]
    assert snapshot_key(GAME, refused["snapId"]) not in [o.key for o in store.list()]
    assert [r["meta"]["snapId"] for r in eng.quarantine.list(GAME)] == [refused["snapId"]]
    os.unlink(os.path.join(roots["base"], "s3.sav"))
    empty = take(eng, roots, base=base)
    assert empty["status"] == "quarantined" and "no files left" in empty["reasons"][0]
    assert eng.release_quarantined(GAME, refused["snapId"], confirmed=False)["status"] == "needs-confirmation"
    assert eng.release_quarantined(GAME, refused["snapId"], confirmed=True)["status"] == "published"
    assert snapshot_key(GAME, refused["snapId"]) in [o.key for o in store.list()]
    assert [r["meta"]["snapId"] for r in eng.quarantine.list(GAME)] == [empty["snapId"]]


def test_restore_takes_verified_prerestore_and_can_be_undone(setup):
    eng, _, roots, clock = setup
    write_tree(roots, {("base", "save.sav"): b"cloud version"})
    snap = take(eng, roots)["snapId"]
    write_tree(roots, {("base", "save.sav"): b"local progress", ("base", "extra.sav"): b"local extra"})
    local_state = tree_state(roots)
    result = eng.restore(GAME, snap, files_in(roots), roots, game_running=False)
    assert result["status"] == "restored" and result["replaced"] == 1 and result["deleted"] == 1
    assert tree_state(roots) == {("base", "save.sav"): b"cloud version"}
    undo = eng.restore_prerestore(GAME, result["prerestore"], files_in(roots), roots, game_running=False)
    assert undo["status"] == "restored"
    assert tree_state(roots) == local_state
    assert eng.restore(GAME, snap, files_in(roots), roots, game_running=False)["status"] == "restored"
    clock.now += 1
    assert eng.restore(GAME, snap, files_in(roots), roots, game_running=False)["status"] == "already-current"


def test_restore_refused_while_game_runs(setup):
    eng, _, roots, _ = setup
    write_tree(roots, {("base", "a"): b"1"})
    snap = take(eng, roots)["snapId"]
    write_tree(roots, {("base", "a"): b"2"})
    with pytest.raises(SnapshotError, match="running"):
        eng.restore(GAME, snap, files_in(roots), roots, game_running=True)
    assert tree_state(roots) == {("base", "a"): b"2"}


def test_prerestore_keeps_five(setup):
    eng, _, roots, clock = setup
    write_tree(roots, {("base", "a"): b"cloud"})
    snap = take(eng, roots)["snapId"]
    for i in range(7):
        clock.now += 60
        write_tree(roots, {("base", "a"): f"local {i}".encode()})
        eng.restore(GAME, snap, files_in(roots), roots, game_running=False)
    assert len(eng.prerestore.list(GAME)) == engine_mod.PRERESTORE_KEEP


def test_corrupt_cloud_blob_is_refused_before_touching_files(setup, tmp_path):
    eng, _, roots, _ = setup
    write_tree(roots, {("base", "a"): b"cloud"})
    snap = take(eng, roots)["snapId"]
    blob_path = os.path.join(str(tmp_path / "cloud"), *blob_key(GAME, snap).split("/"))
    with open(blob_path, "r+b") as handle:
        handle.seek(10)
        handle.write(b"XXXX")
    write_tree(roots, {("base", "a"): b"local"})
    with pytest.raises(SnapshotError):
        eng.restore(GAME, snap, files_in(roots), roots, game_running=False)
    assert tree_state(roots) == {("base", "a"): b"local"}
    assert eng.prerestore.list(GAME) == []


def test_newer_schema_in_cloud_blocks_writes(setup):
    eng, store, roots, _ = setup
    future = {"schemaVersion": 2, "snapId": "000001-ffffff-00000000"}
    store.put_new(snapshot_key(GAME, "000001-ffffff-00000000"), json.dumps(future).encode())
    write_tree(roots, {("base", "a"): b"1"})
    with pytest.raises(NewerSchemaError):
        take(eng, roots)
    assert [o.key for o in store.list(f"games/{GAME}/blobs/")] == []


def test_invalid_cloud_metadata_is_ignored(setup):
    eng, store, roots, _ = setup
    store.put_new(snapshot_key(GAME, "000001-ffffff-00000000"), b"{not json")
    write_tree(roots, {("base", "a"): b"1"})
    take(eng, roots)
    assert len(eng.list_metas(GAME)) == 1


def test_pin_and_retention_apply(setup):
    eng, store, roots, clock = setup
    snaps = []
    base = None
    for i in range(30):
        clock.now += 40 * 86400 if i < 20 else 3600  # 20 old monthly-ish, then 10 recent
        write_tree(roots, {("base", "a"): f"v{i}".encode()})
        result = take(eng, roots, base=base)
        base = result["meta"]
        snaps.append(result["snapId"])
    eng.pin(GAME, snaps[0])
    eng.pin(GAME, snaps[0])  # idempotent
    clock.now += 8 * 86400
    result = eng.apply_retention(GAME, bases={snaps[1]})
    assert result["prune"]
    keys = {o.key for o in store.list()}
    for snap_id in result["prune"]:
        assert pruned_key(GAME, snap_id) in keys
        assert blob_key(GAME, snap_id) not in keys
        assert snapshot_key(GAME, snap_id) in keys  # metadata kept
    for protected in (snaps[0], snaps[1], snaps[-1]):
        assert protected not in result["prune"]
        assert blob_key(GAME, protected) in keys
    assert pin_key(GAME, snaps[0]) in keys
    with pytest.raises(SnapshotError, match="pruned"):
        eng.restore(GAME, result["prune"][0], files_in(roots), roots, game_running=False)


def test_orphan_blobs_deleted_only_after_grace(setup):
    eng, store, roots, clock = setup
    write_tree(roots, {("base", "a"): b"1"})
    take(eng, roots)
    store.put_new(blob_key(GAME, "000099-abc123-deadbeef"), b"orphan")
    assert eng.apply_retention(GAME, set())["orphansDeleted"] == []
    clock.now += engine_mod.ORPHAN_GRACE_SECONDS + 1
    assert eng.apply_retention(GAME, set())["orphansDeleted"] == ["000099-abc123-deadbeef"]


def test_device_seq_is_monotonic_and_persistent(tmp_path):
    seq = engine_mod.DeviceSeq(str(tmp_path))
    assert [seq.next(), seq.next()] == [1, 2]
    assert engine_mod.DeviceSeq(str(tmp_path)).next() == 3
