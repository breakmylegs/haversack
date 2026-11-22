"""R21 stage 2 (ADR-0076): performance profiles through steamos-manager only, never fighting another tool.

A fake steamos-manager answers Properties GetAll, Get and Set on a fake bus, as Valve's user
daemon does. Synthetic app IDs only (P12).
"""

import asyncio

import pytest

from keepsake import devicechecks
from keepsake.desktop import dbus
from keepsake.device import performance as perf
from keepsake.device import steamos

APPID = 4000123
OTHER = 4000456


class FakeManager:
    """steamos-manager's properties, per interface. ``drift`` makes a Set read back differently."""

    def __init__(self, interfaces=None):
        self.props = interfaces or {
            steamos.TDP: {"TdpLimit": ("u", 15), "TdpLimitMin": ("u", 5), "TdpLimitMax": ("u", 30)},
            steamos.PROFILE: {
                "PerformanceProfile": ("s", "balanced"),
                "AvailablePerformanceProfiles": ("as", ["low-power", "balanced", "performance", "custom"]),
                "SuggestedDefaultPerformanceProfile": ("s", "custom"),
            },
            steamos.BOOST: {"CpuBoostState": ("u", 1)},
        }
        self.sets = []
        self.drift = {}

    def connect(self):
        manager = self

        class Conn:
            def call(self, destination, path, interface, member, signature="", body=None):
                assert destination == steamos.BUS and path == steamos.PATH and interface == steamos.PROPS
                if member == "GetAll":
                    if body[0] not in manager.props:
                        raise dbus.DBusError("org.freedesktop.DBus.Error.UnknownInterface: no")
                    return [dict(manager.props[body[0]])]
                if member == "Get":
                    return [manager.props[body[0]][body[1]]]
                if member == "Set":
                    iface, prop, (sig, value) = body
                    manager.sets.append((prop, value))
                    manager.props[iface][prop] = (sig, manager.drift.get(prop, value))
                    return []
                raise AssertionError(member)

            def close(self):
                pass

        return Conn()

    def value(self, iface, prop):
        return self.props[iface][prop][1]


def performance(tmp_path, manager=None, tools=None, limits=None):
    manager = manager or FakeManager()
    store = perf.ProfileStore(str(tmp_path / "device-profiles.json"))
    p = perf.Performance(
        store,
        steamos.SteamOSManager(manager.connect),
        lambda: list(tools or []),
        lambda: limits or {"min": 5, "max": 30},
    )
    return p, manager, store


# steamos-manager


def test_read_what_the_device_offers():
    manager = FakeManager()
    read = steamos.SteamOSManager(manager.connect).read()
    assert read["tdp"] == {"value": 15, "min": 5, "max": 30}
    assert read["profile"]["current"] == "balanced" and "custom" in read["profile"]["available"]
    assert read["boost"] is True and read["chargeLimit"] is None  # not offered: unavailable, not an error


def test_no_steamos_manager_is_a_plain_problem():
    absent = FakeManager()
    absent.props = {}
    with pytest.raises(steamos.ManagerError, match="not running"):
        steamos.SteamOSManager(absent.connect).read()

    def no_bus():
        raise OSError("no socket")

    with pytest.raises(steamos.ManagerError, match="session bus could not be reached"):
        steamos.SteamOSManager(no_bus).read()


def test_every_set_is_read_back():
    manager = FakeManager()
    manager.drift = {"TdpLimit": 12}
    with pytest.raises(steamos.ManagerError, match="reads back as 12 W"):
        steamos.SteamOSManager(manager.connect).set_tdp(20)


# Profiles


@pytest.mark.parametrize(
    "bad",
    [{"mode": "../x"}, {"tdp": 0}, {"tdp": 500}, {"tdp": True}, {"tdp": "15"}, {"boost": "yes"}, "x"],
)
def test_bad_profiles_are_refused(bad):
    with pytest.raises(perf.ProfileError):
        perf.clean_profile(bad)


def test_profiles_are_kept_per_game(tmp_path):
    store = perf.ProfileStore(str(tmp_path / "p.json"))
    store.set(APPID, {"mode": "performance", "tdp": 18, "extra": 1})
    assert store.get(APPID) == {"mode": "performance", "tdp": 18}
    store.set(APPID, None)
    assert store.get(APPID) is None


def test_a_tdp_switches_to_custom_first_and_is_clamped(tmp_path):
    p, manager, _ = performance(tmp_path, limits={"min": 8, "max": 25})
    applied = p.apply({"tdp": 40})
    assert applied == {"mode": "custom", "tdp": 25}  # the device profile's ceiling beats steamos-manager's 30
    assert manager.sets[:2] == [("PerformanceProfile", "custom"), ("TdpLimit", 25)]  # the mode first
    assert p.before == {"mode": "balanced", "tdp": 15}
    assert p.apply({"tdp": 1})["tdp"] == 8


def test_a_game_gets_its_profile_and_the_old_values_come_back(tmp_path):
    p, manager, store = performance(tmp_path)
    store.set(APPID, {"mode": "performance", "boost": False})
    assert p.game_started(APPID) == {"mode": "performance", "boost": False}
    assert manager.value(steamos.PROFILE, "PerformanceProfile") == "performance"
    restored = p.game_exited()
    assert restored == ["boost", "mode"]  # the mode last
    assert manager.value(steamos.PROFILE, "PerformanceProfile") == "balanced"
    assert manager.value(steamos.BOOST, "CpuBoostState") == 1


def test_a_game_without_a_profile_changes_nothing(tmp_path):
    p, manager, _ = performance(tmp_path)
    assert p.game_started(OTHER) is None and manager.sets == []
    assert p.game_exited() == []


def test_a_change_by_someone_else_is_never_undone(tmp_path):
    p, manager, store = performance(tmp_path)
    store.set(APPID, {"tdp": 20})
    p.game_started(APPID)
    manager.props[steamos.TDP]["TdpLimit"] = ("u", 12)  # Steam's own slider, say
    assert "another app" in p.watch()
    p.game_exited()
    assert manager.value(steamos.TDP, "TdpLimit") == 12  # left as the other app set it
    assert manager.value(steamos.PROFILE, "PerformanceProfile") == "balanced"  # the mode Keepsake set is put back


def test_another_tool_means_read_only(tmp_path):
    p, manager, store = performance(tmp_path, tools=["SimpleDeckyTDP"])
    store.set(APPID, {"mode": "performance"})
    assert p.game_started(APPID) is None and manager.sets == []
    assert "SimpleDeckyTDP manages performance" in p.stopped
    with pytest.raises(perf.ProfileError, match="SimpleDeckyTDP"):
        p.apply({"mode": "quiet"})


def test_resume_applies_the_profile_again(tmp_path):
    p, manager, store = performance(tmp_path)
    store.set(APPID, {"mode": "performance"})
    p.game_started(APPID)
    manager.props[steamos.PROFILE]["PerformanceProfile"] = ("s", "custom")  # the firmware reset on wake
    p.resumed()
    assert manager.value(steamos.PROFILE, "PerformanceProfile") == "performance"


def test_a_mode_the_device_lacks_is_refused(tmp_path):
    p, _manager, _ = performance(tmp_path)
    with pytest.raises(perf.ProfileError, match="does not offer that performance mode"):
        p.apply({"mode": "max-power"})


def test_other_tools_are_found(tmp_path):
    home = tmp_path / "home"
    (home / "homebrew" / "plugins" / "SimpleDeckyTDP").mkdir(parents=True)
    (home / "homebrew" / "plugins" / "LegionGoRemapper").mkdir(parents=True)  # sets no TDP
    proc = tmp_path / "proc"
    (proc / "812").mkdir(parents=True)
    (proc / "812" / "comm").write_text("hhd\n")
    (proc / "813").mkdir(parents=True)
    (proc / "813" / "comm").write_text("bash\n")
    assert perf.other_tools(str(home), str(proc)) == ["SimpleDeckyTDP", "Handheld Daemon"]
    assert perf.other_tools(str(tmp_path / "empty"), str(tmp_path / "noproc")) == []


# The Device check


@pytest.mark.parametrize(
    ("found", "status"),
    [
        (
            {
                "reachable": True,
                "current": {"tdp": {"value": 15, "min": 5, "max": 30}, "profile": None},
                "writeBack": "tdp",
                "tools": [],
            },
            "pass",
        ),
        (
            {
                "reachable": True,
                "current": {"tdp": {"value": 15, "min": 5, "max": 30}},
                "writeBack": "tdp",
                "tools": ["Handheld Daemon"],
            },
            "warn",
        ),
        ({"reachable": True, "current": {}, "writeBack": None, "tools": []}, "warn"),
        (
            {
                "reachable": True,
                "current": {"tdp": {"value": 15, "min": 5, "max": 30}},
                "writeError": "denied",
                "tools": [],
            },
            "fail",
        ),
        ({"reachable": False, "error": "no bus"}, "fail"),
    ],
)
def test_device_check(found, status):
    async def probe():
        return found

    ctx = devicechecks.Context("", "", "", "", {}, "", probes={"performance-control": probe})
    outcome = asyncio.run(devicechecks.run("performance-control", ctx))
    assert outcome["status"] == status and outcome["title"] == "Performance control"


# The app


def test_the_app_applies_and_keeps_a_profile_for_the_running_game(tmp_path, monkeypatch):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    manager = FakeManager()
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.34.0", home=str(tmp_path))
    monkeypatch.setattr(app, "_steamos", lambda: steamos.SteamOSManager(manager.connect))
    monkeypatch.setattr(app, "_device_limits", lambda: {"min": 5, "max": 30})

    async def go():
        await app.start()
        try:
            await app.bus.publish("game_started", {"appid": APPID})
            await asyncio.sleep(0)
            status = await app.device_apply({"mode": "performance"}, APPID)
            await app.bus.publish("game_exited", {"appid": APPID})
            after = await app.device_performance()
            return status, after
        finally:
            await app.stop()

    status, after = asyncio.run(go())
    assert status["game"] == APPID and status["profile"] == {"mode": "performance"}
    assert after["game"] is None and manager.value(steamos.PROFILE, "PerformanceProfile") == "balanced"
    stored = perf.ProfileStore(str(tmp_path / "settings" / "device-profiles.json"))
    assert stored.get(APPID) == {"mode": "performance"}


def test_exit_never_undoes_a_change_it_has_not_noticed_yet(tmp_path):
    p, manager, store = performance(tmp_path)
    store.set(APPID, {"mode": "performance"})
    p.game_started(APPID)
    manager.props[steamos.PROFILE]["PerformanceProfile"] = ("s", "low-power")  # changed before any watch ran
    assert p.game_exited() == []
    assert manager.value(steamos.PROFILE, "PerformanceProfile") == "low-power"


def test_several_changes_in_one_game_still_put_back_the_first_value(tmp_path):
    p, manager, _ = performance(tmp_path)
    p.game_started(OTHER)
    p.apply({"mode": "performance"})
    p.apply({"mode": "low-power"})  # changed again from the quick access menu
    p.game_exited()
    assert manager.value(steamos.PROFILE, "PerformanceProfile") == "balanced"


def test_the_app_applies_the_profile_again_after_sleep(tmp_path, monkeypatch):
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    manager = FakeManager()
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), version="0.34.0", home=str(tmp_path))
    monkeypatch.setattr(app, "_steamos", lambda: steamos.SteamOSManager(manager.connect))
    monkeypatch.setattr(app, "_device_limits", lambda: {"min": 5, "max": 30})

    async def go():
        await app.start()
        try:
            await app.device_apply({"mode": "performance"}, APPID)
            app.performance.game = APPID
            manager.props[steamos.PROFILE]["PerformanceProfile"] = ("s", "custom")  # the firmware reset on wake
            await app.on_resume()
        finally:
            await app.stop()

    asyncio.run(go())
    assert ("PerformanceProfile", "performance") in manager.sets[1:]
