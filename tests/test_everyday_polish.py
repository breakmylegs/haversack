"""R2, everyday polish (ADR-0049): newer saves before play, combined playtime, mains-powered devices,
What's new and first-run tips. Synthetic devices, games and saves only."""

import os
import sys
from datetime import UTC, datetime

import pytest

from keepsake import devices, playtime, power
from keepsake.advisor import recommend, stack
from keepsake.app import newer_save, whats_new
from keepsake.store import LocalFolderStore, StoreError, StoreUnavailable
from test_app_ux import pair, run  # noqa: F401 - the fixture

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

NOW = datetime(2026, 11, 16, tzinfo=UTC)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


# Mains-powered devices


def test_a_system_battery_is_told_apart_from_a_controller_battery(tmp_path):
    supplies = tmp_path / "sys/class/power_supply"
    write(str(supplies / "AC/type"), "Mains")
    write(str(supplies / "controller/type"), "Battery")
    write(str(supplies / "controller/scope"), "Device")  # a gamepad, not the machine
    assert power.linux_battery(str(tmp_path)) is False
    write(str(supplies / "BAT0/type"), "Battery")
    assert power.linux_battery(str(tmp_path)) is True
    assert power.linux_battery(str(tmp_path / "nowhere")) is None  # cannot tell


def test_windows_battery_flags():
    assert power.battery_present(platform="win32", flag_reader=lambda: 128) is False
    assert power.battery_present(platform="win32", flag_reader=lambda: 8) is True  # charging
    assert power.battery_present(platform="win32", flag_reader=lambda: 255) is None
    assert power.battery_present(platform="win32", flag_reader=lambda: None) is None


def test_device_facts_carry_the_battery_and_advisor_skips_battery_and_tdp_on_mains(tmp_path):
    write(str(tmp_path / "sys/class/power_supply/AC/type"), "Mains")
    write(str(tmp_path / "proc/cpuinfo"), "model name\t: Synthetic Desktop CPU\n")
    facts = devices.read_facts(str(tmp_path))
    assert facts["battery"] is False
    profiles = devices.load_profiles()
    device, how = devices.resolve(profiles, facts)
    assert how == "generic"
    tools = stack.load_tools()
    report = {
        "power": {"tdp_w": 15},
        "battery": {"draw_w": 20, "minutes": 120},
    }
    mains = {**device, "mains_only": True}
    on_mains = recommend.build([], profiles, tools, mains, {}, "medium", False, NOW)[-1]
    on_battery = recommend.build([], profiles, tools, device, {}, "medium", False, NOW)[-1]
    assert on_mains["lines"]["power"] == [recommend.MAINS_POWER_LINE]
    assert on_battery["lines"]["power"] != [recommend.MAINS_POWER_LINE]
    assert recommend.battery_lines(report, device)  # a battery estimate exists in general
    with_battery = {**on_battery, "battery": report["battery"]}
    assert recommend.translate(with_battery, tools, device, {})["lines"]["battery"]
    assert recommend.translate(with_battery, tools, mains, {})["lines"]["battery"] == []


# Newer save from another device


def test_a_newer_save_from_another_device_is_shown_then_brought_in_without_a_session(pair):  # noqa: F811
    a, b = pair

    async def go():
        for d in (a, b):
            await d.app.update_game_config(d.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"v1")
        await a.app.sync_push(a.key)
        await b.app.sync_pull(b.key)  # b adopts v1
        await b.app.sync_push(b.key)  # session closed
        (a.saves / "slot.sav").write_bytes(b"v2 from a")
        await a.app.sync_push(a.key)
        await b.app.idle_pass()  # prefetch notices the newer save
        games = {g["key"]: g for g in await b.app.match_games()}
        summary = await b.app.qam_summary()
        await a.app.idle_pass()  # a sees only its own save as the head
        own = {g["key"]: g for g in await a.app.match_games()}
        brought = await b.app.bring_newer(b.key)
        after = {g["key"]: g for g in await b.app.match_games()}
        state = b.app._sync().state.get(games[b.key]["gameKey"])
        return games, summary, own, brought, after, state

    games, summary, own, brought, after, state = run(go())
    newer = games[b.key]["newer"]
    assert newer["device"] == "Handheld A" and newer["created"]
    assert summary["newer"] == [{"key": b.key, "name": "Example Quest", **newer}]
    assert own[a.key]["newer"] is None  # a device's own save is never "newer from elsewhere"
    assert brought["action"] == "restored" and (b.saves / "slot.sav").read_bytes() == b"v2 from a"
    assert after[b.key]["newer"] is None
    assert not state.get("sessionOpen")  # outside a launch: no play session was opened
    assert state.get("newer") is None  # cleared in the sync state too, not only hidden


def test_getting_a_newer_save_never_overwrites_progress_made_here(pair):  # noqa: F811
    a, b = pair

    async def go():
        for d in (a, b):
            await d.app.update_game_config(d.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"v1")
        await a.app.sync_push(a.key)
        await b.app.sync_pull(b.key)
        await b.app.sync_push(b.key)
        (a.saves / "slot.sav").write_bytes(b"v2 from a")
        await a.app.sync_push(a.key)
        await b.app.idle_pass()
        (b.saves / "slot.sav").write_bytes(b"progress on b")  # played here too, offline
        return await b.app.bring_newer(b.key)

    result = run(go())
    assert result["action"] == "conflict"
    assert (b.saves / "slot.sav").read_bytes() == b"progress on b"


def test_only_a_single_head_from_another_device_counts_as_newer(pair):  # noqa: F811
    a, _ = pair
    sync = a.app._sync()
    own, other = sync.engine.device_id, "bbbbbbbb-0000-0000-0000-000000000002"
    by_id = {
        "base": {"deviceId": own},
        "theirs": {"deviceId": other, "deviceName": "Handheld B", "created": "2026-11-18T10:00:00Z"},
        "mine": {"deviceId": own, "deviceName": "Handheld A", "created": "2026-11-18T10:00:00Z"},
    }
    assert sync._newer_elsewhere("base", ["theirs"], by_id)["device"] == "Handheld B"
    assert sync._newer_elsewhere("base", ["mine"], by_id) is None
    assert sync._newer_elsewhere("base", ["theirs", "mine"], by_id) is None  # a fork is a conflict
    assert sync._newer_elsewhere("base", ["base"], by_id) is None
    assert sync._newer_elsewhere(None, ["theirs"], by_id) is None  # never synced here: adoption, not newer


def test_newer_save_is_hidden_once_taken_in_or_in_conflict():
    found = {"snapId": "000002-aaaaaa-11111111", "device": "Handheld A", "created": "2026-11-18T10:00:00Z"}
    assert newer_save({"base": "000001-bbbbbb-22222222", "newer": found}) == found
    assert newer_save({"base": found["snapId"], "newer": found}) is None
    assert newer_save({"base": "x", "newer": found, "conflict": {"kind": "fork"}}) is None
    assert newer_save({}) is None


# Combined playtime


class FlakyStore(LocalFolderStore):
    def __init__(self, root):
        super().__init__(root)
        self.offline = True

    def put_new(self, key, data):
        if self.offline:
            raise StoreUnavailable("offline")
        return super().put_new(key, data)


def test_sessions_count_only_between_one_minute_and_a_day():
    assert playtime.countable(1000.0, 1059.0) is None
    assert playtime.countable(1000.0, 1060.0) == 60
    assert playtime.countable(1000.0, 1000.0 + 24 * 3600 + 1) is None
    assert playtime.countable(None, 2000.0) is None and playtime.countable(2000.0, 1000.0) is None


def test_sessions_wait_while_offline_and_add_up_from_one_listing(tmp_path):
    store = FlakyStore(str(tmp_path / "cloud"))
    seq = iter(range(1, 100))
    rec = playtime.Recorder(str(tmp_path), lambda: store, "aaaaaaaa-0000-0000-0000-000000000001", lambda: next(seq))
    assert rec.record("example-quest", 1000.0, 1000.0 + 3600) is True
    assert rec.record("example-quest", 5000.0, 5010.0) is False  # too short: never queued
    assert playtime.totals(store, "example-quest")["totalSeconds"] == 0  # offline: queued
    store.offline = False
    assert rec.flush() == 1 and rec.flush() == 0
    other = playtime.Recorder(str(tmp_path / "b"), lambda: store, "bbbbbbbb-0000-0000-0000-000000000002", lambda: 7)
    os.makedirs(tmp_path / "b")
    other.record("example-quest", 0.0, 1800.0)
    store.put_new("games/example-quest/sessions/cccccccc/00000009-999999.json", b"{}")  # beyond a day: ignored
    store.put_new("games/example-quest/sessions/not-a-session.txt", b"x")
    found = playtime.totals(store, "example-quest")
    assert found == {
        "totalSeconds": 5400,
        "sessions": 2,
        "byDevice": {"aaaaaaaa-0000-0000-0000-000000000001": 3600, "bbbbbbbb-0000-0000-0000-000000000002": 1800},
    }


def test_store_errors_while_listing_the_cloud_do_not_lose_the_queue(tmp_path):
    def broken():
        raise StoreError("signed out")

    rec = playtime.Recorder(str(tmp_path), broken, "aaaaaaaa", lambda: 1)
    assert rec.record("example-quest", 0.0, 120.0) is True
    assert len(rec._pending()) == 1


def test_the_app_records_a_play_session_on_exit_and_names_the_devices(pair, monkeypatch):  # noqa: F811
    import keepsake.app as app_module

    a, _ = pair
    played = 2 * 3600 + 300
    monkeypatch.setattr(app_module.time, "time", lambda: 1_790_000_000.0 + played)

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"v1")
        ctx = await a.app._sync_context(a.key)
        a.app._record_session(ctx.game_key, lastStart=1_790_000_000.0)
        game = await a.app._game(a.key)
        await a.app._exit(game)  # the game is not running in the fake process table
        await a.app._exit(game)  # a second exit without a new start counts nothing
        return await a.app.game_playtime(a.key)

    found = run(go())
    assert found["totalSeconds"] == played and found["sessions"] == 1
    assert found["byDevice"] == [{"device": "Handheld A", "seconds": played}]


# What's new and tips


CHANGELOG = """# Changelog

## [Unreleased]

- Not yet.

## [1.2.0]

Short summary.

### Added

- Checkpoints.

## [1.1.0]

- Older.
"""


def test_whats_new_is_the_section_of_the_new_version():
    assert whats_new(CHANGELOG, "1.2.0") == "Short summary.\n\n### Added\n\n- Checkpoints."
    assert whats_new(CHANGELOG, "9.9.9") == ""
    long = "## [2.0.0]\n" + "x" * 5000
    assert len(whats_new(long, "2.0.0")) == 4000


def test_the_startup_notice_carries_the_release_notes(pair):  # noqa: F811
    a, _ = pair
    write(os.path.join(a.app.paths.plugin_dir, "CHANGELOG.md"), CHANGELOG)
    a.app._notice = {"from": "1.1.0", "to": "1.2.0"}
    notice = run(a.app.take_startup_notice())
    assert notice["notes"].endswith("- Checkpoints.") and run(a.app.take_startup_notice()) is None


def test_tips_can_be_dismissed(pair):  # noqa: F811
    a, _ = pair
    assert run(a.app.qam_summary())["tipsDismissed"] is False
    run(a.app.set_setting("tipsDismissed", True))
    assert run(a.app.qam_summary())["tipsDismissed"] is True
    with pytest.raises(ValueError):
        run(a.app.set_setting("tipsDismissed", "yes"))


def test_both_packages_ship_the_changelog(tmp_path, monkeypatch):
    import zipfile

    import package
    from test_scripts import make_repo

    repo = tmp_path / "repo"
    repo.mkdir()
    make_repo(repo)
    monkeypatch.setattr(package, "ROOT", str(repo))
    with zipfile.ZipFile(package.build(str(tmp_path / "out"))) as archive:
        assert "Keepsake/CHANGELOG.md" in archive.namelist()
    with zipfile.ZipFile(package.build_desktop(str(tmp_path / "out2"))) as archive:
        assert "Keepsake-desktop/CHANGELOG.md" in archive.namelist()
