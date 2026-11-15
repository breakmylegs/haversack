import json

import pytest

from keepsake import configrev
from keepsake.store import AlreadyExistsError, LocalFolderStore, StoreError

GK = "example-quest"
DEV_A = "aaaaaaaa-0000-0000-0000-000000000000"
DEV_B = "bbbbbbbb-0000-0000-0000-000000000000"


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        self.now += 10
        return self.now


def config(**changes):
    return {"aliases": [], "includeConfig": False, "customPaths": [], "exclusions": [], **changes}


def test_publish_numbers_revisions_per_device_and_lists_them(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    clock = Clock()
    first = configrev.publish(store, GK, DEV_A, "Handheld A", config(aliases=["EQ"]), None, clock)
    second = configrev.publish(store, GK, DEV_A, "Handheld A", config(aliases=["EQ2"]), first, clock)
    other = configrev.publish(store, GK, DEV_B, "Handheld B", config(), second, clock)
    assert first == f"000001-{DEV_A}.json" and second == f"000002-{DEV_A}.json" and other == f"000001-{DEV_B}.json"
    revisions = configrev.list_revisions(store, GK)
    assert [r["name"] for r in revisions] == sorted([first, second, other])  # listed by key
    assert configrev.newest(revisions)["name"] == other
    by_name = {r["name"]: r for r in revisions}
    assert by_name[second]["config"]["aliases"] == ["EQ2"] and by_name[second]["basedOn"] == first


def test_only_shared_fields_are_published(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    local = {**config(customPaths=[{"root": "base", "rel": "Saves"}]), "enabled": True, "gameKey": "x"}
    name = configrev.publish(store, GK, DEV_A, "A", local, None, Clock())
    body = json.loads(store.get(f"games/{GK}/config/{name}"))
    assert set(body["config"]) == set(configrev.SHARED_FIELDS)
    assert body["config"]["customPaths"] == [{"root": "base", "rel": "Saves"}]


def test_newest_orders_by_time_then_device(tmp_path):
    revisions = [
        {"name": "1", "createdTs": 5.0, "deviceId": DEV_B, "seq": 1},
        {"name": "2", "createdTs": 9.0, "deviceId": DEV_A, "seq": 1},
        {"name": "3", "createdTs": 9.0, "deviceId": DEV_B, "seq": 2},
    ]
    assert configrev.newest(revisions)["name"] == "3"
    assert configrev.newest([]) is None


def test_concurrent_edits_share_a_base_on_different_devices(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    clock = Clock()
    root = configrev.publish(store, GK, DEV_A, "A", config(), None, clock)
    configrev.publish(store, GK, DEV_A, "A", config(aliases=["A"]), root, clock)
    configrev.publish(store, GK, DEV_B, "B", config(aliases=["B"]), root, clock)
    revisions = configrev.list_revisions(store, GK)
    chosen = configrev.newest(revisions)
    assert chosen["deviceName"] == "B"
    assert [r["deviceName"] for r in configrev.concurrent_with(revisions, chosen)] == ["A"]


def test_sibling_revisions_from_one_device_are_not_concurrent(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    clock = Clock()
    root = configrev.publish(store, GK, DEV_B, "B", config(), None, clock)
    # A change left pending, then another before it was shared: both based on the same revision.
    configrev.publish(store, GK, DEV_A, "A", config(aliases=["1"]), root, clock)
    configrev.publish(store, GK, DEV_A, "A", config(aliases=["2"]), root, clock)
    revisions = configrev.list_revisions(store, GK)
    assert configrev.concurrent_with(revisions, configrev.newest(revisions)) == []


def test_invalid_or_foreign_revisions_are_ignored(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    good = configrev.publish(store, GK, DEV_A, "A", config(), None, Clock())
    body = json.loads(store.get(f"games/{GK}/config/{good}"))

    def put(name, data):
        store.put_new(f"games/{GK}/config/{name}", json.dumps(data).encode())

    put(f"000005-{DEV_B}.json", {**body, "deviceId": DEV_B, "seq": 5, "schemaVersion": 2})  # newer schema
    put(f"000006-{DEV_B}.json", {**body, "deviceId": DEV_A, "seq": 6})  # device does not match the name
    put(f"000007-{DEV_B}.json", {**body, "deviceId": DEV_B, "seq": 7, "gameKey": "other"})
    put(f"000008-{DEV_B}.json", {**body, "deviceId": DEV_B, "seq": 8, "config": {"enabled": True}})
    bad_path = {**body["config"], "customPaths": [{"root": "base", "rel": "../escape"}]}
    put(f"000009-{DEV_B}.json", {**body, "deviceId": DEV_B, "seq": 9, "config": bad_path})
    put("notes.json", {"x": 1})
    store.put_new(f"games/{GK}/config/000010-{DEV_B}.json", b"not json")
    assert [r["name"] for r in configrev.list_revisions(store, GK)] == [good]


def test_publish_skips_a_taken_number(tmp_path, monkeypatch):
    store = LocalFolderStore(str(tmp_path))
    real = store.put_new
    calls = []

    def racing(key, data):
        calls.append(key)
        if len(calls) == 1:
            raise AlreadyExistsError(key)  # another write took this number between list and put
        return real(key, data)

    monkeypatch.setattr(store, "put_new", racing)
    assert configrev.publish(store, GK, DEV_A, "A", config(), None, Clock()) == f"000002-{DEV_A}.json"

    monkeypatch.setattr(store, "put_new", lambda key, data: (_ for _ in ()).throw(AlreadyExistsError(key)))
    with pytest.raises(StoreError):
        configrev.publish(store, GK, DEV_A, "A", config(), None, Clock())
