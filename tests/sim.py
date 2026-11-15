"""Two-device simulator for the sync engine (build prompt slice 7 and section 17).

Two fake devices with separate save folders, different device IDs and skewed
clocks share one LocalFolderStore. A device can go offline (its store raises
StoreUnavailable), and a hook can run another device's action in the middle
of a store call to simulate races.
"""

from __future__ import annotations

import os

from helpers import files_in, tree_state, write_tree
from keepsake.engine import SnapshotEngine
from keepsake.store import LocalFolderStore, Store, StoreUnavailable
from keepsake.sync import GameContext, SyncEngine

GAME = "example-game"
ROOT = "winLocalAppData"


class SharedClock:
    def __init__(self):
        self.now = 2_000_000_000.0

    def tick(self, seconds=60):
        self.now += seconds


class FlakyStore(Store):
    def __init__(self, inner, device):
        self.inner = inner
        self.device = device
        self.before_list = None  # one-shot hook for races

    def _check(self):
        if not self.device.online:
            raise StoreUnavailable("offline")

    def put_new(self, key, data):
        self._check()
        return self.inner.put_new(key, data)

    def put_new_file(self, key, path):
        self._check()
        return self.inner.put_new_file(key, path)

    def get(self, key):
        self._check()
        return self.inner.get(key)

    def get_to_file(self, key, dest):
        self._check()
        self.device.downloads += 1
        return self.inner.get_to_file(key, dest)

    def list(self, prefix=""):
        self._check()
        if self.before_list and "/snapshots/" in prefix:
            hook, self.before_list = self.before_list, None
            hook()
        return self.inner.list(prefix)

    def delete(self, key):
        self._check()
        return self.inner.delete(key)


class Device:
    def __init__(self, tmp, name, shared, clock, skew):
        self.name = name
        self.online = True
        self.running = False
        self.downloads = 0
        base = tmp / name
        self.roots = {ROOT: str(base / "saves")}
        os.makedirs(self.roots[ROOT], exist_ok=True)
        os.makedirs(base / "settings", exist_ok=True)
        self.clock = lambda: clock.now + skew
        self.store = FlakyStore(shared, self)
        self.engine = SnapshotEngine(
            self.store,
            str(base / "rt"),
            str(base / "settings"),
            f"{name}0000-0000-0000-0000-000000000000"[:36],
            name,
            "sim",
            clock=self.clock,
        )
        self.sync = SyncEngine(self.engine, str(base / "rt"), clock=self.clock)
        self.ctx = GameContext(GAME, files=lambda: files_in(self.roots), roots=self.roots, running=lambda: self.running)

    def files(self):
        return {rel: data for (_root, rel), data in tree_state(self.roots).items()}

    def write(self, changes):
        """``changes`` maps rel to bytes, or to None to delete."""
        for rel, data in changes.items():
            path = os.path.join(self.roots[ROOT], *rel.split("/"))
            if data is None:
                if os.path.exists(path):
                    os.unlink(path)
            else:
                write_tree(self.roots, {(ROOT, rel): data})

    def launch(self):
        result = self.sync.pull(self.ctx)
        self.running = True
        return result

    def exit(self):
        self.running = False
        return self.sync.push(self.ctx)


def make_pair(tmp_path, skew_b=-3 * 86400):
    clock = SharedClock()
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a = Device(tmp_path, "aaaaaa", shared, clock, 0)
    b = Device(tmp_path, "bbbbbb", shared, clock, skew_b)  # B's clock is three days behind
    return a, b, clock
