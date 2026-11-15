import hashlib

import pytest

from fake_graph import FakeGraph, FakeTokens, http_transport
from keepsake import net
from keepsake.store import AlreadyExistsError, StoreError
from keepsake.store.graph import GraphStore, StoreUnavailable

CHUNK = 320 * 1024


@pytest.fixture
def fake():
    server = FakeGraph()
    yield server
    server.close()


def make(fake, tokens=None, sleeps=None):
    return GraphStore(
        tokens or FakeTokens(fake),
        transport=http_transport,
        base_url=fake.base_url,
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
        chunk_size=CHUNK,
    )


def test_token_never_sent_to_upload_or_download_urls(fake):
    store = make(fake)
    store.put_new("a/b.json", b"x" * (CHUNK + 10))
    store.get("a/b.json")
    for method, path, had_auth in fake.log:
        if path.startswith(("/up/", "/download/")):
            assert had_auth is False, (method, path)
        else:
            assert had_auth is True, (method, path)


def test_401_refreshes_token_once(fake):
    tokens = FakeTokens(fake, token="stale")
    store = make(fake, tokens)
    store.put_new("k.json", b"1")
    assert tokens.refreshes == 1
    fake.reject_next_token = 2  # still rejected after refresh: give up, not loop
    with pytest.raises(StoreError):
        store.get("k.json")


def test_429_backs_off_and_retries(fake):
    sleeps = []
    store = make(fake, sleeps=sleeps)
    fake.throttle_next = 2
    store.put_new("k.json", b"1")
    assert len(sleeps) == 2
    fake.throttle_next = 10
    with pytest.raises(StoreUnavailable):
        store.get("k.json")


def test_missing_parents_are_created(tmp_path):
    fake = FakeGraph(auto_parents=False)
    try:
        store = make(fake)
        store.put_new("games/g/snapshots/1.json", b"{}")
        assert {"games", "games/g", "games/g/snapshots"} <= fake.folders
        assert store.get("games/g/snapshots/1.json") == b"{}"
    finally:
        fake.close()


def test_conflict_cancels_the_session(fake):
    store = make(fake)
    store.put_new("k.json", b"1")
    with pytest.raises(AlreadyExistsError):
        store.put_new("k.json", b"2")
    assert fake.cancelled == ["k.json"]


@pytest.mark.parametrize(
    ("report_sha", "wrong_sha", "wrong_qx", "verified"),
    [
        (True, False, False, True),
        (True, True, False, False),  # a wrong SHA-256 is never overridden by a right QuickXorHash
        (False, False, False, True),
        (False, False, True, False),
    ],
)
def test_upload_verification_uses_reported_hash(report_sha, wrong_sha, wrong_qx, verified):
    fake = FakeGraph(report_sha256=report_sha, wrong_sha256=wrong_sha, wrong_quickxor=wrong_qx)
    try:
        info = make(fake).put_new("k.json", b"hello world")
        assert info.sha256 == (hashlib.sha256(b"hello world").hexdigest() if verified else None)
    finally:
        fake.close()


def test_engine_redownloads_when_hash_cannot_be_verified(tmp_path):
    from helpers import files_in, write_tree
    from keepsake.engine import SnapshotEngine

    fake = FakeGraph(wrong_quickxor=True)
    try:
        roots = {"base": str(tmp_path / "base")}
        write_tree(roots, {("base", "s.sav"): b"save"})
        eng = SnapshotEngine(make(fake), str(tmp_path / "rt"), str(tmp_path), "abc12300-0", "d", "t")
        result = eng.take("g", files_in(roots), roots, "manual", None)
        assert result["status"] == "published"
        assert sum(1 for m, p, _ in fake.log if p.startswith("/download/")) == 1  # verified by re-download
    finally:
        fake.close()


def test_empty_objects_refused(fake):
    with pytest.raises(StoreError, match="empty"):
        make(fake).put_new("k.json", b"")


def test_chunk_size_must_be_320k_multiple(fake):
    with pytest.raises(ValueError):
        GraphStore(FakeTokens(fake), transport=http_transport, base_url=fake.base_url, chunk_size=1000)


def test_disallowed_host_is_refused_not_retried(fake):
    sleeps = []

    def transport(method, url, headers=None, body=None, dest=None, **kw):
        raise net.DisallowedHost("host not on the allowlist: evil.example")

    store = GraphStore(FakeTokens(fake), transport=transport, base_url=fake.base_url, sleep=sleeps.append)
    with pytest.raises(StoreError, match="refused"):
        store.get("k.json")
    assert sleeps == []


def test_app_folder_check(fake):
    assert make(fake).check() == {"name": "Keepsake", "id": True}


def test_microsoft_allowlist():
    net.check_url("https://graph.microsoft.com/v1.0/me", net.MICROSOFT_HOSTS)
    net.check_url("https://sn3302.up.1drv.com/up/x", net.MICROSOFT_HOSTS, net.MICROSOFT_CONTENT_SUFFIXES)
    net.check_url("https://my.microsoftpersonalcontent.com/x", net.MICROSOFT_HOSTS, net.MICROSOFT_CONTENT_SUFFIXES)
    for bad in (
        "https://evil1drv.com/x",
        "https://1drv.com.evil.example/x",
        "http://sn1.up.1drv.com/x",
        "https://graph.microsoft.com.evil.example/x",
    ):
        with pytest.raises(net.DisallowedHost):
            net.check_url(bad, net.MICROSOFT_HOSTS, net.MICROSOFT_CONTENT_SUFFIXES)
