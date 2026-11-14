import contextlib
import json
import stat
import zipfile

import pytest

from helpers import files_in, write_tree
from keepsake import snapshot
from keepsake.snapshot import FileEntry, NewerSchemaError, SnapshotError

DEVICE = "d3f1a9c2-0000-0000-0000-000000000000"


def make_roots(tmp_path):
    roots = {"winLocalAppData": str(tmp_path / "local"), "winDocuments": str(tmp_path / "docs")}
    for path in roots.values():
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    return roots


def sample(tmp_path):
    roots = make_roots(tmp_path)
    write_tree(
        roots, {("winLocalAppData", "Game/Saves/slot0.sav"): b"slot zero", ("winDocuments", "Game/profile.dat"): b"p"}
    )
    entries = snapshot.scan_entries(files_in(roots), roots)
    blob = str(tmp_path / "blob.zip")
    blob_sha = snapshot.pack(entries, roots, blob)
    meta = snapshot.build_meta(
        game_key="example-game",
        entries=entries,
        parents=[],
        device_id=DEVICE,
        device_name="Handheld",
        device_seq=42,
        kind="auto-exit",
        blob_sha256=blob_sha,
        plugin_version="0.5.0",
        created=1_700_000_000,
    )
    return roots, entries, blob, meta


def test_meta_shape_matches_build_prompt(tmp_path):
    _, entries, _, meta = sample(tmp_path)
    assert meta["schemaVersion"] == 1
    assert meta["snapId"] == f"000042-d3f1a9-{meta['contentHash'][:8]}"
    assert meta["files"][0] == {
        "root": "winDocuments",
        "rel": "Game/profile.dat",
        "size": 1,
        "sha256": entries[0].sha256,
    }
    assert meta["created"] == "2023-11-14T22:13:20Z"
    assert snapshot.validate_meta(json.loads(snapshot.meta_bytes(meta))) == meta


def test_content_hash_is_order_independent_and_sensitive():
    a = FileEntry("winAppData", "a", 1, "0" * 64)
    b = FileEntry("winAppData", "b", 2, "1" * 64)
    assert snapshot.content_hash([a, b]) == snapshot.content_hash([b, a])
    assert snapshot.content_hash([a]) != snapshot.content_hash([FileEntry("winAppData", "a", 1, "2" * 64)])
    assert snapshot.content_hash([a]) != snapshot.content_hash([FileEntry("base", "a", 1, "0" * 64)])


def test_verify_blob_accepts_good_blob(tmp_path):
    _, _, blob, meta = sample(tmp_path)
    snapshot.verify_blob(blob, meta)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda m: m.update(schemaVersion=1, contentHash="0" * 64),
        lambda m: m["files"][0].update(rel="../escape"),
        lambda m: m["files"][0].update(rel="/abs"),
        lambda m: m["files"][0].update(root="nowhere"),
        lambda m: m["files"][0].update(size=-1),
        lambda m: m.update(snapId="not-an-id"),
        lambda m: m.update(kind="weird"),
        lambda m: m.update(parents=["../x"]),
        lambda m: m["files"].append(dict(m["files"][0])),
    ],
)
def test_validate_meta_rejects_tampering(tmp_path, tamper):
    _, _, _, meta = sample(tmp_path)
    tamper(meta)
    with pytest.raises(SnapshotError):
        snapshot.validate_meta(meta)


def test_newer_schema_is_a_distinct_error(tmp_path):
    _, _, _, meta = sample(tmp_path)
    meta["schemaVersion"] = 2
    with pytest.raises(NewerSchemaError):
        snapshot.validate_meta(meta)


def test_pack_detects_file_changed_since_scan(tmp_path):
    roots, entries, _, _ = sample(tmp_path)
    write_tree(roots, {("winLocalAppData", "Game/Saves/slot0.sav"): b"changed!!"})
    with pytest.raises(SnapshotError, match="changed while packing"):
        snapshot.pack(entries, roots, str(tmp_path / "again.zip"))


def craft(tmp_path, meta, entries, mutate):
    """Build a zip by hand, letting ``mutate(archive)`` add hostile entries."""
    path = str(tmp_path / "crafted.zip")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        mutate(archive)
    meta = dict(meta, blobSha256=snapshot.hash_file(path)[1])
    return path, meta


def good_entries(archive, meta, skip=None):
    for f in meta["files"]:
        if f["rel"] != skip:
            archive.writestr(f"{f['root']}/{f['rel']}", b"slot zero" if f["rel"].endswith(".sav") else b"p")


@pytest.mark.parametrize(
    ("name", "mutate", "message"),
    [
        (
            "slip",
            lambda a, m: (good_entries(a, m), a.writestr("winDocuments/../../evil", b"x")),
            "unexpected zip entry",
        ),
        ("absolute", lambda a, m: (good_entries(a, m), a.writestr("/etc/passwd", b"x")), "unexpected zip entry"),
        ("missing", lambda a, m: good_entries(a, m, skip="Game/profile.dat"), "missing"),
        (
            "duplicate",
            lambda a, m: (good_entries(a, m), a.writestr("winDocuments/Game/profile.dat", b"p")),
            "duplicate",
        ),
        (
            "wrong content",
            lambda a, m: (
                a.writestr("winDocuments/Game/profile.dat", b"q"),
                a.writestr("winLocalAppData/Game/Saves/slot0.sav", b"slot zero"),
            ),
            "does not match its hash",
        ),
    ],
)
def test_hostile_zips_rejected(tmp_path, name, mutate, message):
    _, entries, _, meta = sample(tmp_path)
    with pytest.warns(UserWarning) if name == "duplicate" else contextlib.nullcontext():
        path, meta2 = craft(tmp_path, meta, entries, lambda a: mutate(a, meta))
    with pytest.raises(SnapshotError, match=message):
        snapshot.verify_blob(path, meta2)


def test_symlink_entry_rejected(tmp_path):
    _, entries, _, meta = sample(tmp_path)

    def mutate(archive):
        archive.writestr("winLocalAppData/Game/Saves/slot0.sav", b"slot zero")
        info = zipfile.ZipInfo("winDocuments/Game/profile.dat")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"p")

    path, meta2 = craft(tmp_path, meta, entries, mutate)
    with pytest.raises(SnapshotError, match="not a regular file"):
        snapshot.verify_blob(path, meta2)


def test_compression_bomb_rejected(tmp_path):
    roots = make_roots(tmp_path)
    write_tree(roots, {("winDocuments", "zeros.bin"): b"\0" * 5_000_000})
    entries = snapshot.scan_entries(files_in(roots), roots)
    blob = str(tmp_path / "bomb.zip")
    sha = snapshot.pack(entries, roots, blob)
    meta = snapshot.build_meta(
        game_key="g",
        entries=entries,
        parents=[],
        device_id=DEVICE,
        device_name="h",
        device_seq=1,
        kind="manual",
        blob_sha256=sha,
        plugin_version="x",
    )
    with pytest.raises(SnapshotError, match="compression ratio"):
        snapshot.verify_blob(blob, meta)


def test_blob_hash_mismatch_rejected(tmp_path):
    _, _, blob, meta = sample(tmp_path)
    meta["blobSha256"] = "f" * 64
    with pytest.raises(SnapshotError, match="blob hash"):
        snapshot.verify_blob(blob, meta)


def test_extract_only_into_its_base(tmp_path):
    _, entries, blob, meta = sample(tmp_path)
    out = tmp_path / "out"
    snapshot.extract(blob, meta, entries, lambda e: (str(out / e.root), e.rel))
    assert (out / "winLocalAppData" / "Game" / "Saves" / "slot0.sav").read_bytes() == b"slot zero"
    foreign = FileEntry("winDocuments", "Game/other.dat", 1, "0" * 64)
    with pytest.raises(SnapshotError, match="not in this snapshot"):
        snapshot.extract(blob, meta, [foreign], lambda e: (str(out), e.rel))
