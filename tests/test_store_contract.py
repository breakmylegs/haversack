"""Store contract: every backend must behave the same (build prompt slices 6 and 10)."""

import os
import threading

import pytest

from fake_graph import FakeGraph, FakeTokens, http_transport
from keepsake.store import AlreadyExistsError, LocalFolderStore, NotFoundError, StoreError
from keepsake.store.graph import GraphStore

SMALL_CHUNK = 320 * 1024


@pytest.fixture(params=["local", "graph"])
def store(request, tmp_path):
    if request.param == "local":
        yield LocalFolderStore(str(tmp_path / "store"))
        return
    fake = FakeGraph()
    yield GraphStore(
        FakeTokens(fake), transport=http_transport, base_url=fake.base_url, sleep=lambda s: None, chunk_size=SMALL_CHUNK
    )
    fake.close()


def test_put_get_list_delete(store):
    info = store.put_new("games/g/snapshots/1.json", b"{}")
    assert info.size == 2
    store.put_new("games/g/blobs/1.zip", b"zip")
    store.put_new("registry/devices/d.json", b"d")
    assert store.get("games/g/snapshots/1.json") == b"{}"
    assert [o.key for o in store.list("games/g/")] == ["games/g/blobs/1.zip", "games/g/snapshots/1.json"]
    assert [o.key for o in store.list("games/g/snapshots/")] == ["games/g/snapshots/1.json"]
    assert len(store.list()) == 3
    assert store.list("games/missing/") == []
    store.delete("games/g/blobs/1.zip")
    with pytest.raises(NotFoundError):
        store.get("games/g/blobs/1.zip")
    with pytest.raises(NotFoundError):
        store.delete("games/g/blobs/1.zip")


def test_create_only(store):
    store.put_new("a/b.json", b"first")
    with pytest.raises(AlreadyExistsError):
        store.put_new("a/b.json", b"second")
    assert store.get("a/b.json") == b"first"


def test_racing_writers_exactly_one_wins(store):
    results = []
    barrier = threading.Barrier(4)

    def writer(n):
        barrier.wait()
        try:
            store.put_new("race/x.json", str(n).encode())
            results.append(("ok", n))
        except AlreadyExistsError:
            results.append(("exists", n))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [n for status, n in results if status == "ok"]
    assert len(winners) == 1
    assert store.get("race/x.json") == str(winners[0]).encode()


def test_large_file_round_trip_with_verified_hash(store, tmp_path):
    data = os.urandom(3 * SMALL_CHUNK + 12345)  # several chunks plus a partial one
    source = tmp_path / "big.bin"
    source.write_bytes(data)
    info = store.put_new_file("games/g/blobs/big.zip", str(source))
    import hashlib

    assert info.sha256 == hashlib.sha256(data).hexdigest()
    dest = tmp_path / "down.bin"
    got = store.get_to_file("games/g/blobs/big.zip", str(dest))
    assert dest.read_bytes() == data and got.sha256 == info.sha256


def test_get_missing(store, tmp_path):
    with pytest.raises(NotFoundError):
        store.get("nope/x.json")
    with pytest.raises(NotFoundError):
        store.get_to_file("nope/x.json", str(tmp_path / "x"))


@pytest.mark.parametrize("key", ["", "/a", "a/", "../a", "a//b", ".hidden", "a b"])
def test_invalid_keys(store, key):
    with pytest.raises(StoreError):
        store.put_new(key, b"x")


def test_listing_paginates_and_nests(store):
    for i in range(5):
        store.put_new(f"games/g/snapshots/{i}.json", b"x")
    store.put_new("games/g/pins/0.json", b"p")
    keys = [o.key for o in store.list("games/g/")]
    assert keys == ["games/g/pins/0.json"] + [f"games/g/snapshots/{i}.json" for i in range(5)]
