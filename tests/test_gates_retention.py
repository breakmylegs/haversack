import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from keepsake import gates, retention
from keepsake.snapshot import FileEntry


def files(n, size=10):
    return [FileEntry("base", f"f{i}", size, f"{i:064x}") for i in range(n)]


def test_gates_defaults():
    base = files(10)
    assert gates.check(None, [], {}) == []
    assert gates.check([], files(1), {}) == []
    assert gates.check(base, base, {}) == []
    assert "no files left" in gates.check(base, [], {})[0]
    assert gates.check(base, files(5), {}) == []  # exactly 50% removed passes
    assert "removes 6 of 10" in gates.check(base, files(4), {})[0]
    shrunk = [FileEntry(e.root, e.rel, 2, e.sha256) for e in base]  # 80% smaller
    assert "total size falls" in gates.check(base, shrunk, {})[0]
    slightly = [FileEntry(e.root, e.rel, 3, e.sha256) for e in base]  # exactly 70% smaller
    assert gates.check(base, slightly, {}) == []


def test_gates_can_be_tightened_not_loosened():
    base = files(10)
    assert gates.check(base, files(8), {"gateMaxRemovedPercent": 10}) != []
    assert gates.check(base, files(4), {"gateMaxRemovedPercent": 100}) != []  # clamped to 50
    assert gates.check(base, files(4), {"gateMaxRemovedPercent": True}) != []
    assert gates.clamp_threshold(0, 50) == gates.MIN_PERCENT
    assert gates.clamp_threshold(99, 50) == 50
    assert gates.clamp_threshold("x", 70) == 70


NOW = 2_000_000_000.0


def meta(snap_id, days_ago, kind="auto-exit", parents=(), flags=()):
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - days_ago * 86400))
    return {"snapId": snap_id, "created": created, "kind": kind, "parents": list(parents), "flags": list(flags)}


def chain(n, step_days=1, start_days=400):
    out = []
    for i in range(n):
        parents = [out[-1]["snapId"]] if out else []
        out.append(meta(f"{i:06d}-aaaaaa-{i:08x}", start_days - i * step_days, parents=parents))
    return out


def test_retention_policy_on_a_long_chain():
    metas = chain(400)  # one a day, oldest first, newest is a day old... up to 400 days ago
    result = retention.plan(metas, set(), set(), set(), NOW)
    kept = set(result["keep"])
    head = metas[-1]["snapId"]
    assert result["keep"][head] == "head"
    assert all(m["snapId"] in kept for m in metas if NOW - retention.created_epoch(m) < 7 * 86400)
    assert len([m for m in metas[-10:] if m["snapId"] in kept]) == 10
    daily = [m for m in metas if NOW - retention.created_epoch(m) <= 30 * 86400]
    assert all(m["snapId"] in kept for m in daily)
    assert len(result["prune"]) > 300
    assert set(result["prune"]).isdisjoint(kept)


def test_retention_never_prunes_protected_kinds_pins_and_bases():
    metas = chain(60, start_days=200)
    metas.append(meta("000999-aaaaaa-0000aaaa", 150, kind="manual"))
    metas.append(meta("000998-aaaaaa-0000bbbb", 150, kind="merge"))
    # Give them children so they are not heads: only the kind rule protects them.
    metas[40]["parents"] += ["000999-aaaaaa-0000aaaa", "000998-aaaaaa-0000bbbb"]
    pinned = {metas[5]["snapId"]}
    bases = {metas[6]["snapId"]}
    result = retention.plan(metas, pinned, bases, {metas[7]["snapId"]}, NOW)
    for snap_id in (*pinned, *bases, "000999-aaaaaa-0000aaaa", "000998-aaaaaa-0000bbbb"):
        assert snap_id not in result["prune"]
    assert metas[7]["snapId"] not in result["prune"]  # already pruned


def test_active_pins_and_heads():
    pins = [{"snapId": "a", "until": None}, {"snapId": "b", "until": NOW + 1}, {"snapId": "c", "until": NOW - 1}]
    assert retention.active_pins(pins, NOW) == {"a", "b"}
    metas = [meta("1", 1), meta("2", 1, parents=["1"]), meta("3", 1, parents=["1"])]
    assert retention.heads(metas) == {"2", "3"}


@st.composite
def dags(draw):
    n = draw(st.integers(min_value=1, max_value=40))
    metas = []
    for i in range(n):
        parents = (
            draw(st.lists(st.sampled_from([m["snapId"] for m in metas]), max_size=2, unique=True)) if metas else []
        )
        kind = draw(st.sampled_from(["auto-exit", "auto-exit", "auto-recovered", "manual", "merge", "provisional"]))
        metas.append(meta(f"{i:06d}-bbbbbb-{i:08x}", draw(st.floats(min_value=0, max_value=800)), kind, parents))
    pinned = set(draw(st.lists(st.sampled_from([m["snapId"] for m in metas]), max_size=3)))
    bases = set(draw(st.lists(st.sampled_from([m["snapId"] for m in metas]), max_size=3)))
    return metas, pinned, bases


@settings(max_examples=200, deadline=None)
@given(dags())
def test_property_protected_snapshots_are_never_pruned(case):
    metas, pinned, bases = case
    result = retention.plan(metas, pinned, bases, set(), NOW)
    pruned = set(result["prune"])
    protected = set(retention.heads(metas)) | pinned | bases
    protected |= {m["snapId"] for m in metas if NOW - retention.created_epoch(m) < 7 * 86400}
    protected |= {m["snapId"] for m in metas if m["kind"] in ("manual", "merge", "import")}
    passed = sorted(
        (m for m in metas if m["kind"] != "provisional"), key=lambda m: (retention.created_epoch(m), m["snapId"])
    )
    if passed:
        protected.add(passed[-1]["snapId"])
    assert pruned.isdisjoint(protected)
    assert pruned | set(result["keep"]) == {m["snapId"] for m in metas}


@pytest.mark.parametrize("bad", ["", "nonsense", "2026-13-40T00:00:00Z"])
def test_bad_created_is_treated_as_old_but_still_protected_if_head(bad):
    m = meta("000001-cccccc-00000001", 1)
    m["created"] = bad
    result = retention.plan([m], set(), set(), set(), NOW)
    assert result["prune"] == []
