"""R16 step 2 (ADR-0080): "When saves differ: take the newest", with its clock guard and Undo.

The rules alone, then two simulated handhelds sharing one store, with each device's clock set
on purpose (fast, slow, close) to show the guard refuses whenever time cannot be trusted.
Synthetic games and app IDs only (P12).
"""

import asyncio
import os
import time

import pytest

from keepsake import newest
from test_app_ux import Device

NOW = 1_800_000_000.0


def iso(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def sides(local, cloud, extra=False):
    out = [{"side": "local", "created": iso(local) if local else None}]
    out.append({"side": "cloud", "snapId": "s1", "created": iso(cloud) if cloud else None, "device": "Handheld A"})
    if extra:
        out.append({"side": "cloud", "snapId": "s2", "created": iso(cloud), "device": "PC"})
    return out


# The rules


def test_the_newer_side_wins_when_time_can_be_trusted():
    taken = newest.decide(sides(NOW - 3600, NOW - 600), NOW)
    assert taken["choice"] == "use-cloud" and taken["head"] == "s1" and taken["margin"] == 3000
    assert taken["device"] == "Handheld A"
    assert newest.decide(sides(NOW - 600, NOW - 3600), NOW)["choice"] == "use-local"


@pytest.mark.parametrize(
    ("local", "cloud", "extra", "says"),
    [
        (NOW - 60, NOW - 30, False, "too close"),
        (NOW - 3600, NOW + 3600, False, "clock looks wrong"),  # the other device's clock runs fast
        (NOW + 3600, NOW - 3600, False, "clock looks wrong"),  # this device's files are dated ahead
        (None, NOW - 600, False, "not known"),
        (NOW - 3600, NOW - 600, True, "more than two"),
    ],
)
def test_the_guard_asks_instead(local, cloud, extra, says):
    decided = newest.decide(sides(local, cloud, extra), NOW)
    assert decided["choice"] is None and says in decided["reason"]


def test_just_inside_the_guard():
    assert newest.decide(sides(NOW - 3600, NOW + 299), NOW)["choice"] == "use-cloud"  # under 5 min ahead: allowed
    assert newest.decide(sides(NOW - 120, NOW), NOW)["choice"] == "use-cloud"  # exactly 2 min apart: allowed
    assert newest.decide(sides(NOW - 119, NOW), NOW)["choice"] is None


def test_times_parse_with_zones():
    assert newest.parse_time("2027-01-15T08:00:00Z") == newest.parse_time("2027-01-15T09:00:00+01:00")
    assert newest.parse_time("not a time") is None and newest.parse_time(None) is None


# Two devices


def set_clock(device, offset):
    """Give a device's snapshots a clock ``offset`` seconds out."""
    make = device.app._engine

    def engine():
        made = make()
        made.clock = lambda: time.time() + offset
        return made

    device.app._engine = engine


def age(device, seconds):
    """Date this device's save files ``seconds`` ago (their last change, as Keepsake reads it)."""
    stamp = time.time() - seconds
    for path in device.saves.iterdir():
        os.utime(path, (stamp, stamp))


@pytest.fixture
def pair(tmp_path):
    from keepsake.store import LocalFolderStore

    shared = LocalFolderStore(str(tmp_path / "cloud"))
    return Device(tmp_path, "a", 4171510507, shared), Device(tmp_path, "b", 4171510999, shared)


def fork(a, b):
    """Both devices start in step, then each changes the save while apart: a real fork for b."""

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"shared")
        await a.app.sync_push(a.key)
        await b.app.update_game_config(b.key, {"enabled": True})
        await b.app.sync_pull(b.key)
        (a.saves / "slot.sav").write_bytes(b"from a")
        (b.saves / "slot.sav").write_bytes(b"from b")

    return go


def test_the_newer_save_from_the_other_device_is_taken_and_undo_brings_mine_back(pair):
    a, b = pair

    async def go():
        await fork(a, b)()
        await a.app.sync_push(a.key)  # a's version, dated now
        age(b, 3600)  # b's change is an hour old
        pulled = await b.app.sync_pull(b.key)
        b.app.settings.set("conflictPolicy", "newest")  # after the pull: this test settles it itself
        taken = await b.app.take_newest(b.key)
        after = (b.saves / "slot.sav").read_bytes()
        choice = await b.app.newest_choice(b.key)
        conflicts = await b.app.list_conflicts()
        await b.app.undo_newest(b.key)
        undone = (b.saves / "slot.sav").read_bytes()
        cleared = await b.app.newest_choice(b.key)
        return pulled, taken, after, choice, conflicts, undone, cleared

    pulled, taken, after, choice, conflicts, undone, cleared = asyncio.run(go())
    assert cleared is None  # one Undo per choice
    assert pulled["action"] == "conflict"
    assert taken["status"] == "taken" and taken["choice"] == "use-cloud" and taken["device"] == "Handheld A"
    assert after == b"from a" and conflicts == []
    assert choice["replaced"]  # this device's version, kept pinned
    assert undone == b"from b"  # Undo brings this device's version back
    assert any("kept the other device's newer save from Handheld A" in t for t in b.toasts())


def test_a_device_with_a_fast_clock_never_wins_by_it(pair):
    a, b = pair
    b.app.settings.set("conflictPolicy", "newest")
    set_clock(a, 2 * 3600)  # a's clock runs two hours fast

    async def go():
        await fork(a, b)()
        await a.app.sync_push(a.key)
        age(b, 3600)
        await b.app.sync_pull(b.key)
        return await b.app.take_newest(b.key)

    asked = asyncio.run(go())
    assert asked["status"] == "asked" and "clock looks wrong" in asked["reason"]
    assert (b.saves / "slot.sav").read_bytes() == b"from b"  # nothing replaced
    assert any("clock looks wrong" in t for t in b.toasts())


def test_this_devices_newer_save_is_kept(pair):
    a, b = pair
    b.app.settings.set("conflictPolicy", "newest")
    set_clock(a, -2 * 3600)  # a saved two hours ago, by its clock

    async def go():
        await fork(a, b)()
        await a.app.sync_push(a.key)
        await b.app.sync_pull(b.key)
        taken = await b.app.take_newest(b.key)
        return taken, await b.app.list_conflicts()

    taken, conflicts = asyncio.run(go())
    assert taken["choice"] == "use-local" and conflicts == []
    assert (b.saves / "slot.sav").read_bytes() == b"from b"


def test_saves_too_close_in_time_are_left_to_you(pair):
    a, b = pair
    b.app.settings.set("conflictPolicy", "newest")

    async def go():
        await fork(a, b)()
        await a.app.sync_push(a.key)
        await b.app.sync_pull(b.key)  # both changed just now
        return await b.app.take_newest(b.key), await b.app.list_conflicts()

    asked, conflicts = asyncio.run(go())
    assert asked["status"] == "asked" and "too close" in asked["reason"] and len(conflicts) == 1


def test_ask_me_is_the_default_and_never_takes_anything(pair):
    a, b = pair

    async def go():
        await fork(a, b)()
        await a.app.sync_push(a.key)
        age(b, 3600)
        await b.app.sync_pull(b.key)
        await asyncio.sleep(0.05)
        return await b.app.list_conflicts()

    conflicts = asyncio.run(go())
    assert len(conflicts) == 1 and (b.saves / "slot.sav").read_bytes() == b"from b"
    assert b.app.settings.get("conflictPolicy") == "ask"


def test_with_newest_set_a_manual_pull_settles_it_by_itself(pair):
    a, b = pair
    b.app.settings.set("conflictPolicy", "newest")

    async def go():
        await fork(a, b)()
        await a.app.sync_push(a.key)
        age(b, 3600)
        await b.app.sync_pull(b.key)
        for _ in range(200):  # the settle runs in the background; wait for it, then look
            await asyncio.sleep(0.02)
            if not b.app._newest_running:
                break
        return await b.app.list_conflicts()

    assert asyncio.run(go()) == [] and (b.saves / "slot.sav").read_bytes() == b"from a"


def test_the_setting_is_checked():
    from keepsake.settings import SettingsError, _validate

    assert _validate("conflictPolicy", "newest") == "newest"
    with pytest.raises(SettingsError):
        _validate("conflictPolicy", "always")


def test_history_shows_which_locations_hold_each_snapshot(pair, tmp_path):
    from keepsake.store import LocalFolderStore
    from keepsake.store.multi import LocationState, MultiStore

    a, _b = pair
    first, second = LocalFolderStore(str(tmp_path / "one")), LocalFolderStore(str(tmp_path / "two"))
    multi = MultiStore({"onedrive": first, "direct": second}, lambda key: ["onedrive", "direct"], LocationState(None))
    a.app._store = lambda: multi

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"one")
        await a.app.sync_push(a.key)
        both = await a.app.snapshot_locations(a.key)
        for info in second.list("games/"):
            if "/snapshots/" in info.key:
                second.delete(info.key)  # gone from one location
        one = await a.app.snapshot_locations(a.key)
        return both, one

    both, one = asyncio.run(go())
    assert len(both) == 1 and sorted(next(iter(both.values()))) == ["direct", "onedrive"]
    assert next(iter(one.values())) == ["onedrive"]


def test_with_ask_me_a_conflict_is_announced_and_left(pair):
    a, b = pair

    async def go():
        await fork(a, b)()
        await a.app.sync_push(a.key)
        age(b, 3600)
        await b.app.sync_pull(b.key)
        await b.app._conflict_raised(await b.app._game(b.key))
        await asyncio.sleep(0.05)
        return await b.app.list_conflicts()

    assert len(asyncio.run(go())) == 1
    assert "Save conflict for Example Quest. Open Haversack to choose." in b.toasts()
    assert not b.app._newest_running
