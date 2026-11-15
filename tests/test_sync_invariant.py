"""Invariant: no file version that ever existed on a device at a sync boundary is lost (build prompt slice 7).

Random sequences of whole actions run on two simulated devices sharing one
store: play sessions (online or offline), edits made while Keepsake is not
running, idle passes and conflict resolutions with random choices. Every
version a device holds when sync looks at it (before a pull, a push, an idle
pass or a conflict choice) is recorded. After every action each recorded
version must still be recoverable: in a cloud snapshot, in a device's
pre-restore or quarantine copies, or on a device right now.

The one allowed way to lose a version is the player's own progress: an edit
that overwrites files which were never synced is the player's change, not
sync's. Such versions are exempted at the moment of the edit.
"""

import hashlib
import json

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from keepsake.snapshot import SnapshotError
from keepsake.store import StoreError
from sim import GAME, make_pair

NAMES = ["a.sav", "b.sav", "c.sav"]
changes = st.dictionaries(st.sampled_from(NAMES), st.sampled_from([None, 1, 2, 3]), min_size=1, max_size=3)
action = st.one_of(
    st.tuples(st.just("session"), st.sampled_from([0, 1]), changes, st.booleans()),
    st.tuples(st.just("edit"), st.sampled_from([0, 1]), changes, st.just(False)),
    st.tuples(st.just("idle"), st.sampled_from([0, 1]), st.just({}), st.booleans()),
    st.tuples(
        st.just("resolve"),
        st.sampled_from([0, 1]),
        st.sampled_from(["use-cloud", "use-local", "decide-later"]),
        st.integers(0, 3),
    ),
)


def versions_on(device):
    return {(rel, hashlib.sha256(data).hexdigest()) for rel, data in device.files().items()}


def local_copies(device):
    found = set()
    for record in device.engine.prerestore.list(GAME) + device.engine.quarantine.list(GAME):
        found |= {(f["rel"], f["sha256"]) for f in record["meta"]["files"]}
    return found


def cloud_versions(device):
    found = set()
    inner = device.engine.store.inner
    for info in inner.list(f"games/{GAME}/snapshots/"):
        meta = json.loads(inner.get(info.key))
        found |= {(f["rel"], f["sha256"]) for f in meta["files"]}
    return found


def recoverable(devices):
    found = cloud_versions(devices[0])
    for d in devices:
        found |= versions_on(d) | local_copies(d)
    return found


@settings(
    max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
)
@given(sequence=st.lists(action, min_size=2, max_size=14))
def test_no_version_is_ever_lost(tmp_path_factory, sequence):
    devices = list(make_pair(tmp_path_factory.mktemp("inv"))[:2])
    observed: set[tuple[str, str]] = set()
    exempt: set[tuple[str, str]] = set()
    counter = 0

    def edit(device, wanted):
        nonlocal counter
        # Versions only this device holds, never synced, are the player's to overwrite.
        others = [x for x in devices if x is not device]
        elsewhere = cloud_versions(device) | local_copies(device)
        for x in others:
            elsewhere |= versions_on(x) | local_copies(x)
        exempt.update(versions_on(device) - elsewhere)
        counter += 1
        device.write({n: None if v is None else f"{device.name}-{counter}-{v}".encode() for n, v in wanted.items()})

    for kind, index, arg, flag in sequence:
        d = devices[index]
        if kind == "session":
            d.online = not flag if flag else True
            observed.update(versions_on(d))
            d.launch()
            edit(d, arg)
            observed.update(versions_on(d))
            d.exit()
            d.online = True
        elif kind == "edit":
            edit(d, arg)
        elif kind == "idle":
            observed.update(versions_on(d))
            d.sync.idle(d.ctx)
        elif kind == "resolve" and d.sync.status(GAME).get("conflict"):
            observed.update(versions_on(d))
            heads = [h["snapId"] for h in d.sync.status(GAME)["conflict"]["heads"]]
            try:
                d.sync.resolve(d.ctx, arg, head=heads[flag % len(heads)] if heads else None)
            except (SnapshotError, StoreError):
                pass  # e.g. the chosen head is no longer a head; nothing was changed
        missing = (observed - exempt) - recoverable(devices)
        assert not missing, f"lost {missing} after {kind} on device {index}"
