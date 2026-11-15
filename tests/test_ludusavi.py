"""Ludusavi import (slice 10): reading backups, mapping paths, verifying files, and import snapshots."""

import asyncio
import hashlib
import os
import zipfile

import pytest

from keepsake.importers import ludusavi
from keepsake.retention import heads

PFX = "/home/deck/.local/share/Steam/steamapps/compatdata/4171510507/pfx/drive_c/users/steamuser"
SLOT = f"{PFX}/AppData/Local/ExampleQuest/slot1.sav"
OLD = f"{PFX}/AppData/Local/ExampleQuest/old.sav"
DOCS = f"{PFX}/Documents/My Games/ExampleQuest/profile.dat"
ELSEWHERE = "/opt/somewhere/cache.bin"


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def put(folder, backup, path, data):
    target = os.path.join(folder, backup, "drive-0", *path.lstrip("/").split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(data)


def file_block(files, indent):
    lines = []
    for path, data in files.items():
        if data is None:
            lines.append(f'{indent}"{path}": ~')
        else:
            lines += [f'{indent}"{path}":', f"{indent}  hash: {sha1(data)}", f"{indent}  size: {len(data)}"]
    return "\n".join(lines)


def make_simple_game(root, name="Example Quest"):
    folder = root / name
    full = "backup-20260101T000000Z"
    diff = "backup-20260201T000000Z-diff"
    full_files = {SLOT: b"v1", OLD: b"old", DOCS: b"profile", ELSEWHERE: b"cache"}
    diff_files = {SLOT: b"v2", OLD: None}
    for path, data in full_files.items():
        put(folder, full, path, data)
    put(folder, diff, SLOT, b"v2")
    mapping = "\n".join(
        [
            f"name: {name}",
            "drives:",
            '  drive-0: ""',
            "backups:",
            f"  - name: {full}",
            '    when: "2026-01-01T00:00:00Z"',
            "    os: linux",
            "    files:",
            file_block(full_files, "      "),
            "    registry:",
            "      hash: ~",
            "    children:",
            f"      - name: {diff}",
            '        when: "2026-02-01T00:00:00Z"',
            "        os: linux",
            "        files:",
            file_block(diff_files, "          "),
            "        registry: ~",
            "",
        ]
    )
    (folder / "mapping.yaml").write_text(mapping, encoding="utf-8")
    return folder


def make_zip_game(root, name="Zip Game"):
    folder = root / name
    folder.mkdir(parents=True)
    backup = "backup-20260301T000000Z.zip"
    files = {f"{PFX}/AppData/Roaming/ZipGame/save.dat": b"zipped"}
    with zipfile.ZipFile(folder / backup, "w") as archive:
        for path, data in files.items():
            archive.writestr("drive-0/" + path.lstrip("/"), data)
    (folder / "mapping.yaml").write_text(
        "\n".join(
            [
                f"name: {name}",
                "drives:",
                '  drive-0: ""',
                "backups:",
                f"  - name: {backup}",
                '    when: "2026-03-01T00:00:00Z"',
                "    files:",
                file_block(files, "      "),
                "    children: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return folder


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (SLOT, ("winLocalAppData", "ExampleQuest/slot1.sav")),
        (f"{PFX}/AppData/Roaming/G/a.sav", ("winAppData", "G/a.sav")),
        (f"{PFX}/AppData/LocalLow/Dev/G/a.sav", ("winLocalAppDataLow", "Dev/G/a.sav")),
        (f"{PFX}/Saved Games/G/a.sav", ("winSavedGames", "G/a.sav")),
        (DOCS, ("winDocuments", "My Games/ExampleQuest/profile.dat")),
        ("/run/media/deck/SDCARD/steamapps/compatdata/1/pfx/drive_c/users/Public/G/a", ("winPublic", "G/a")),
        ("/home/deck/.local/share/Steam/steamapps/compatdata/9/pfx/drive_c/ProgramData/G/a", ("winProgramData", "G/a")),
        ("C:/Users/Someone/AppData/Roaming/G/a.sav", ("winAppData", "G/a.sav")),
        ("/home/deck/.local/share/G/a.sav", ("xdgData", "G/a.sav")),
        ("/var/home/player/.config/G/a.cfg", ("xdgConfig", "G/a.cfg")),
        ("/home/deck/Games/G/a.sav", ("home", "Games/G/a.sav")),
        ("/home/deck/.local/share/Steam/userdata/12345/440/remote/a.sav", ("steamUserdata", "440/remote/a.sav")),
        (ELSEWHERE, None),
        (f"{PFX}/AppData", None),
        (f"{PFX}/Desktop/a.sav", None),
        (f"{PFX}/AppData/Local/../../../../etc/passwd", None),
    ],
)
def test_paths_map_to_logical_roots_whatever_the_compatdata_id(path, expected):
    assert ludusavi.to_logical(path) == expected


def test_scan_lists_games_backups_and_unreadable_ones(tmp_path):
    make_simple_game(tmp_path)
    make_zip_game(tmp_path)
    (tmp_path / "Broken").mkdir()
    (tmp_path / "Broken" / "mapping.yaml").write_text("name: [unsupported\n")
    (tmp_path / "Not a game").mkdir()
    games = {g["folder"]: g for g in ludusavi.scan(str(tmp_path))}
    assert set(games) == {"Example Quest", "Zip Game", "Broken"}
    assert games["Broken"]["error"]
    backups = games["Example Quest"]["backups"]
    assert [(b["id"], b["kind"], b["files"]) for b in backups] == [
        ("backup-20260101T000000Z", "full", 4),
        ("backup-20260101T000000Z/backup-20260201T000000Z-diff", "differential", 3),
    ]


def test_extract_full_backup_maps_verifies_and_reports_skips(tmp_path):
    folder = make_simple_game(tmp_path / "backups")
    out = ludusavi.extract(str(folder), "backup-20260101T000000Z", str(tmp_path / "stage"))
    assert out["files"] == {
        "winDocuments": ["My Games/ExampleQuest/profile.dat"],
        "winLocalAppData": ["ExampleQuest/old.sav", "ExampleQuest/slot1.sav"],
    }
    assert [s["path"] for s in out["skipped"]] == [ELSEWHERE]
    assert (tmp_path / "stage/winLocalAppData/ExampleQuest/slot1.sav").read_bytes() == b"v1"
    assert out["created"] == pytest.approx(1767225600.0) and out["name"] == "Example Quest"


def test_extract_differential_applies_changes_and_removals(tmp_path):
    folder = make_simple_game(tmp_path / "backups")
    out = ludusavi.extract(str(folder), "backup-20260101T000000Z/backup-20260201T000000Z-diff", str(tmp_path / "s"))
    assert out["files"]["winLocalAppData"] == ["ExampleQuest/slot1.sav"]  # old.sav was removed
    assert (tmp_path / "s/winLocalAppData/ExampleQuest/slot1.sav").read_bytes() == b"v2"
    assert (tmp_path / "s/winDocuments/My Games/ExampleQuest/profile.dat").read_bytes() == b"profile"  # inherited


def test_extract_zip_backup(tmp_path):
    folder = make_zip_game(tmp_path / "backups")
    out = ludusavi.extract(str(folder), "backup-20260301T000000Z.zip", str(tmp_path / "s"))
    assert out["files"] == {"winAppData": ["ZipGame/save.dat"]}
    assert (tmp_path / "s/winAppData/ZipGame/save.dat").read_bytes() == b"zipped"


def test_a_file_that_does_not_match_its_hash_refuses_the_backup(tmp_path):
    folder = make_simple_game(tmp_path / "backups")
    put(folder, "backup-20260101T000000Z", SLOT, b"v9")  # same size, different content
    with pytest.raises(ludusavi.LudusaviError, match="does not match"):
        ludusavi.extract(str(folder), "backup-20260101T000000Z", str(tmp_path / "s"))


def test_a_missing_file_refuses_the_backup(tmp_path):
    folder = make_simple_game(tmp_path / "backups")
    os.unlink(os.path.join(folder, "backup-20260101T000000Z", "drive-0", *DOCS.lstrip("/").split("/")))
    with pytest.raises(ludusavi.LudusaviError, match="missing"):
        ludusavi.extract(str(folder), "backup-20260101T000000Z", str(tmp_path / "s"))


def test_unknown_backup_id(tmp_path):
    folder = make_simple_game(tmp_path / "backups")
    with pytest.raises(ludusavi.LudusaviError):
        ludusavi.extract(str(folder), "backup-nope", str(tmp_path / "s"))


@pytest.mark.posix
@pytest.mark.skipif(os.name != "posix", reason="symlinks need POSIX")
def test_a_symlinked_backup_file_is_refused(tmp_path):
    folder = make_simple_game(tmp_path / "backups")
    target = os.path.join(folder, "backup-20260101T000000Z", "drive-0", *SLOT.lstrip("/").split("/"))
    secret = tmp_path / "outside.txt"
    secret.write_bytes(b"v1")
    os.unlink(target)
    os.symlink(secret, target)
    with pytest.raises(ludusavi.LudusaviError, match="plain file"):
        ludusavi.extract(str(folder), "backup-20260101T000000Z", str(tmp_path / "s"))


def test_import_snapshots_are_never_heads():
    metas = [
        {"snapId": "a", "parents": [], "kind": "auto-exit"},
        {"snapId": "b", "parents": ["a"], "kind": "auto-exit"},
        {"snapId": "i", "parents": [], "kind": "import"},
    ]
    assert heads(metas) == {"b"}


# Through the app, with two devices sharing one store


def test_import_on_one_device_restores_on_the_other(tmp_path):
    from keepsake.store import LocalFolderStore
    from test_app_ux import Device

    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a = Device(tmp_path, "a", 4171510507, shared)
    b = Device(tmp_path, "b", 4171510999, shared)
    backups = tmp_path / "ludusavi"
    make_simple_game(backups)

    async def go():
        scanned = await a.app.ludusavi_scan(str(backups))
        game = next(g for g in scanned["games"] if g["folder"] == "Example Quest")
        ids = [bk["id"] for bk in game["backups"]]
        first = await a.app.ludusavi_import(str(backups), "Example Quest", ids, game["gameKey"])
        again = await a.app.ludusavi_import(str(backups), "Example Quest", ids, game["gameKey"])
        pull = await b.app.sync_pull(b.key)  # imports are history: nothing to pull, no conflict
        listing = await b.app.list_snapshots(b.key)
        newest = next(s for s in listing["snapshots"] if s["kind"] == "import" and s["created"].startswith("2026-02"))
        restored = await b.app.restore_snapshot(b.key, newest["snapId"])
        return game, first, again, pull, listing, restored

    game, first, again, pull, listing, restored = asyncio.run(go())
    assert game["gameKey"] == "example-quest" and game["inManifest"] is True and game["localGame"] == "Example Quest"
    assert [r["status"] for r in first["results"]] == ["published", "published"]
    assert first["results"][0]["skippedCount"] == 1
    assert [r["status"] for r in again["results"]] == ["already-imported", "already-imported"]
    assert pull["reason"] == "no-cloud-snapshots"
    assert sorted(s["created"][:10] for s in listing["snapshots"]) == ["2026-01-01", "2026-02-01"]
    assert restored["status"] == "restored"
    assert (b.saves / "slot1.sav").read_bytes() == b"v2"


def test_import_refuses_a_bad_game_key_or_folder(tmp_path):
    from keepsake.store import LocalFolderStore
    from test_app_ux import Device

    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    with pytest.raises(ValueError, match="game key"):
        asyncio.run(a.app.ludusavi_import(str(tmp_path), "Example Quest", ["x"], "Not A Key"))
    with pytest.raises(ValueError, match="folder"):
        asyncio.run(a.app.ludusavi_import(str(tmp_path), "../escape", ["x"], "example-quest"))
