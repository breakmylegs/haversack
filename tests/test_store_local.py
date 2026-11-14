import hashlib
import threading

import pytest

from keepsake.store import AlreadyExistsError, LocalFolderStore, NotFoundError, StoreError, validate_key


def test_put_get_list_delete(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    info = store.put_new("games/g/snapshots/1.json", b"{}")
    assert info.sha256 == hashlib.sha256(b"{}").hexdigest()
    store.put_new("games/g/blobs/1.zip", b"zip")
    store.put_new("registry/devices/d.json", b"d")
    assert store.get("games/g/snapshots/1.json") == b"{}"
    assert [o.key for o in store.list("games/g/")] == ["games/g/blobs/1.zip", "games/g/snapshots/1.json"]
    assert len(store.list()) == 3
    store.delete("games/g/blobs/1.zip")
    with pytest.raises(NotFoundError):
        store.get("games/g/blobs/1.zip")
    with pytest.raises(NotFoundError):
        store.delete("games/g/blobs/1.zip")


def test_create_only(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    store.put_new("a.json", b"first")
    with pytest.raises(AlreadyExistsError):
        store.put_new("a.json", b"second")
    assert store.get("a.json") == b"first"


def test_racing_writers_exactly_one_wins(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    results = []
    barrier = threading.Barrier(8)

    def writer(n):
        barrier.wait()
        try:
            store.put_new("race.json", str(n).encode())
            results.append(("ok", n))
        except AlreadyExistsError:
            results.append(("exists", n))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [n for status, n in results if status == "ok"]
    assert len(winners) == 1
    assert store.get("race.json") == str(winners[0]).encode()


def test_temp_files_not_listed(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    store.put_new("a", b"1")
    assert [o.key for o in store.list()] == ["a"]


@pytest.mark.parametrize("key", ["", "/a", "a/", "../a", "a/../b", "a//b", ".hidden", "a b", "a\\b", "x" * 600])
def test_invalid_keys(tmp_path, key):
    with pytest.raises(StoreError):
        validate_key(key)
    with pytest.raises(StoreError):
        LocalFolderStore(str(tmp_path)).put_new(key, b"")
