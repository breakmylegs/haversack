"""Store contract against the real OneDrive app folder (opt-in, build prompt slice 6).

Runs only when KEEPSAKE_ONEDRIVE_TOKEN_FILE points at a token file written by
Keepsake's sign-in, normally on a device:

    python scripts/test_on_device.py --onedrive

Everything happens under ``contract-tests/<random>/`` in the app folder and is
deleted afterwards. User data is never touched.
"""

import hashlib
import os
import uuid

import pytest

from keepsake.auth import TokenManager, TokenStore
from keepsake.store import AlreadyExistsError, NotFoundError
from keepsake.store.graph import GraphStore

TOKEN_FILE = os.environ.get("KEEPSAKE_ONEDRIVE_TOKEN_FILE", "")

pytestmark = [
    pytest.mark.onedrive,
    pytest.mark.skipif(not TOKEN_FILE or not os.path.exists(TOKEN_FILE), reason="no OneDrive token file"),
]


@pytest.fixture
def store():
    tokens = TokenManager(TokenStore(os.path.dirname(TOKEN_FILE)), lambda: "")
    graph = GraphStore(tokens)
    prefix = f"contract-tests/{uuid.uuid4().hex[:12]}/"
    created: list[str] = []
    yield graph, prefix, created
    for key in created:
        try:
            graph.delete(key)
        except NotFoundError:
            pass


def test_live_contract(store, tmp_path):
    graph, prefix, created = store
    assert graph.check()["id"] is True
    key = prefix + "a/one.json"
    created.append(key)
    info = graph.put_new(key, b'{"hello": 1}')
    assert info.size == 12
    assert graph.get(key) == b'{"hello": 1}'
    with pytest.raises(AlreadyExistsError):  # create-only conflict (assumption A55)
        graph.put_new(key, b"other")
    assert graph.get(key) == b'{"hello": 1}'

    big = os.urandom(11 * 1024 * 1024)  # two upload chunks
    source = tmp_path / "big.bin"
    source.write_bytes(big)
    big_key = prefix + "blobs/big.zip"
    created.append(big_key)
    uploaded = graph.put_new_file(big_key, str(source))
    downloaded = graph.get_to_file(big_key, str(tmp_path / "down.bin"))
    assert downloaded.sha256 == hashlib.sha256(big).hexdigest()
    print(f"upload verified by reported hash: {uploaded.sha256 is not None}")

    assert sorted(o.key for o in graph.list(prefix)) == sorted(created)
    graph.delete(key)
    created.remove(key)
    with pytest.raises(NotFoundError):
        graph.get(key)
