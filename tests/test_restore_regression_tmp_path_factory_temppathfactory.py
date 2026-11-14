# A regression test pinned by Codehouse from a Hypothesis counterexample (D-008). Locked: change it only with the person.
import json
import os
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from helpers import files_in, tree_state, write_tree
from keepsake import restore, snapshot
from keepsake.restore import RestoreError
from hypothesis import Phase, example, settings


@example(| tmp_path_factory=TempPathFactory(_given_basetemp=None, | _trace=<pluggy._tracing.TagTracerSub object at 0x00000218956A03E0>, | _basetemp=WindowsPath('C:/Users/peter.j.kelly/AppData/Local/Temp/pytest-of-peter.j.kelly/pytest-299'), | _retention_count=3, | _retention_policy='all'), | old={('winLocalAppData', '0'): b''}, | new={('winLocalAppData', '0/0'): b''}, |)
@settings(phases=[Phase.explicit])
@given(old=states, new=states)
def test_property_restore_reproduces_scanned_state_regression_tmp_path_factory_temppathfactory(tmp_path_factory, old, new):
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
