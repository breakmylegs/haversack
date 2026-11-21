"""Several save locations at once (ADR-0071): the union store, catch-up, and two devices out of step."""

from __future__ import annotations

import asyncio
import json

import pytest

from keepsake.store import LocalFolderStore, Store, StoreUnavailable
from keepsake.store.base import AlreadyExistsError, NotFoundError
from keepsake.store.multi import LocationState, MultiStore, game_of
from sim import GAME, Device, SharedClock


class Location(Store):
    """A save location that can be taken down (a NAS off, a cloud unreachable)."""

    def __init__(self, inner):
        self.inner, self.up = inner, True

    def _check(self):
        if not self.up:
            raise StoreUnavailable("location down")

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
        return self.inner.get_to_file(key, dest)

    def list(self, prefix=""):
        self._check()
        return self.inner.list(prefix)

    def delete(self, key):
        self._check()
        return self.inner.delete(key)


def two(tmp_path, route=None):
    a, b = Location(LocalFolderStore(str(tmp_path / "one"))), Location(LocalFolderStore(str(tmp_path / "two")))
    state = LocationState(str(tmp_path / "locations.json"), clock=lambda: 1000.0)
    return MultiStore({"onedrive": a, "webdav": b}, route, state), a, b, state


def keys(store):
    return [i.key for i in store.list()]


def test_writes_go_everywhere_and_reads_and_lists_are_one_view(tmp_path):
    multi, a, b, state = two(tmp_path)
    multi.put_new("games/g/snapshots/s1.json", b"one")
    assert keys(a.inner) == keys(b.inner) == ["games/g/snapshots/s1.json"]
    b.inner.put_new("games/g/snapshots/s2.json", b"two")  # only in the second (from another device)
    assert keys(multi) == ["games/g/snapshots/s1.json", "games/g/snapshots/s2.json"]
    assert multi.get("games/g/snapshots/s2.json") == b"two"
    assert state.load()["onedrive"]["lastOk"] == 1000.0
    with pytest.raises(AlreadyExistsError):
        multi.put_new("games/g/snapshots/s1.json", b"one")  # already everywhere
    assert multi.put_new("games/g/snapshots/s2.json", b"two").key.endswith("s2.json")  # created where missing
    assert keys(a.inner) == keys(b.inner)
    with pytest.raises(NotFoundError):
        multi.get("games/g/snapshots/nope.json")


def test_one_location_down_never_blocks_the_others(tmp_path):
    multi, a, b, state = two(tmp_path)
    b.up = False
    multi.put_new("games/g/snapshots/s1.json", b"one")  # written to the one that answers
    assert keys(a.inner) == ["games/g/snapshots/s1.json"] and "location down" in state.load()["webdav"]["problem"]
    assert keys(multi) == ["games/g/snapshots/s1.json"]  # the union of what answered
    assert multi.get("games/g/snapshots/s1.json") == b"one"
    with pytest.raises(StoreUnavailable):  # not here, and the other did not answer: never "not found"
        multi.get("games/g/snapshots/elsewhere.json")
    a.up = False
    for action in (
        lambda: multi.put_new("games/g/x", b"x"),
        lambda: multi.list("games/"),
        lambda: multi.delete("games/g/x"),
    ):
        with pytest.raises(StoreUnavailable):
            action()  # none answers: the offline queue keeps it, as with one location
    a.up = b.up = True
    copied = multi.catch_up()
    assert copied == {"onedrive": 0, "webdav": 1} and keys(b.inner) == ["games/g/snapshots/s1.json"]
    assert state.load()["webdav"]["missing"] == 0


def test_catch_up_never_brings_back_what_retention_pruned_nor_orphans(tmp_path):
    multi, a, b, _state = two(tmp_path)
    for store in (a.inner, b.inner):
        store.put_new("games/g/snapshots/s1.json", b"{}")
        store.put_new("games/g/blobs/s1.zip", b"zip")
    a.inner.put_new("games/g/pruned/s1", b"{}")  # retention ran while the second was away
    a.inner.delete("games/g/blobs/s1.zip")
    a.inner.put_new("games/g/blobs/orphan.zip", b"zip")  # no snapshot: an orphan
    copied = multi.catch_up()
    assert "games/g/blobs/s1.zip" not in keys(a.inner) and "games/g/blobs/s1.zip" not in keys(b.inner)
    assert "games/g/pruned/s1" in keys(b.inner)  # the marker travels
    assert "games/g/blobs/orphan.zip" not in keys(b.inner)
    assert copied == {"onedrive": 0, "webdav": 1}


def test_a_game_can_use_some_locations_only(tmp_path):
    route = lambda key: ["onedrive"] if game_of(key) == "private" else ["onedrive", "webdav"]  # noqa: E731
    multi, _a, b, _state = two(tmp_path, route)
    multi.put_new("games/private/snapshots/s1.json", b"x")
    multi.put_new("games/shared/snapshots/s1.json", b"y")
    multi.put_new("registry/devices/d.json", b"z")
    assert keys(b.inner) == ["games/shared/snapshots/s1.json", "registry/devices/d.json"]
    assert multi.catch_up() == {"onedrive": 0, "webdav": 0}  # the private game is not copied to the second
    assert game_of("games/abc/pins/x.json") == "abc" and game_of("registry/x") is None


def test_catch_up_is_bounded_and_large_objects_go_through_a_file(tmp_path, monkeypatch):
    multi, a, b, _state = two(tmp_path)
    for i in range(5):
        a.inner.put_new(f"games/g/pins/p{i}.json", b"{}")
    a.inner.put_new("games/g/snapshots/big.json", b"{}")
    monkeypatch.setattr("keepsake.store.multi.SMALL", 3)
    a.inner.put_new("games/g/blobs/big.zip", b"0123456789")
    whole = a.inner.get

    def no_whole_reads_of_big_objects(key):
        assert key != "games/g/blobs/big.zip", "a large object is copied through a file"
        return whole(key)

    monkeypatch.setattr(a.inner, "get", no_whole_reads_of_big_objects)
    assert sum(multi.catch_up(limit=3).values()) == 3
    multi.catch_up()
    assert b.inner.get("games/g/blobs/big.zip") == b"0123456789"
    assert keys(a.inner) == keys(b.inner)


def test_errors_other_than_unavailable_are_reported():
    class Broken(Location):
        def put_new(self, key, data):
            raise NotFoundError("no such folder")

    multi = MultiStore({"one": Broken(None)})
    with pytest.raises(NotFoundError):
        multi.put_new("games/g/x", b"x")
    with pytest.raises(Exception, match="no save location"):
        MultiStore({})


# Two devices, two locations, out of step


def pair(tmp_path):
    clock = SharedClock()
    one, two_ = Location(LocalFolderStore(str(tmp_path / "one"))), Location(LocalFolderStore(str(tmp_path / "two")))
    # Each device has its own union store over the same two locations, with its own copy of history seen.
    store_a = MultiStore({"onedrive": one, "webdav": two_}, cache_dir=str(tmp_path / "a-history"))
    store_b = MultiStore({"onedrive": one, "webdav": two_}, cache_dir=str(tmp_path / "b-history"))
    a = Device(tmp_path, "aaaaaa", store_a, clock, 0)
    b = Device(tmp_path, "bbbbbb", store_b, clock, 0)
    return a, b, clock, store_a, one, two_


def test_two_devices_stay_in_step_while_each_location_drops_out_in_turn(tmp_path):
    a, b, clock, store, one, two_ = pair(tmp_path)
    a.launch()
    a.write({"slot.sav": b"from A"})
    two_.up = False
    assert a.exit()["status"] == "published"  # only the first location took it
    clock.tick()
    b.launch()  # B sees it through the first
    assert b.files() == {"slot.sav": b"from A"}
    b.write({"slot.sav": b"from B"})
    two_.up, one.up = True, False
    assert b.exit()["status"] == "published"  # only the second took this one
    clock.tick()
    one.up = True
    pulled = a.launch()  # both answer: one view, a straight line of history, no conflict
    assert pulled.get("action") != "conflict" and a.files() == {"slot.sav": b"from B"}
    store.catch_up()
    assert sorted(i.key for i in one.inner.list("games/")) == sorted(i.key for i in two_.inner.list("games/"))


def test_play_carries_on_with_every_location_down(tmp_path):
    a, _b, clock, _store, one, two_ = pair(tmp_path)
    a.launch()
    a.write({"slot.sav": b"v1"})
    one.up = two_.up = False
    result = a.exit()
    assert result["status"] == "pending"  # queued, as with one location
    one.up = two_.up = True
    clock.tick()
    assert a.sync.push(a.ctx)["status"] in ("published", "no-change")
    assert any("/snapshots/" in i.key for i in two_.inner.list(f"games/{GAME}/"))


# The app


def test_the_app_uses_one_store_or_all_of_them(tmp_path):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.30.0", home=str(tmp_path))

    async def go():
        single = app._store()
        assert isinstance(single, LocalFolderStore) and app._locations() == ["local"]
        status = await app.add_location("direct")
        assert [x["id"] for x in status["locations"]] == ["local", "direct"]
        assert isinstance(app._store(), MultiStore) and app._direct_store() is not None
        await app.add_location("direct")  # already there: nothing changes
        with pytest.raises(ValueError):
            await app.add_location("nowhere")
        app.settings.set("snapshotStore", "local")  # still the first: the list stands
        assert app._locations() == ["local", "direct"]
        await app.remove_location("local")
        assert app._locations() == ["direct"] and app.settings.get("snapshotStore") == "direct"
        with pytest.raises(ValueError, match="at least one"):
            await app.remove_location("direct")
        app.settings.set("snapshotStores", ["direct", "local"])
        app.settings.set("snapshotStore", "local")  # an older page chose one: that alone counts
        assert app._locations() == ["local"]

    asyncio.run(go())
    with pytest.raises(Exception, match="once each"):
        app.settings.set("snapshotStores", ["local", "local"])


def test_a_game_chooses_its_locations(tmp_path):
    from keepsake.gameconfig import GameConfigError, GameConfigStore, validate

    configs = GameConfigStore(str(tmp_path))
    configs.update("shortcut:7:1", {"gameKey": "example-game", "locations": ["direct"]})
    configs.update("shortcut:7:2", {"gameKey": "other-game"})
    assert configs.locations_by_game_key() == {"example-game": ["direct"]}
    with pytest.raises(GameConfigError):
        validate({"locations": []})
    with pytest.raises(GameConfigError):
        validate({"locations": ["nowhere"]})
    assert validate({"locations": ["direct", "direct"]})["locations"] == ["direct"]
    assert json.dumps(validate({})["locations"]) == "null"


def test_history_already_seen_stays_visible_while_its_location_is_down(tmp_path):
    a, b = Location(LocalFolderStore(str(tmp_path / "one"))), Location(LocalFolderStore(str(tmp_path / "two")))
    multi = MultiStore({"onedrive": a, "webdav": b}, cache_dir=str(tmp_path / "history"))
    a.inner.put_new("games/g/snapshots/s1.json", b"meta")  # written by another device, only to the first
    a.inner.put_new("games/g/blobs/s1.zip", b"zip")
    assert multi.get("games/g/snapshots/s1.json") == b"meta"  # read once: now known here
    multi.put_new("games/g/bases/dev/000001.json", b"base")
    multi.put_new("games/g/blobs/s2.zip", b"zip2")  # written through it, still never kept
    a.up = b.up = False
    with pytest.raises(StoreUnavailable):
        multi.list("games/g/")  # nothing answers: no decision on history alone
    b.up = True
    listed = [i.key for i in multi.list("games/g/")]
    assert "games/g/snapshots/s1.json" in listed and "games/g/bases/dev/000001.json" in listed
    assert "games/g/blobs/s1.zip" not in listed  # blobs are never kept: retention deletes them
    assert "games/g/blobs/s2.zip" in listed  # it is in the second location, which answers
    assert multi.get("games/g/snapshots/s1.json") == b"meta"
    with pytest.raises(StoreUnavailable):
        multi.get("games/g/blobs/s1.zip")
    assert not (tmp_path / "history" / "games" / "g" / "blobs").exists()
