"""v2 slice 13: module registry, lifecycle bus, per-game locks, state database, Steam operations queue."""

import asyncio

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake import discovery
from keepsake.bus import EventBus
from keepsake.locks import GameLocks
from keepsake.modules import Module, ModuleRegistry
from keepsake.statedb import StateDB, StateError
from keepsake.steamops import CLAIM_TIMEOUT, SteamOps, SteamOpsError
from keepsake.store import LocalFolderStore
from test_app_ux import Device


def run(coro):
    return asyncio.run(coro)


class Probe:
    def __init__(self, fail_start=False, fail_health=False):
        self.events, self.started, self.stopped = [], 0, 0
        self.fail_start, self.fail_health = fail_start, fail_health

    async def start(self):
        if self.fail_start:
            raise RuntimeError("boom")
        self.started += 1

    async def stop(self):
        self.stopped += 1

    async def health(self):
        if self.fail_health:
            raise RuntimeError("health boom")
        return [{"id": "x", "status": "ok"}]

    async def on_exit(self, payload):
        self.events.append(payload)

    def module(self, name="probe", available=True):
        return Module(
            name,
            name.title(),
            "test module",
            "nothing",
            available=available,
            start=self.start,
            stop=self.stop,
            health=self.health,
            listeners={"game_exited": self.on_exit},
        )


def test_flags_control_start_stop_and_listeners():
    bus, flags = EventBus(), {"probe": False}
    registry = ModuleRegistry(bus, lambda: flags)
    probe = Probe()
    registry.register(probe.module())

    async def go():
        await registry.start_all()
        off = (probe.started, bus.subscribers("game_exited"))
        flags["probe"] = True
        await registry.apply_flags()
        await bus.publish("game_exited", {"gameKey": "g"})
        on = (probe.started, bus.subscribers("game_exited"), list(probe.events))
        flags["probe"] = False
        await registry.apply_flags()
        await bus.publish("game_exited", {"gameKey": "g2"})
        return off, on, (probe.stopped, bus.subscribers("game_exited"), len(probe.events))

    off, on, after = run(go())
    assert off == (0, [])  # disabled: no start, no listeners
    assert on == (1, ["probe"], [{"event": "game_exited", "gameKey": "g"}])
    assert after == (1, [], 1)  # disabled again: stopped, listener gone


def test_a_failing_module_is_isolated_and_can_be_retried():
    bus = EventBus()
    registry = ModuleRegistry(bus, lambda: {"bad": True, "good": True})
    bad, good = Probe(fail_start=True), Probe()
    registry.register(bad.module("bad"))
    registry.register(good.module("good"))

    async def go():
        await registry.start_all()
        status = {m["name"]: m for m in await registry.status()}
        bad.fail_start = False
        await registry.reset("bad")
        return status, registry.running("bad")

    status, retried = run(go())
    assert status["bad"]["failed"].startswith("could not start") and not status["bad"]["running"]
    assert status["good"]["running"] and good.started == 1
    assert bus.subscribers("game_exited") == ["good", "bad"]
    assert retried is True


def test_a_failing_health_check_stops_only_that_module():
    registry = ModuleRegistry(EventBus(), lambda: {"sick": True, "fine": True})
    sick, fine = Probe(fail_health=True), Probe()
    registry.register(sick.module("sick"))
    registry.register(fine.module("fine"))

    async def go():
        await registry.start_all()
        return {m["name"]: m for m in await registry.status()}

    status = run(go())
    assert "health check failed" in status["sick"]["failed"] and sick.stopped == 1
    assert status["fine"]["running"] and status["fine"]["health"] == [{"id": "x", "status": "ok"}]


def test_unavailable_modules_never_start():
    registry = ModuleRegistry(EventBus(), lambda: {"later": True})
    probe = Probe()
    registry.register(probe.module("later", available=False))
    run(registry.start_all())
    assert probe.started == 0 and not registry.enabled("later")


def test_bus_isolates_a_failing_handler():
    bus = EventBus()
    seen = []

    async def bad(payload):
        raise ValueError("nope")

    async def good(payload):
        seen.append(payload["gameKey"])

    bus.subscribe("game_started", "bad", bad)
    bus.subscribe("game_started", "good", good)
    run(bus.publish("game_started", {"gameKey": "g"}))
    assert seen == ["g"] and bus.failures == [("bad", "game_started", "nope")]
    with pytest.raises(ValueError):
        bus.subscribe("not_an_event", "x", good)


def test_game_lock_makes_a_second_holder_wait():
    locks = GameLocks()
    order = []

    async def first():
        async with locks.hold("g", "saves"):
            order.append(("first", locks.holder("g")))
            await asyncio.sleep(0.05)
            order.append("first done")

    async def second():
        await asyncio.sleep(0.01)
        async with locks.hold("g", "replication"):
            order.append(("second", locks.holder("g")))

    async def go():
        await asyncio.gather(first(), second())

    run(go())
    assert order == [("first", "saves"), "first done", ("second", "replication")]
    assert locks.held() == {}


def test_state_db_migrations_are_namespaced_and_atomic(tmp_path):
    db = StateDB(str(tmp_path / "k.db"))
    assert db.migrate("alpha", ["CREATE TABLE alpha_a (x INTEGER)"]) == 1
    assert db.migrate("beta", ["CREATE TABLE beta_a (y TEXT)", "CREATE TABLE beta_b (z TEXT)"]) == 2
    with pytest.raises(StateError, match="migration 2 failed"):
        db.migrate("alpha", ["CREATE TABLE alpha_a (x INTEGER)", "CREATE TABLE alpha_b (x); NOT SQL"])
    assert db.version("alpha") == 1 and db.version("beta") == 2
    assert not db.execute("SELECT name FROM sqlite_master WHERE name = 'alpha_b'")  # rolled back
    with pytest.raises(StateError, match="newer"):
        db.migrate("beta", ["CREATE TABLE beta_a (y TEXT)"])  # a rollback to an older build
    db.close()


def test_steam_ops_queue(tmp_path):
    clock = {"now": 1000.0}
    ops = SteamOps(StateDB(str(tmp_path / "k.db")), clock=lambda: clock["now"])
    with pytest.raises(SteamOpsError):
        ops.enqueue("replication", "rm-rf", {"appid": 1})
    with pytest.raises(SteamOpsError):
        ops.enqueue("replication", "set-launch-options", {"value": "x"})
    first = ops.enqueue("core", "probe", {})
    second = ops.enqueue("replication", "set-launch-options", {"appid": 7, "value": "-x"})
    assert ops.pending_count() == 2
    claimed = ops.claim()
    assert claimed["id"] == first and claimed["kind"] == "probe"
    assert ops.claim()["id"] == second
    assert ops.claim() is None
    ops.finish(first, True, {"functions": {"Apps.AddShortcut": True}})
    with pytest.raises(SteamOpsError):
        ops.finish(first, True, {})  # already finished
    clock["now"] += CLAIM_TIMEOUT + 1
    assert ops.claim()["id"] == second  # the frontend reloaded mid-operation: offered again
    states = {o["id"]: o["state"] for o in ops.list()}
    assert states == {first: "done", second: "claimed"}


# Through the app


def test_a_failing_module_leaves_saves_working(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    flaky = Probe(fail_start=True)
    a.app.registry.register(flaky.module("flaky"))
    a.app.settings.set("moduleFlags", {})

    async def go():
        a.app.registry.flags = lambda: {"flaky": True}
        await a.app.start()
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"progress")
        pushed = await a.app.sync_push(a.key)
        status = await a.app.modules_status()
        await a.app.stop()
        return pushed, status

    pushed, status = run(go())
    by_name = {m["name"]: m for m in status["modules"]}
    assert pushed["status"] == "published"
    assert by_name["flaky"]["failed"] and by_name["saves"]["running"]
    assert status["stateDatabase"] is True
    assert {m["name"] for m in status["modules"] if not m["available"]} == {
        "replication",
        "desktop",
    }


def test_lifecycle_events_reach_subscribers_and_saves_can_be_switched_off(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    listener = Probe()
    a.app.bus.subscribe("game_exited", "test", listener.on_exit)

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"progress")
        game = await a.app._game(a.key)
        exited = await a.app._exit(game)
        handled_on = await a.app.on_game_event("exit", 4171510507)
        await a.app.set_module_enabled("saves", False)
        handled_off = await a.app.on_game_event("exit", 4171510507)
        return exited, handled_on, handled_off

    exited, handled_on, handled_off = run(go())
    assert exited["status"] == "published"
    assert listener.events == [{"event": "game_exited", "gameKey": "example-quest", "appid": 4171510507}]
    assert handled_on == {"handled": 1} and handled_off == {"handled": 0}


def test_steam_probe_queues_an_operation_and_events_the_frontend(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))

    async def go():
        await a.app.start()
        queued = await a.app.steam_probe()
        op = await a.app.steam_ops_claim()
        await a.app.steam_ops_finish(op["id"], True, {"functions": {}})
        listing = await a.app.steam_ops_list()
        await a.app.stop()
        return queued, op, listing

    queued, op, listing = run(go())
    assert op == {"id": queued["id"], "module": "core", "kind": "probe", "payload": {}}
    assert listing[0]["state"] == "done"
    assert ("keepsake_steam_ops", ()) in a.events


# Discovery amendment (v2 section 10, slice 3)


def test_discovery_captures_launch_options_compat_tool_artwork_and_icon(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    entry = shortcut_entry(-123456789, "Example Quest", "/g.exe", start_dir="/games/eq")
    entry.update({"LaunchOptions": "PROTON_LOG=1 %command%", "icon": '"/games/eq/icon.png"'})
    root = make_fake_steam(home, users={"7": [entry]}, prefixes=[(None, 4171510507)], most_recent="7")
    (root / "config" / "config.vdf").write_text(
        '"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" {'
        ' "4171510507" { "name" "GE-Proton10-1" "config" "" "priority" "250" } } } } } }'
    )
    grid = root / "userdata" / "7" / "config" / "grid"
    grid.mkdir(parents=True)
    for name in ("4171510507p.png", "4171510507_hero.jpg", "999.png"):
        (grid / name).write_bytes(b"x")
    game = next(g for g in discovery.discover(str(home))["games"] if g["kind"] == "shortcut")
    assert game["launch_options"] == "PROTON_LOG=1 %command%"
    assert game["compat_tool"] == "GE-Proton10-1"
    assert game["artwork"] == ["4171510507p.png", "4171510507_hero.jpg"]
    assert game["icon"] == "/games/eq/icon.png"
    assert game["exe"] == "/g.exe" and game["start_dir"] == "/games/eq"
