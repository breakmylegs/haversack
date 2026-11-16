"""Import every game at once (Peter's device run, 16 November 2026). Synthetic backups only."""

import asyncio

import pytest

from keepsake.app import import_verdict
from keepsake.store import LocalFolderStore
from test_app_ux import Device
from test_ludusavi import SLOT, make_simple_game, put


def library(tmp_path):
    backups = tmp_path / "ludusavi"
    make_simple_game(backups, "Alpha Game")
    broken = make_simple_game(backups, "Broken Game")
    put(broken, "backup-20260101T000000Z", SLOT, b"v9")  # does not match its recorded hash
    make_simple_game(backups, "Charlie Game")
    (backups / "Unreadable Game").mkdir()  # no mapping.yaml: left out
    return backups


async def finished(app):
    for _ in range(400):
        status = await app.ludusavi_import_status()
        if not status["running"]:
            return status
        await asyncio.sleep(0.05)
    raise AssertionError("the import of every game did not finish")


def test_every_game_is_imported_one_failing_does_not_stop_the_rest_and_a_rerun_is_safe(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    backups = library(tmp_path)

    async def go():
        started = await a.app.ludusavi_import_all(str(backups), "all")
        first = await finished(a.app)
        again_started = await a.app.ludusavi_import_all(str(backups), "all")
        again = await finished(a.app)
        return started, first, again_started, again

    started, first, again_started, again = asyncio.run(go())
    assert started["total"] == 3 and again_started["total"] == 3  # the unreadable folder is left out
    assert first["summary"] == {"imported": 2, "already-imported": 0, "nothing-to-import": 0, "failed": 1}
    assert (
        first["games"]["Broken Game"]["status"] == "failed"
        and "does not match" in first["games"]["Broken Game"]["error"]
    )
    assert first["games"]["Charlie Game"]["status"] == "imported"  # after the failing one: it carried on
    assert first["done"] == 3 and first["cancelled"] is False
    assert again["summary"] == {"imported": 0, "already-imported": 2, "nothing-to-import": 0, "failed": 1}
    progress = [args[0] for event, args in a.events if event == "keepsake_import_progress"]
    assert [p["current"] for p in progress if p["running"]][:3] == ["Alpha Game", "Broken Game", "Charlie Game"]
    assert progress[-1]["running"] is False


def test_latest_only_imports_one_backup_per_game(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    backups = library(tmp_path)

    async def go():
        await a.app.ludusavi_import_all(str(backups), "latest")
        return await finished(a.app)

    status = asyncio.run(go())
    assert [len(status["games"][g]["results"]) for g in ("Alpha Game", "Charlie Game")] == [1, 1]
    # Broken Game's latest backup is the differential one, whose own copy of the file is good: it imports too.
    assert status["summary"]["imported"] == 3


def test_cancel_stops_between_games_and_a_second_run_is_refused(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    backups = library(tmp_path)

    async def go():
        await a.app.ludusavi_import_all(str(backups), "all")
        with pytest.raises(ValueError, match="already running"):
            await a.app.ludusavi_import_all(str(backups), "all")
        await a.app.ludusavi_import_cancel()
        status = await finished(a.app)
        with pytest.raises(ValueError, match="latest backup or all"):
            await a.app.ludusavi_import_all(str(backups), "everything")
        return status

    status = asyncio.run(go())
    assert status["cancelled"] is True and status["done"] < status["total"]


def test_import_verdicts():
    assert import_verdict([{"status": "published"}, {"status": "already-imported"}], None) == "imported"
    assert import_verdict([{"status": "already-imported"}] * 2, None) == "already-imported"
    assert import_verdict([{"status": "nothing-to-import"}], None) == "nothing-to-import"
    assert import_verdict([{"status": "published"}, {"status": "error"}], None) == "failed"
    assert import_verdict([], "the cloud could not be reached") == "failed"
    assert import_verdict([], None) == "nothing-to-import"


def test_a_game_whose_import_raises_is_recorded_and_the_rest_carry_on(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    backups = library(tmp_path)
    real = a.app.ludusavi_import

    async def flaky(root, folder, ids, game_key):
        if folder == "Alpha Game":
            raise RuntimeError("synthetic failure")
        return await real(root, folder, ids, game_key)

    a.app.ludusavi_import = flaky

    async def go():
        await a.app.ludusavi_import_all(str(backups), "latest")
        return await finished(a.app)

    status = asyncio.run(go())
    assert status["games"]["Alpha Game"] == {
        "name": "Alpha Game",
        "status": "failed",
        "error": "synthetic failure",
        "results": [],
    }
    assert status["summary"] == {"imported": 2, "already-imported": 0, "nothing-to-import": 0, "failed": 1}
