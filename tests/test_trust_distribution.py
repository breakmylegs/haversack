"""R3, trust and distribution (ADR-0050): cloud integrity, export, the SBOM and the performance budget.
Synthetic games and saves only."""

import json
import os
import sys
import zipfile

import pytest

from keepsake import app as app_module
from keepsake.app import export_folder, safe_name
from keepsake.snapshot import verify_blob
from test_app_ux import pair, run  # noqa: F401 - the fixture

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import perf_budget
import sbom


def blob_path(tmp_path, game_key, snap_id):
    return tmp_path / "cloud" / "games" / game_key / "blobs" / f"{snap_id}.zip"


async def two_snapshots(device):
    await device.app.update_game_config(device.key, {"enabled": True})
    (device.saves / "slot.sav").write_bytes(b"first")
    first = await device.app.snapshot_game(device.key)
    (device.saves / "slot.sav").write_bytes(b"second")
    second = await device.app.snapshot_game(device.key)
    game_key = (await device.app._snapshot_context(device.key))["gameKey"]
    return game_key, first["snapId"], second["snapId"]


# Cloud integrity


def test_the_scrub_finds_damaged_and_missing_snapshots_and_health_says_so(pair, tmp_path):  # noqa: F811
    a, _ = pair

    async def go():
        game_key, first, second = await two_snapshots(a)
        before = await a.app.scrub_cloud(full=True)
        damaged = blob_path(tmp_path, game_key, first)
        damaged.write_bytes(b"not the original zip")
        blob_path(tmp_path, game_key, second).unlink()
        after = await a.app.scrub_cloud(full=True)
        listing = await a.app.list_snapshots(a.key)
        checks = {c["id"]: c for c in (await a.app.health_checks(False))["checks"]}
        return game_key, first, second, before, after, listing, checks

    game_key, first, second, before, after, listing, checks = run(go())
    assert before["games"][game_key] == {"name": "Example Quest", "key": a.key, "checked": 2, "bad": [], "missing": []}
    assert after["games"][game_key]["bad"] == [first] and after["games"][game_key]["missing"] == [second]
    assert listing["damaged"] == sorted([first, second])
    assert checks["integrity"]["status"] == "warn" and checks["integrity"]["items"] == ["Example Quest: 2 snapshots"]


def test_the_weekly_scrub_checks_only_what_restores_rely_on_and_only_once_a_week(pair, tmp_path, monkeypatch):  # noqa: F811
    a, _ = pair

    async def go():
        game_key, first, second = await two_snapshots(a)
        blob_path(tmp_path, game_key, first).write_bytes(b"old and damaged")  # not a head, base or pin
        await a.app._weekly_scrub()
        report = json.loads((tmp_path / "a" / "runtime" / app_module.SCRUB_FILE).read_text())
        blob_path(tmp_path, game_key, second).write_bytes(b"now the head is damaged")
        await a.app._weekly_scrub()  # less than a week later: not run again
        same = json.loads((tmp_path / "a" / "runtime" / app_module.SCRUB_FILE).read_text())
        monkeypatch.setattr(app_module.time, "time", lambda: report["lastRun"] + app_module.SCRUB_INTERVAL + 1)
        await a.app._weekly_scrub()
        later = json.loads((tmp_path / "a" / "runtime" / app_module.SCRUB_FILE).read_text())
        return game_key, second, report, same, later

    game_key, second, report, same, later = run(go())
    assert report["games"][game_key]["checked"] == 1 and report["games"][game_key]["bad"] == []
    assert same == report
    assert later["games"][game_key]["bad"] == [second]


def test_repair_saves_a_fresh_snapshot_under_a_new_id(pair, tmp_path):  # noqa: F811
    a, _ = pair

    async def go():
        game_key, _first, second = await two_snapshots(a)
        blob_path(tmp_path, game_key, second).write_bytes(b"damaged")
        repaired = await a.app.repair_snapshot(a.key)
        listing = await a.app.list_snapshots(a.key)
        return game_key, second, repaired, listing

    game_key, second, repaired, listing = run(go())
    assert repaired["status"] == "published" and repaired["snapId"] != second
    assert listing["snapshots"][0]["snapId"] == repaired["snapId"] and listing["snapshots"][0]["base"] is True
    meta = a.app._engine().get_meta(game_key, repaired["snapId"])
    verify_blob(str(blob_path(tmp_path, game_key, repaired["snapId"])), meta)  # intact
    assert "repair" in meta["flags"]


# Export


def test_export_writes_verified_zips_an_index_and_a_readme_and_never_overwrites(pair, tmp_path):  # noqa: F811
    a, _ = pair
    target = tmp_path / "sdcard"
    target.mkdir()

    async def go():
        game_key, first, second = await two_snapshots(a)
        latest = await a.app.export_snapshots(str(target), "latest")
        everything = await a.app.export_snapshots(str(target), "all")
        return game_key, first, second, latest, everything

    _game_key, first, second, latest, everything = run(go())
    assert latest["snapshots"] == 1 and everything["snapshots"] == 2
    assert latest["folder"] != everything["folder"]  # a second export never reuses the first folder
    folder = target / os.path.basename(everything["folder"])
    index = json.loads((folder / "index.json").read_text())
    assert sorted(i["snapId"] for i in index) == sorted([first, second])
    assert all(i["files"] == ["winLocalAppData/ExampleQuest/slot.sav"] for i in index)
    with zipfile.ZipFile(folder / index[-1]["zip"]) as archive:
        assert archive.read("winLocalAppData/ExampleQuest/slot.sav") in (b"first", b"second")
    assert "winLocalAppData" in (folder / "README.txt").read_text()
    only = [p.name for p in (target / os.path.basename(latest["folder"]) / "Example Quest").iterdir()]
    assert len(only) == 1 and second in only[0]


def test_export_refuses_a_bad_folder_or_scope(pair, tmp_path):  # noqa: F811
    a, _ = pair
    with pytest.raises(ValueError, match="choose a folder"):
        export_folder("relative/path")
    with pytest.raises(ValueError, match="does not exist"):
        export_folder(str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="latest"):
        run(a.app.export_snapshots(str(tmp_path), "some"))
    with pytest.raises(ValueError, match="nothing to export"):
        run(a.app.export_snapshots(str(tmp_path), "latest"))  # no game syncs yet


def test_safe_names_work_on_every_file_system():
    assert safe_name('Quest: The "Return" / Part 2?') == "Quest_ The _Return_ _ Part 2_"
    assert safe_name("Trailing dots...") == "Trailing dots"
    assert safe_name("\x01") == "_" and safe_name("") == "Unnamed game"
    assert len(safe_name("x" * 200)) == 80


# The SBOM


LOCK = """lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      '@decky/api':
        specifier: ^1.1.3
        version: 1.1.3
      react-icons:
        specifier: ^5.3.0
        version: 5.7.0(react@19.3.1)
    devDependencies:
      typescript:
        specifier: ^5.6.0
        version: 5.9.3

  other:
    dependencies:
      left-pad:
        specifier: 1.0.0
        version: 1.0.0
"""


def test_locked_versions_reads_the_root_dependencies_only():
    assert sbom.locked_versions(LOCK) == {"@decky/api": "1.1.3", "react-icons": "5.7.0"}


def test_the_sbom_lists_what_the_release_ships_and_is_deterministic():
    first, second = sbom.build(), sbom.build()
    assert first == second and "timestamp" not in json.dumps(first)
    names = [c["name"] for c in first["components"]]
    assert names == ["@decky/api", "qrcode-generator", "react-icons", "tslib", "pyasn1", "pysmb"]
    assert "@decky/ui" not in names  # provided by Decky at run time, not in the bundle
    pysmb = first["components"][-1]
    assert pysmb["licenses"] == [{"license": {"id": "Zlib"}}] and pysmb["hashes"][0]["alg"] == "SHA-256"
    assert first["components"][0]["purl"] == "pkg:npm/%40decky/api@1.1.3"


# The performance budget


def test_the_performance_budget_measures_every_path_and_fails_when_over(monkeypatch, capsys):
    results = perf_budget.run()
    assert set(results) == set(perf_budget.BUDGETS)
    monkeypatch.setattr(perf_budget, "run", lambda: {name: 0.0 for name in perf_budget.BUDGETS})
    assert perf_budget.main() == 0
    monkeypatch.setattr(perf_budget, "run", lambda: {name: 99.0 for name in perf_budget.BUDGETS})
    assert perf_budget.main() == 1
    assert "over budget" in capsys.readouterr().out


def test_an_export_file_that_already_exists_is_never_overwritten(pair, tmp_path):  # noqa: F811
    a, _ = pair

    async def go():
        game_key, _first, second = await two_snapshots(a)
        dest = tmp_path / "taken.zip"
        dest.write_bytes(b"someone else's file")
        with pytest.raises(FileExistsError):
            a.app._engine().download_verified(game_key, second, str(dest))
        return dest.read_bytes()

    assert run(go()) == b"someone else's file"


def test_a_snapshot_whose_files_are_only_missing_is_reported_too():
    from keepsake import health

    report = {"lastRun": 1_800_000_000.0, "games": {"g": {"name": "Example Quest", "bad": [], "missing": ["s1"]}}}
    check = {c["id"]: c for c in health.run({"now": 1_800_000_100.0, "integrity": report})}["integrity"]
    assert check["status"] == "warn" and check["items"] == ["Example Quest: 1 snapshots"]
    clean = {"lastRun": 1_800_000_000.0, "games": {"g": {"name": "Example Quest", "bad": [], "missing": []}}}
    assert {c["id"]: c for c in health.run({"now": 1_800_000_100.0, "integrity": clean})}["integrity"]["status"] == "ok"
    assert {c["id"]: c for c in health.run({"now": 1.0})}["integrity"]["status"] == "info"


def test_packages_decky_provides_at_run_time_are_left_out_of_the_sbom(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"version": "1.0.0", "dependencies": {"@decky/ui": "^4", "react": "^19", "tslib": "^2"}})
    )
    (tmp_path / "pnpm-lock.yaml").write_text(
        "importers:\n\n  .:\n    dependencies:\n      tslib:\n        specifier: ^2\n        version: 2.9.1\n"
    )
    vendor = tmp_path / "py_modules" / "keepsake" / "_vendor"
    vendor.mkdir(parents=True)
    (vendor / "MANIFEST.json").write_text(json.dumps({"libraries": [], "files": {}}))
    assert [c["name"] for c in sbom.build(str(tmp_path))["components"]] == ["tslib"]
