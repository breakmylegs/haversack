"""Slice 9 backend: QAM summary, conflicts, history, setup wizard, health and shared game settings.

Two simulated devices with different shortcut app IDs share one local store,
standing in for OneDrive.
"""

import asyncio
import json

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths
from keepsake.store import LocalFolderStore, StoreUnavailable

MANIFEST = '---\nExample Quest:\n  files:\n    "<winLocalAppData>/ExampleQuest":\n      tags:\n        - save\n'


class Device:
    def __init__(self, tmp_path, name, appid, shared):
        base = tmp_path / name
        home = base / "home"
        home.mkdir(parents=True)
        root = make_fake_steam(
            home, users={"7": [shortcut_entry(appid - 2**32, "Example Quest", "/g.exe")]}, prefixes=[(None, appid)]
        )
        self.key = f"shortcut:7:{appid}"
        prefix = root / "steamapps/compatdata" / str(appid) / "pfx"
        self.saves = prefix / "drive_c/users/steamuser/AppData/Local/ExampleQuest"
        self.saves.mkdir(parents=True)
        self.events = []

        async def emit(event, *args):
            self.events.append((event, args))

        paths = PluginPaths(*(str(base / n) for n in ("settings", "runtime", "logs", "plugin")))
        self.app = KeepsakeApp(
            paths, emit=emit, proc_root=str(base / "proc"), version="0.9.0", home=str(home), auto_refresh_manifest=False
        )
        manifest_file = base / "manifest.yaml"
        manifest_file.write_text(MANIFEST)
        self.app.manifest.import_file(str(manifest_file))
        self.app.settings.set("deviceName", f"Handheld {name.upper()}")
        self.store = shared
        self.app._store = lambda: self.store

    def toasts(self):
        return [args[0] for event, args in self.events if event == "keepsake_toast"]


@pytest.fixture
def pair(tmp_path):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    return Device(tmp_path, "a", 4171510507, shared), Device(tmp_path, "b", 4171510999, shared)


def run(coro):
    return asyncio.run(coro)


def test_qam_summary_tracks_the_current_game_and_last_sync(pair):
    a, _ = pair

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        idle = await a.app.qam_summary()
        await a.app.sync_pull(a.key)  # launch: a session opens
        playing = await a.app.qam_summary()
        (a.saves / "slot.sav").write_bytes(b"progress")
        await a.app.sync_push(a.key)
        after = await a.app.qam_summary()
        return idle, playing, after

    idle, playing, after = run(go())
    assert idle["currentGame"] is None and idle["lastSync"] is None and idle["enabledGames"] == 1
    assert idle["setupComplete"] is False and idle["deviceName"] == "Handheld A"
    assert playing["currentGame"] == {"key": a.key, "name": "Example Quest", "status": "not-synced"}
    assert after["currentGame"] is None and after["lastSync"] is not None
    assert after["health"] == "warn" and "Cloud sign-in and reachability" in after["problems"]  # local test store


def test_match_games_reports_enabled_and_sync_status(pair):
    a, _ = pair

    async def go():
        before = (await a.app.match_games())[0]
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"progress")
        await a.app.sync_push(a.key)
        return before, (await a.app.match_games())[0]

    before, after = run(go())
    assert before["enabled"] is False and before["sync"] == "off"
    assert after["enabled"] is True and after["sync"] == "synced"


def test_conflicts_details_history_and_plan(pair):
    a, b = pair

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"from a")
        await a.app.sync_push(a.key)
        (b.saves / "slot.sav").write_bytes(b"from b")
        plan = await b.app.plan_sync([b.key, "shortcut:7:1"])
        await b.app.update_game_config(b.key, {"enabled": True})
        await b.app.sync_pull(b.key)  # adoption conflict: never overwritten
        conflicts = await b.app.list_conflicts()
        details = await b.app.conflict_details(b.key)
        history = await b.app.recent_history(10)
        summary = await b.app.qam_summary()
        return plan, conflicts, details, history, summary

    plan, conflicts, details, history, summary = run(go())
    assert plan[0] == {"key": b.key, "name": "Example Quest", "action": "conflict", "reason": "adoption"}
    assert plan[1]["action"] == "error"  # an unknown game is reported, not fatal
    assert [c["key"] for c in conflicts] == [b.key] and conflicts[0]["conflict"]["kind"] == "adoption"
    assert details["hasBase"] is False
    assert [s["side"] for s in details["sides"]] == ["local", "cloud"]
    assert details["sides"][1]["device"] == "Handheld A"
    assert (b.saves / "slot.sav").read_bytes() == b"from b"
    assert history["errors"] == []
    assert history["snapshots"][0]["name"] == "Example Quest" and history["snapshots"][0]["device"] == "Handheld A"
    assert summary["conflicts"] == 1


def test_finish_setup_enables_games_and_marks_setup_done(pair):
    a, _ = pair

    async def go():
        result = await a.app.finish_setup([a.key])
        config = a.app.game_configs.get(a.key)
        await a.app.stop()  # cancels the first sync it started
        return result, config

    result, config = run(go())
    assert result == {"ok": True, "enabled": 1}
    assert config["enabled"] is True and a.app.settings.get("setupComplete") is True


def test_setup_is_marked_done_for_upgraded_installs(tmp_path):
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "games.json").write_text(json.dumps({"shortcut:7:1": {"enabled": True}}))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.9.0", auto_refresh_manifest=False)
    run(app.start())
    assert app.settings.get("setupComplete") is True


def test_shared_settings_reach_the_other_device(pair):
    a, b = pair

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        await a.app.update_game_config(a.key, {"exclusions": ["*.bak"], "aliases": ["EQ"]})
        await b.app.update_game_config(b.key, {"enabled": True})  # enabling fetches shared settings
        return b.app.game_configs.get(b.key), await b.app.game_config_sync(b.key)

    config, where = run(go())
    assert config["exclusions"] == ["*.bak"] and config["aliases"] == ["EQ"]
    assert where["appliedFrom"] == "Handheld A" and where["pending"] is False and where["concurrent"] == []


def test_concurrent_edits_apply_the_newest_and_warn(pair):
    a, b = pair

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        await b.app.update_game_config(b.key, {"enabled": True})
        await a.app.update_game_config(a.key, {"aliases": ["from a"]})
        await b.app.update_game_config(b.key, {"aliases": ["from b"]})  # same base as A's edit
        await a.app.sync_now()
        return a.app.game_configs.get(a.key), await a.app.game_config_sync(a.key)

    config, where = run(go())
    assert config["aliases"] == ["from b"]
    assert where["concurrent"] == ["Handheld A"]


def test_settings_changed_offline_are_shared_later(pair, monkeypatch):
    a, b = pair

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        await a.app.update_game_config(a.key, {"aliases": ["EQ"]})  # an earlier, published revision
        real = a.store.put_new

        def offline(key, data):
            raise StoreUnavailable("offline")

        monkeypatch.setattr(a.store, "put_new", offline)
        await a.app.update_game_config(a.key, {"exclusions": ["*.tmp"]})
        pending = await a.app.game_config_sync(a.key)
        monkeypatch.setattr(a.store, "put_new", real)
        await a.app.idle_pass()
        await b.app.update_game_config(b.key, {"enabled": True})
        return pending, await a.app.game_config_sync(a.key), b.app.game_configs.get(b.key)

    pending, after, other = run(go())
    assert pending["pending"] is True
    assert after["pending"] is False
    assert other["exclusions"] == ["*.tmp"] and other["aliases"] == ["EQ"]
    assert a.app.game_configs.get(a.key)["exclusions"] == ["*.tmp"]  # the older revision never overwrote it


def test_a_good_save_after_a_quarantined_one_clears_the_flag(pair):
    a, _ = pair

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        for n in range(4):
            (a.saves / f"slot{n}.sav").write_bytes(b"x" * 100)
        await a.app.sync_push(a.key)
        for n in range(3):
            (a.saves / f"slot{n}.sav").unlink()
        quarantined = await a.app.sync_push(a.key)
        for n in range(3):
            (a.saves / f"slot{n}.sav").write_bytes(b"y" * 100)  # the files come back with new progress
        published = await a.app.sync_push(a.key)
        return quarantined, published, (await a.app.match_games())[0]["sync"]

    quarantined, published, status = run(go())
    assert quarantined["status"] == "quarantined" and published["status"] == "published"
    assert status == "synced"


def test_releasing_a_quarantined_snapshot_clears_the_flag(pair):
    a, _ = pair

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        for n in range(4):
            (a.saves / f"slot{n}.sav").write_bytes(b"x" * 100)
        await a.app.sync_push(a.key)
        for n in range(3):
            (a.saves / f"slot{n}.sav").unlink()
        pushed = await a.app.sync_push(a.key)  # three of four files gone: safety gate
        quarantined = (await a.app.match_games())[0]["sync"]
        checks = await a.app.health_checks(False)
        await a.app.release_quarantine(a.key, pushed["snapId"], True)
        return pushed, quarantined, checks, (await a.app.match_games())[0]["sync"]

    pushed, quarantined, checks, released = run(go())
    assert pushed["status"] == "quarantined" and quarantined == "quarantined"
    assert {c["id"]: c for c in checks["checks"]}["quarantine"]["items"] == ["Example Quest"]
    assert released == "synced"


def test_signin_problem_toasts_once_until_it_recovers(pair):
    a, _ = pair
    a.app.settings.set("snapshotStore", "onedrive")

    async def go():
        a.app.tokens.last_error = "invalid_grant"
        await a.app._warn_signin()
        await a.app._warn_signin()
        a.app.tokens.last_error = None
        await a.app._warn_signin()
        a.app.tokens.last_error = "invalid_grant"
        await a.app._warn_signin()

    run(go())
    assert a.toasts().count("OneDrive sign-in needs attention. Open Haversack, Settings, to sign in again.") == 2


def test_sync_now_refuses_while_busy(pair):
    a, _ = pair

    async def go():
        with a.app.jobs.job("restore"):
            return await a.app.sync_now()

    assert run(go()) == {"ok": False, "reason": "busy"}
