"""Direct save sync between paired devices, no cloud account (slice R7, ADR-0061). Synthetic data only."""

import asyncio
import json
import os

import pytest

from keepsake import directsync
from keepsake.engine import blob_key, pin_key, pruned_key, snapshot_key
from keepsake.store import LocalFolderStore, StoreError
from test_replication_devices import make_app  # noqa: F401 - the app fixture

GAME = "test-game"


class Session:
    peer_id = "device-bbbb-0002"


class Refused(Exception):
    pass


class FakeConnection:
    """The other device's handlers, called in process, as the Replication link would carry them."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    async def _call(self, message):
        self.calls.append(message)
        reply = await self.handlers[message["type"]](Session(), message)
        if isinstance(reply, dict) and reply.get("type") == "error":
            raise Refused(reply["reason"])
        return reply

    async def request(self, message):
        return await self._call(message)

    async def request_blob(self, message, max_size=64 * 1024 * 1024):
        header, data = await self._call(message)
        assert len(data) <= max_size
        return header, data


def pair(tmp_path, other_is_direct=True):
    here = LocalFolderStore(str(tmp_path / "here"))
    there = LocalFolderStore(str(tmp_path / "there"))
    changed = []
    handlers = directsync.handlers(lambda: there if other_is_direct else None, on_changed=changed.append)
    return here, there, FakeConnection(handlers), changed


def snapshot(store, snap_id, data=b"zipped saves"):
    """A snapshot as the engine writes it: the blob first, then the snapshot that names it."""
    store.put_new(blob_key(GAME, snap_id), data)
    store.put_new(snapshot_key(GAME, snap_id), json.dumps({"snapId": snap_id}).encode())


def keys(store):
    return sorted(i.key for i in store.list("games/"))


def test_what_the_other_device_has_is_copied_and_nothing_here_changes(tmp_path):
    here, there, connection, _ = pair(tmp_path)
    snapshot(there, "s-there")
    there.put_new(pin_key(GAME, "s-there"), b"{}")
    snapshot(here, "s-here")
    result = asyncio.run(directsync.exchange(here, connection))
    assert result["copied"] == 3 and result["removed"] == 0
    assert keys(here) == sorted(
        [
            blob_key(GAME, "s-here"),
            snapshot_key(GAME, "s-here"),
            blob_key(GAME, "s-there"),
            snapshot_key(GAME, "s-there"),
            pin_key(GAME, "s-there"),
        ]
    )
    assert here.get(blob_key(GAME, "s-there")) == b"zipped saves"
    assert keys(there) == sorted([blob_key(GAME, "s-there"), snapshot_key(GAME, "s-there"), pin_key(GAME, "s-there")])
    connection.calls.clear()
    again = asyncio.run(directsync.exchange(here, connection))
    assert again["copied"] == 0  # write-once: nothing is fetched twice
    assert [c["type"] for c in connection.calls] == ["store-list"]  # not even asked for


def test_a_snapshot_never_arrives_before_its_blob(tmp_path):
    here, there, connection, _ = pair(tmp_path)
    for snap in ("a", "b", "c"):
        snapshot(there, snap)
    asyncio.run(directsync.exchange(here, connection))
    fetched = [c["key"] for c in connection.calls if c["type"] == "store-get"]
    for snap in ("a", "b", "c"):
        assert fetched.index(blob_key(GAME, snap)) < fetched.index(snapshot_key(GAME, snap))


def test_every_snapshot_comes_after_every_other_object():
    keys_in = ["games/a/snapshots/1.json", "games/b/blobs/2.zip", "games/a/pins/1.json", "games/b/snapshots/2.json"]
    ordered = directsync._order(keys_in)
    assert ordered[:2] == ["games/a/pins/1.json", "games/b/blobs/2.zip"]
    assert ordered[2:] == ["games/a/snapshots/1.json", "games/b/snapshots/2.json"]


def test_retention_on_either_device_decides_for_both(tmp_path):
    here, there, connection, _ = pair(tmp_path)
    # Pruned on the other device: its blob is not copied back.
    snapshot(there, "old")
    there.put_new(pruned_key(GAME, "old"), b"{}")
    there.delete(blob_key(GAME, "old"))
    # Pruned on the other device, still here: removed here once the marker arrives.
    snapshot(here, "older")
    there.put_new(pruned_key(GAME, "older"), b"{}")
    # The other device has the blob, but this device pruned it: not copied.
    snapshot(there, "mine-pruned")
    here.put_new(pruned_key(GAME, "mine-pruned"), b"{}")
    result = asyncio.run(directsync.exchange(here, connection))
    assert blob_key(GAME, "old") not in keys(here) and blob_key(GAME, "mine-pruned") not in keys(here)
    assert blob_key(GAME, "older") not in keys(here) and result["removed"] == 1
    assert pruned_key(GAME, "old") in keys(here) and pruned_key(GAME, "older") in keys(here)


def test_large_objects_come_in_parts(tmp_path, monkeypatch):
    monkeypatch.setattr(directsync, "PART", 1000)
    here, there, connection, _ = pair(tmp_path)
    big = os.urandom(3500)
    snapshot(there, "big", big)
    asyncio.run(directsync.exchange(here, connection))
    assert here.get(blob_key(GAME, "big")) == big
    lengths = [c["length"] for c in connection.calls if c["type"] == "store-get" and c["key"] == blob_key(GAME, "big")]
    assert lengths == [1000, 1000, 1000, 500]
    assert not os.listdir(os.path.join(here._root, directsync.INCOMING))  # no part left behind


def test_an_object_that_arrives_short_is_not_kept(tmp_path):
    here, there, connection, _ = pair(tmp_path)
    snapshot(there, "s")
    original = connection.request_blob

    async def short(message, max_size=64 * 1024 * 1024):
        header, data = await original(message, max_size)
        if message["type"] == "store-get" and message["key"].endswith(".zip"):
            return header, b""
        return header, data

    connection.request_blob = short
    with pytest.raises(StoreError, match="wrong size"):
        asyncio.run(directsync.exchange(here, connection))
    assert blob_key(GAME, "s") not in keys(here)


def test_a_device_that_does_not_sync_directly_refuses(tmp_path):
    here, _there, connection, _ = pair(tmp_path, other_is_direct=False)
    with pytest.raises(Refused, match="does not sync saves directly"):
        asyncio.run(directsync.exchange(here, connection))


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ({"type": "store-get", "key": "../settings.json", "offset": 0, "length": 10}, "invalid store key"),
        ({"type": "store-get", "key": "other/thing", "offset": 0, "length": 10}, "only save objects"),
        ({"type": "store-get", "key": "games/x/blobs/y.zip", "offset": 0, "length": 10**8}, "4 MiB"),
        ({"type": "store-get", "key": "games/x/blobs/y.zip", "offset": -1, "length": 10}, "4 MiB"),
        ({"type": "store-get", "key": "games/x/blobs/missing.zip", "offset": 0, "length": 10}, "not on this device"),
    ],
)
def test_requests_that_are_refused(tmp_path, message, reason):
    _here, _there, connection, _ = pair(tmp_path)
    with pytest.raises(Refused, match=reason):
        asyncio.run(connection.request_blob(message))


def test_a_list_that_is_not_valid_is_refused(tmp_path):
    here = LocalFolderStore(str(tmp_path / "here"))

    class Bad:
        async def request_blob(self, message, max_size=0):
            return {}, b'[["../escape", 1]]'

    with pytest.raises(StoreError, match="not valid"):
        asyncio.run(directsync.exchange(here, Bad()))


def test_telling_the_other_device_asks_it_to_fetch(tmp_path):
    _here, _there, connection, changed = pair(tmp_path)
    asyncio.run(directsync.tell_changed(connection))
    assert changed == ["device-bbbb-0002"]


def test_the_app_uses_its_own_store_and_fetches_on_the_idle_pass(make_app, monkeypatch):  # noqa: F811
    async def scenario():
        app = make_app("a")
        await app.start()
        try:
            with pytest.raises(ValueError, match="Direct between my devices"):
                await app.direct_sync_now()
            assert app._direct_store() is None
            await app.set_setting("snapshotStore", "direct")
            store = app._store()
            assert isinstance(store, LocalFolderStore) and store._root == os.path.realpath(app._direct_root())
            status = await app.cloud_status()
            assert status["signedIn"] is False and "pair your other device" in status["problem"]
            with pytest.raises(ValueError, match="switch on Replication"):
                await app.direct_sync_now()
            assert (await app._direct_exchange())["peers"] == 0  # no Replication: nothing to reach, no error
            await app.set_module_enabled("replication", True)
            app.links.store.add("device-bbbb-0002", "Test device B", b"k" * 32, "127.0.0.1:1")
            assert (await app.cloud_status())["signedIn"] is True
            calls = []

            async def exchange(timeout=60.0, only=None):
                calls.append(only)
                return {"peers": 0, "copied": 0, "unreachable": []}

            monkeypatch.setattr(app, "_direct_exchange", exchange)
            await app.idle_pass()
            assert calls == [None]
            app._direct_peer_changed("device-bbbb-0002")
            await asyncio.sleep(0)
            assert calls == [None, "device-bbbb-0002"]
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_an_unreachable_device_never_blocks_play(make_app):  # noqa: F811
    async def scenario():
        app = make_app("a")
        await app.start()
        await app.set_setting("snapshotStore", "direct")
        await app.set_module_enabled("replication", True)
        try:
            app.links.store.add("device-bbbb-0002", "Test device B", b"k" * 32, "127.0.0.1:1")  # nothing listens
            result = await app._direct_exchange(timeout=2)
            assert result["unreachable"] == ["Test device B"] and result["copied"] == 0
            assert (await app.cloud_status())["direct"]["unreachable"] == ["Test device B"]
        finally:
            await app.stop()

    asyncio.run(scenario())
