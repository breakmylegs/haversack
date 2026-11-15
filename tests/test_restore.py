import json
import os

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from helpers import files_in, tree_state, write_tree
from keepsake import restore, snapshot
from keepsake.restore import RestoreError

DEVICE = "abcdef00-0000-0000-0000-000000000000"
ROOT_NAMES = ("winLocalAppData", "base")


class Crash(BaseException):
    """Simulates a power cut: not caught by restore()'s in-process rollback."""


def make_roots(base):
    roots = {name: str(base / name) for name in ROOT_NAMES}
    for path in roots.values():
        os.makedirs(path, exist_ok=True)
    return roots


def snap(roots, out):
    entries = snapshot.scan_entries(files_in(roots), roots)
    sha = snapshot.pack(entries, roots, out)
    return snapshot.build_meta(
        game_key="g",
        entries=entries,
        parents=[],
        device_id=DEVICE,
        device_name="d",
        device_seq=1,
        kind="manual",
        blob_sha256=sha,
        plugin_version="t",
    )


def reset(roots, state):
    for path in roots.values():
        for folder, dirs, files in os.walk(path, topdown=False):
            for f in files:
                os.unlink(os.path.join(folder, f))
            for d in dirs:
                os.rmdir(os.path.join(folder, d))
    write_tree(roots, state)


def current(roots):
    return snapshot.scan_entries(files_in(roots), roots)


def test_plan():
    a = snapshot.FileEntry("base", "a", 1, "0" * 64)
    b = snapshot.FileEntry("base", "b", 1, "1" * 64)
    b2 = snapshot.FileEntry("base", "b", 1, "2" * 64)
    c = snapshot.FileEntry("base", "c", 1, "3" * 64)
    ops = restore.plan([a, b], [b2, c])
    assert [(o["rel"], o["action"]) for o in ops] == [("b", "replace"), ("c", "create"), ("a", "delete")]
    assert restore.plan([a], [a]) == []


def test_restore_round_trip_and_cleanup(tmp_path):
    roots = make_roots(tmp_path / "roots")
    original = {("base", "save/one.sav"): b"1", ("winLocalAppData", "Game/two.sav"): b"22"}
    write_tree(roots, original)
    blob = str(tmp_path / "s.zip")
    meta = snap(roots, blob)
    reset(roots, {("base", "save/one.sav"): b"changed", ("base", "save/new.sav"): b"n"})
    result = restore.restore(blob, meta, current(roots), roots, str(tmp_path / "rt"))
    assert result == {"changed": 3, "created": 1, "replaced": 1, "deleted": 1}
    assert tree_state(roots) == original
    leftovers = [d for p in roots.values() for d in os.listdir(p) if d.startswith(".keepsake-")]
    assert leftovers == []
    assert os.listdir(tmp_path / "rt" / restore.JOURNAL_DIR) == []


def test_file_present_but_unscanned_is_backed_up_not_lost(tmp_path):
    roots = make_roots(tmp_path / "roots")
    write_tree(roots, {("base", "keep.cfg"): b"from snapshot"})
    blob = str(tmp_path / "s.zip")
    meta = snap(roots, blob)
    reset(roots, {("base", "keep.cfg"): b"local only, hidden by an exclusion"})

    def crash(stage, index):
        if stage == "placed":
            raise Crash

    with pytest.raises(Crash):
        restore.restore(blob, meta, [], roots, str(tmp_path / "rt"), hook=crash)  # scan saw nothing
    restore.recover(str(tmp_path / "rt"))
    assert tree_state(roots) == {("base", "keep.cfg"): b"local only, hidden by an exclusion"}


names = st.text(alphabet="abcxyz019_-", min_size=1, max_size=6)
rels = st.lists(names, min_size=1, max_size=3).map("/".join)
states = st.dictionaries(st.tuples(st.sampled_from(ROOT_NAMES), rels), st.binary(max_size=64), max_size=8)


def consistent(state):
    """Drop entries where one path is a folder of another (a file cannot also be a folder)."""
    keys = sorted(state)
    out = {}
    for root, rel in keys:
        if any(r == root and (rel.startswith(o + "/") or o.startswith(rel + "/")) for r, o in out):
            continue
        out[(root, rel)] = state[(root, rel)]
    return out


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
)
@given(old=states, new=states)
# Counterexample found during slice 5 (a file becoming a folder); always run it.
@example(old={("winLocalAppData", "0"): b""}, new={("winLocalAppData", "0/0"): b""})
@example(old={("winLocalAppData", "0/0"): b""}, new={("winLocalAppData", "0"): b""})
def test_property_restore_reproduces_scanned_state(tmp_path_factory, old, new):
    old, new = consistent(old), consistent(new)
    base = tmp_path_factory.mktemp("prop")
    roots = make_roots(base / "roots")
    write_tree(roots, new)
    blob = str(base / "s.zip")
    meta = snap(roots, blob)
    reset(roots, old)
    restore.restore(blob, meta, current(roots), roots, str(base / "rt"))
    assert tree_state(roots) == new
    assert snapshot.content_hash(current(roots)) == meta["contentHash"]


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
)
@given(old=states, new=states, crash_at=st.integers(min_value=0, max_value=40))
def test_property_interrupted_restore_is_old_or_new_never_mixed(tmp_path_factory, old, new, crash_at):
    old, new = consistent(old), consistent(new)
    base = tmp_path_factory.mktemp("crash")
    roots = make_roots(base / "roots")
    runtime = str(base / "rt")
    write_tree(roots, new)
    blob = str(base / "s.zip")
    meta = snap(roots, blob)
    reset(roots, old)
    steps = []

    def hook(stage, index):
        steps.append(stage)
        if len(steps) - 1 == crash_at:
            raise Crash

    try:
        restore.restore(blob, meta, current(roots), roots, runtime, hook=hook)
        crashed_after_commit = None
    except Crash:
        crashed_after_commit = steps[-1] == "committed"
    restore.recover(runtime)
    state = tree_state(roots)
    if crashed_after_commit:
        assert state == new
    elif crashed_after_commit is False:
        assert state == old
    else:
        assert state == new
    leftovers = [d for p in roots.values() for d in os.listdir(p) if d.startswith(".keepsake-")]
    assert leftovers == []


def test_ordinary_error_mid_commit_rolls_back_immediately(tmp_path):
    roots = make_roots(tmp_path / "roots")
    write_tree(roots, {("base", "a.sav"): b"new", ("base", "b.sav"): b"new"})
    blob = str(tmp_path / "s.zip")
    meta = snap(roots, blob)
    old = {("base", "a.sav"): b"old", ("base", "c.sav"): b"old"}
    reset(roots, old)

    def fail(stage, index):
        if stage == "placed" and index == 1:
            raise OSError("disk full")

    with pytest.raises(OSError):
        restore.restore(blob, meta, current(roots), roots, str(tmp_path / "rt"), hook=fail)
    assert tree_state(roots) == old  # no recover() needed
    assert os.listdir(tmp_path / "rt" / restore.JOURNAL_DIR) == []


def test_file_becomes_folder_and_back(tmp_path):
    roots = make_roots(tmp_path / "roots")
    for old, new in (
        ({("base", "x"): b"file"}, {("base", "x/inner"): b"nested"}),
        ({("base", "x/inner"): b"nested"}, {("base", "x"): b"file"}),
    ):
        write_tree(roots, new)
        blob = str(tmp_path / "s.zip")
        meta = snap(roots, blob)
        reset(roots, old)
        restore.restore(blob, meta, current(roots), roots, str(tmp_path / "rt"))
        assert tree_state(roots) == new
        reset(roots, {})


@pytest.mark.parametrize("crash_stage", ["placed", "moved-aside"])
def test_crash_after_file_became_folder_recovers_old_state(tmp_path, crash_stage):
    roots = make_roots(tmp_path / "roots")
    old = {("base", "x"): b"file", ("base", "y"): b"keep"}
    new = {("base", "x/inner"): b"nested", ("base", "y"): b"changed"}
    write_tree(roots, new)
    blob = str(tmp_path / "s.zip")
    meta = snap(roots, blob)
    reset(roots, old)
    seen = []

    def crash(stage, index):
        seen.append(stage)
        if stage == crash_stage and seen.count(crash_stage) == 3:
            raise Crash

    with pytest.raises(Crash):
        restore.restore(blob, meta, current(roots), roots, str(tmp_path / "rt"), hook=crash)
    restore.recover(str(tmp_path / "rt"))
    assert tree_state(roots) == old


def test_folder_with_unmanaged_files_is_refused(tmp_path):
    roots = make_roots(tmp_path / "roots")
    write_tree(roots, {("base", "x"): b"file"})
    blob = str(tmp_path / "s.zip")
    meta = snap(roots, blob)
    reset(roots, {("base", "x/unscanned.log"): b"keep me"})
    with pytest.raises(RestoreError, match="in the way"):
        restore.restore(blob, meta, [], roots, str(tmp_path / "rt"))
    assert tree_state(roots) == {("base", "x/unscanned.log"): b"keep me"}


def test_recover_refuses_unreadable_journal(tmp_path):
    folder = tmp_path / restore.JOURNAL_DIR
    folder.mkdir()
    (folder / "x.json").write_text("{broken")
    with pytest.raises(RestoreError, match="left untouched"):
        restore.recover(str(tmp_path))
    (folder / "x.json").write_text(json.dumps({"no": "ops"}))
    with pytest.raises(RestoreError):
        restore.recover(str(tmp_path))


def test_restore_refuses_missing_root(tmp_path):
    roots = make_roots(tmp_path / "roots")
    write_tree(roots, {("base", "a"): b"1"})
    blob = str(tmp_path / "s.zip")
    meta = snap(roots, blob)
    with pytest.raises(RestoreError, match="not available"):
        restore.restore(
            blob, meta, [], {"base": None, "winLocalAppData": roots["winLocalAppData"]}, str(tmp_path / "rt")
        )
