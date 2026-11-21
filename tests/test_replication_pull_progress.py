"""v0.31.0 (ADR-0072): two-way pairing, a space check before sending, no Accept, pulling a game,
progress on both devices, Stop and remove from either side, and toasts on both.

Two apps talk in process: a fake link calls the other app's request handlers directly, with the
calling device's identity, as the real link does after its handshake. Synthetic data only (P12).
"""

import asyncio
import os
import types

import pytest

from keepsake import app as app_module
from keepsake.replication import activity, news, offers, sendgame, transfer
from keepsake.replication.link import ServeError, Session
from test_replication_devices import make_app  # noqa: F401 - the app fixture
from test_replication_sendgame import SENDER, deliver, make_game, receiving_places, run_accept, setup_pair
from test_replication_transfer import PEER, FakeConnection

GIB = 2**30


# The bars


def job(state="running", received=0, total=100, rate=0.0, held=False, reason=None):
    return types.SimpleNamespace(state=state, received=received, total=total, rate=rate, held=held, reason=reason)


def record(state="transferring", jobs=None, done=(), update=False):
    return {
        "offer": {
            "title": "Test Game",
            "from": "Test handheld A",
            "shares": {"install": {"bytes": 100}, "prefix": {"bytes": 300}},
            "update": {"link": "x"} if update else None,
        },
        "peer": SENDER,
        "state": state,
        "jobs": jobs if jobs is not None else {"install": "j1", "prefix": "j2"},
        "doneScopes": list(done),
    }


def test_receiving_stages_and_numbers():
    r = activity.receiving("o1", record("offered", jobs={}), {}, "Go")
    assert r["stage"] == "checking-space" and r["total"] == 400 and r["percent"] == 0
    r = activity.receiving(
        "o1", record(), {"j1": job(received=50, rate=10.0), "j2": job(received=150, total=300)}, "Go"
    )
    assert (r["stage"], r["done"], r["total"], r["percent"]) == ("copying", 200, 400, 50)
    assert r["bytesPerSecond"] == 10 and r["secondsLeft"] == 20 and r["canStop"] and not r["canClear"]
    r = activity.receiving("o1", record(done=["install"]), {"j2": job("verifying", 300, 300)}, "Go")
    assert r["stage"] == "verifying" and r["done"] == 400 and r["secondsLeft"] is None
    r = activity.receiving("o1", record(), {"j1": job("paused", reason="Paused."), "j2": job("paused")}, "Go")
    assert r["stage"] == "paused" and r["reason"] == "Paused."
    r = activity.receiving("o1", record(), {"j1": job(held=True, reason="on battery"), "j2": job()}, "Go")
    assert r["stage"] == "waiting" and r["reason"] == "on battery"
    r = activity.receiving("o1", record(), {"j1": job("failed", reason="the disk is full"), "j2": job()}, "Go")
    assert r["stage"] == "failed" and r["reason"] == "the disk is full"
    assert activity.receiving("o1", record("registering", done=["install", "prefix"]), {}, "Go")["stage"] == "adding"
    done = activity.receiving("o1", record("done", done=["install", "prefix"]), {}, "Go")
    assert done["stage"] == "done" and done["percent"] == 100 and done["canClear"] and not done["canStop"]


def test_sending_bars_follow_the_receiving_device():
    base = {"title": "Test Game", "peer": PEER}
    waiting = activity.sending("o1", base, "Go 2")
    assert waiting["stage"] == "waiting" and waiting["reason"] == "Waiting for Go 2 to start"
    moving = {
        **base,
        "remoteState": "transferring",
        "remoteStage": "copying",
        "remoteDone": 30,
        "remoteTotal": 120,
        "remoteRate": 6,
        "remoteSecondsLeft": 15,
    }
    bar = activity.sending("o1", moving, "Go 2")
    assert (bar["stage"], bar["percent"], bar["bytesPerSecond"], bar["secondsLeft"]) == ("copying", 25, 6, 15)
    removed = activity.sending("o1", {**moving, "remoteState": "removed"}, "Go 2")
    assert removed["stage"] == "failed" and removed["reason"] == "Stopped and removed on Go 2"  # final beats progress
    old = activity.sending("o1", {**base, "remoteState": "done"}, "Go 2")  # an older device sends no numbers
    assert old["stage"] == "done" and old["percent"] == 100


def test_progress_from_the_other_device_is_checked():
    clean = activity.clean_progress(
        {"stage": "copying", "done": 5, "total": 10, "bytesPerSecond": 2, "secondsLeft": 3, "title": "x"}
    )
    assert clean == {
        "remoteStage": "copying",
        "remoteDone": 5,
        "remoteTotal": 10,
        "remoteRate": 2,
        "remoteSecondsLeft": 3,
    }
    bad = activity.clean_progress(
        {"stage": "deleting", "done": -1, "total": True, "bytesPerSecond": "9", "secondsLeft": 10**9}
    )
    assert bad == {"remoteSecondsLeft": None}
    assert set(activity.wire(activity.receiving("o", record(), {}, ""))) == set(activity.WIRE_FIELDS)


# Space


def test_space_check_counts_each_disk_once_with_its_margin(tmp_path, monkeypatch):
    _game, _where, _wire, incoming, *_ = setup_pair(tmp_path)
    usage = types.SimpleNamespace(free=10 * GIB)
    monkeypatch.setattr(offers.shutil, "disk_usage", lambda path: usage)
    fits = incoming.space_check({"install": 3 * GIB, "prefix": 1 * GIB}, None)
    assert fits["ok"] and fits["needed"] == 6 * GIB  # one disk: 4 GiB plus the 2 GiB margin
    short = incoming.space_check({"install": 9 * GIB, "prefix": 1 * GIB}, None)
    assert not short["ok"] and short["needed"] == 12 * GIB and short["free"] == 10 * GIB
    assert incoming.space_check({"install": 1, "tool": 50 * GIB}, "proton_9")["ok"]  # built-in tool: not copied
    assert not incoming.space_check({"install": 1, "tool": 50 * GIB}, "GE-Proton-Missing")["ok"]


def test_space_check_without_a_library_says_so(tmp_path):
    _game, _where, _wire, incoming, _manager, _ops, places, _ = setup_pair(tmp_path)
    places["library"] = ""
    result = incoming.space_check({"install": 1}, None)
    assert not result["ok"] and "choose where games are installed" in result["reason"]


def test_space_text_is_the_wording_asked_for():
    text = app_module.space_text("Legion Go 2", int(41.2 * GIB), 12 * GIB)
    assert text == "Legion Go 2 doesn't have enough space: needs 41.2 GiB, has 12.0 GiB free"


def test_space_check_request_is_validated(tmp_path):
    _game, _where, _wire, incoming, *_ = setup_pair(tmp_path)
    session = Session(SENDER, "127.0.0.1", None, None)
    reply = asyncio.run(incoming.handle_space(session, {"bytes": {"install": 10}, "compatTool": None}))
    assert reply["type"] == "space" and reply["ok"] is True
    for bad in (
        {"bytes": {"etc": 1}},
        {"bytes": {"install": -1}},
        {"bytes": {"install": True}},
        {"bytes": 5},
        {"bytes": {"install": 1}, "compatTool": "../x"},
    ):
        with pytest.raises(ServeError):
            asyncio.run(incoming.handle_space(session, bad))


def test_sizes_skip_logs_and_temp_files(tmp_path):
    game, where = make_game(tmp_path)
    plan = sendgame.plan(game, where["home"], where["library"], where["tools"])
    sizes = sendgame.sizes(plan)
    assert sizes["install"] == 3002 + 5000  # game.exe and data.pak; game.log is left out
    prefix = where["steam"] + "/steamapps/compatdata/4000123"
    kept = os.path.getsize(prefix + "/version") + os.path.getsize(
        prefix + "/pfx/drive_c/users/steamuser/Saved Games/Test/slot1.sav"
    )
    assert sizes["prefix"] == kept  # the Windows Temp folder is left out
    assert sizes["art"] == 400  # the capsule and the hero; icons are not sent (ADR-0059)


# Stop from the sending device


def test_offer_stop_comes_only_from_the_sending_device(tmp_path):
    _game, _where, wire, incoming, manager, _ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    with pytest.raises(ServeError):
        asyncio.run(incoming.handle_stop(Session("device-cccc-0003", "127.0.0.1", None, None), {"id": wire["id"]}))
    assert incoming.list()
    reply = asyncio.run(incoming.handle_stop(Session(SENDER, "127.0.0.1", None, None), {"id": wire["id"]}))
    assert reply == {"type": "offer-stopped", "id": wire["id"]} and incoming.list() == []
    assert os.listdir(places["library"]) == []  # the copy is gone


def test_progress_news_updates_the_senders_bar(tmp_path):
    _game, _where, wire, _incoming, _manager, _ops, _places, outgoing = setup_pair(tmp_path)
    first = outgoing.record_state(PEER, wire["id"], "transferring", None, {"stage": "copying", "done": 10, "total": 40})
    assert first["stateChanged"] is True
    moved = outgoing.record_state(PEER, wire["id"], "transferring", None, {"stage": "copying", "done": 20, "total": 40})
    assert moved["stateChanged"] is False
    assert (
        outgoing.record_state(PEER, wire["id"], "transferring", None, {"stage": "copying", "done": 20, "total": 40})
        is None
    )
    (bar,) = outgoing.activity({PEER: "Go 2"})
    assert bar["percent"] == 50 and bar["peer"] == "Go 2" and bar["direction"] == "sending"


# The news sender


class Recorder:
    def __init__(self, fail_first=0):
        self.sent, self.fail_first, self.connects = [], fail_first, 0

    def connect_for(self, peer_id):
        async def connect():
            self.connects += 1
            if self.fail_first:
                self.fail_first -= 1
                raise OSError("away")
            return self

        return connect

    async def request(self, message):
        self.sent.append(message)
        return {"type": "offer-state-received"}

    async def close(self):
        pass


def test_news_keeps_only_the_newest_progress_and_reuses_one_connection():
    link = Recorder()

    async def scenario():
        sender = news.PeerNews(link.connect_for, gap=0.01, idle=0.05)
        for done in range(5):
            sender.tell(PEER, "o1", {"type": "offer-state", "done": done})
        sender.tell(PEER, "o2", {"type": "offer-state", "done": 9})
        await asyncio.sleep(0.2)
        await sender.close()

    asyncio.run(scenario())
    assert [m["done"] for m in link.sent] == [4, 9] and link.connects == 1


def test_news_tries_a_final_state_again_and_drops_stale_progress():
    link = Recorder(fail_first=1)

    async def scenario():
        sender = news.PeerNews(link.connect_for, gap=0.01, idle=0.05, retry=(0.01,))
        sender.tell(PEER, "o1", {"type": "offer-state", "state": "done"}, final=True)
        sender.tell(PEER, "o2", {"type": "offer-state", "state": "transferring"})
        await asyncio.sleep(0.3)
        await sender.close()

    asyncio.run(scenario())
    states = [m["state"] for m in link.sent]
    assert "done" in states and "transferring" in states  # the rest of the round was kept for the next one


# Two apps


class Link:
    """A paired connection in process: requests go to the other app's handlers as this device."""

    def __init__(self, other, me):
        self.other, self.me = other, me

    async def request(self, message):
        try:
            return await self.other.links.handlers[message["type"]](Session(self.me, "127.0.0.1", None, None), message)
        except KeyError:
            return {"type": "error", "reason": f"unknown request {message['type']}"}
        except ServeError as exc:
            return {"type": "error", "reason": str(exc)}

    async def close(self):
        pass


class FakeNews:
    def __init__(self):
        self.told, self.sent = [], []

    def tell(self, peer_id, about, message, final=False):
        self.told.append((peer_id, about, message, final))

    async def close(self):
        pass


async def started(make, name):
    app = make(name)
    await app.start()
    await app.set_module_enabled("replication", True)
    app.emitted = []

    async def emit(event, *args):
        app.emitted.append((event, args))

    app.emit = emit
    app._news = FakeNews()
    return app


def toasts(app):
    return [a[0] for e, a in app.emitted if e == "keepsake_toast"]


def test_a_new_game_starts_copying_by_itself_and_both_sides_see_it(make_app, tmp_path):  # noqa: F811
    _game, _where, wire, _incoming, _manager, _ops, _places, outgoing = setup_pair(tmp_path / "pair")

    async def scenario():
        app = await started(make_app, "b")
        places = receiving_places(tmp_path / "b-places")
        app.incoming.places = lambda: places

        async def connect():
            return FakeConnection(outgoing.shares)

        app.transfers.connect_for = lambda _peer: connect
        try:
            await app.incoming.handle_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire})
            for _ in range(200):  # no Accept: it copies and reaches Steam's step by itself
                await asyncio.sleep(0.02)
                if app.incoming.list()[0]["state"] == "registering":
                    break
            bars = await app.replication_activity()
            return app.incoming.list()[0], bars, app._news.told, toasts(app)
        finally:
            await app.stop()

    listed, bars, told, said = asyncio.run(scenario())
    assert listed["state"] == "registering"
    assert bars[0]["stage"] == "adding" and bars[0]["direction"] == "receiving" and bars[0]["percent"] == 100
    states = [m["state"] for _p, _a, m, _f in told]
    assert states[0] == "transferring" and "registering" in states
    assert all(set(activity.WIRE_FIELDS) <= set(m) for _p, _a, m, _f in told)  # every message carries the bar
    assert "Test Game is coming from Test handheld A." in said


def test_a_game_that_cannot_start_fails_with_the_reason_on_both_devices(make_app, tmp_path):  # noqa: F811
    _game, _where, wire, *_ = setup_pair(tmp_path / "pair")

    async def scenario():
        app = await started(make_app, "b")
        places = receiving_places(tmp_path / "b-places")
        places["library"] = ""
        app.incoming.places = lambda: places
        try:
            await app.incoming.handle_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire})
            for _ in range(100):
                await asyncio.sleep(0.02)
                if app.incoming.list()[0]["state"] == "failed":
                    break
            return app.incoming.list()[0], app._news.told
        finally:
            await app.stop()

    listed, told = asyncio.run(scenario())
    assert listed["state"] == "failed" and "choose where games are installed" in listed["reason"]
    assert told[-1][2]["state"] == "failed" and told[-1][3] is True  # final: tried again if the sender is away


def sending_setup(make_app, tmp_path, monkeypatch, reply):  # noqa: F811
    game, where = make_game(tmp_path / "send")

    async def make():
        app = await started(make_app, "a")
        app.links.store.add(PEER, "Legion Go 2", b"k" * 32, "192.168.1.30:47110")

        async def fake_game(key):
            return game

        monkeypatch.setattr(app, "_game", fake_game)
        monkeypatch.setattr(
            app,
            "_replication_places",
            lambda: {"home": where["home"], "library": where["library"], "tools": where["tools"]},
        )
        asked = []

        class Peer:
            async def request(self, message):
                asked.append(message)
                return reply

            async def close(self):
                pass

        async def connect():
            return Peer()

        monkeypatch.setattr(app, "_replication_connect_for", lambda _peer: connect)
        return app, asked

    return make


def test_sending_stops_before_hashing_when_the_other_device_lacks_space(make_app, tmp_path, monkeypatch):  # noqa: F811
    make = sending_setup(
        make_app, tmp_path, monkeypatch, {"type": "space", "ok": False, "needed": 41 * GIB, "free": 12 * GIB}
    )

    async def scenario():
        app, asked = await make()
        prepared = []
        monkeypatch.setattr(app.outgoing, "prepare", lambda *a: prepared.append(a))
        try:
            with pytest.raises(ValueError) as refused:
                await app.replication_send("shortcut:123:4000123", PEER)
            bars = await app.replication_activity()
            return str(refused.value), asked, prepared, bars
        finally:
            await app.stop()

    refused, asked, prepared, bars = asyncio.run(scenario())
    assert refused == "Legion Go 2 doesn't have enough space: needs 41.0 GiB, has 12.0 GiB free"
    assert asked[0]["type"] == "space-check" and asked[0]["bytes"]["install"] == 8002 and prepared == []
    assert bars[0]["stage"] == "failed" and bars[0]["reason"] == refused and bars[0]["direction"] == "sending"


def test_an_older_device_without_a_space_check_still_gets_the_game(make_app, tmp_path, monkeypatch):  # noqa: F811
    make = sending_setup(make_app, tmp_path, monkeypatch, {"type": "error", "reason": "unknown request space-check"})

    async def scenario():
        app, _asked = await make()
        sent = []

        async def fake_send(key, plan, peer_id, extra):
            sent.append((key, peer_id))

        monkeypatch.setattr(app, "_send_game", fake_send)
        try:
            result = await app.replication_send("shortcut:123:4000123", PEER)
            await asyncio.sleep(0)
            return result, sent
        finally:
            await app.stop()

    result, sent = asyncio.run(scenario())
    assert result["stage"] == "preparing" and sent == [("shortcut:123:4000123", PEER)]


def test_get_this_game_from_another_device(make_app, tmp_path, monkeypatch):  # noqa: F811
    game, where = make_game(tmp_path / "send")

    async def scenario():
        sender = await started(make_app, "a")
        receiver = await started(make_app, "b")
        a_id, b_id = str(sender.settings.get("deviceId")), str(receiver.settings.get("deviceId"))
        sender.links.store.add(b_id, "Legion Go 2", b"k" * 32, "192.168.1.30:47110")
        receiver.links.store.add(a_id, "Legion Go", b"k" * 32, "192.168.1.20:47110")
        sender.settings.set("deviceName", "Legion Go")

        async def discover(refresh=False):
            return {"games": [game]}

        async def fake_game(key):
            return game

        monkeypatch.setattr(sender, "discover_games", discover)
        monkeypatch.setattr(sender, "_game", fake_game)
        monkeypatch.setattr(
            sender,
            "_replication_places",
            lambda: {"home": where["home"], "library": where["library"], "tools": where["tools"]},
        )
        places = receiving_places(tmp_path / "b-places")
        receiver.incoming.places = lambda: places
        offered = []

        async def fake_send(key, plan, peer_id, extra):
            offered.append((key, peer_id, extra.get("pull")))

        monkeypatch.setattr(sender, "_send_game", fake_send)

        def to(other, me):
            async def connect():
                return Link(other, me)

            return lambda _peer: connect

        monkeypatch.setattr(receiver, "_replication_connect_for", to(sender, b_id))
        try:
            games = await receiver.replication_peer_games(a_id)
            bars = await receiver.replication_get_game(a_id, games[0]["id"], games[0]["title"])
            await asyncio.sleep(0.05)
            replay = None
            try:
                await receiver.replication_get_game(a_id, games[0]["id"], games[0]["title"])  # a token is used once
            except ValueError as exc:
                replay = str(exc)
            return games, bars, offered, toasts(sender), replay
        finally:
            await sender.stop()
            await receiver.stop()

    games, bars, offered, said, replay = asyncio.run(scenario())
    assert games == [{"id": games[0]["id"], "title": "Test Game"}]
    assert "4000123" not in str(games) and "shortcut" not in str(games)  # no app ID or key over the link (P10)
    assert bars[0]["stage"] == "preparing" and bars[0]["direction"] == "receiving" and bars[0]["peer"] == "Legion Go"
    assert offered == [("shortcut:123:4000123", next(iter([offered[0][1]])), games[0]["id"])]
    assert "Test Game is being copied to Legion Go 2." in said
    assert replay and "out of date" in replay


def test_get_this_game_checks_space_here_first(make_app, tmp_path, monkeypatch):  # noqa: F811
    async def scenario():
        receiver = await started(make_app, "b")
        receiver.settings.set("deviceName", "Legion Go 2")
        receiver.links.store.add(PEER, "Legion Go", b"k" * 32, "192.168.1.20:47110")
        receiver.incoming.places = lambda: receiving_places(tmp_path / "b-places")
        monkeypatch.setattr(offers.shutil, "disk_usage", lambda path: types.SimpleNamespace(free=1 * GIB))
        asked = []

        class Peer:
            async def request(self, message):
                asked.append(message["type"])
                return {"type": "pull-size", "title": "Test Game", "bytes": {"install": 5 * GIB}, "compatTool": None}

            async def close(self):
                pass

        async def connect():
            return Peer()

        monkeypatch.setattr(receiver, "_replication_connect_for", lambda _peer: connect)
        try:
            with pytest.raises(ValueError) as refused:
                await receiver.replication_get_game(PEER, "0123456789abcdef", "Test Game")
            return str(refused.value), asked, await receiver.replication_activity()
        finally:
            await receiver.stop()

    refused, asked, bars = asyncio.run(scenario())
    assert refused == "Legion Go 2 doesn't have enough space: needs 7.0 GiB, has 1.0 GiB free"
    assert asked == ["pull-check"]  # never asked it to send
    assert bars[0]["stage"] == "failed" and bars[0]["reason"] == refused


def test_a_pull_needs_a_token_listed_to_that_device(make_app):  # noqa: F811
    async def scenario():
        app = await started(make_app, "a")
        app._pull_tokens["0123456789abcdef"] = {"key": "k", "peer": PEER, "expires": 0}
        try:
            for peer, token in ((PEER, "0123456789abcdef"), ("device-cccc-0003", "0123456789abcdef"), (PEER, "nope")):
                with pytest.raises(ServeError):
                    await app._serve_pull(Session(peer, "127.0.0.1", None, None), {"game": token})
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_stop_from_the_sending_device_reaches_the_receiver_and_withdraws(make_app, tmp_path, monkeypatch):  # noqa: F811
    _game, _where, wire, *_rest, outgoing = setup_pair(tmp_path / "pair")

    async def scenario():
        app = await started(make_app, "a")
        app.outgoing = outgoing
        asked = []

        class Peer:
            async def request(self, message):
                asked.append(message)
                return {"type": "offer-stopped", "id": message["id"]}

            async def close(self):
                pass

        async def connect():
            return Peer()

        monkeypatch.setattr(app, "_replication_connect_for", lambda _peer: connect)
        try:
            bars = await app.replication_stop_game(wire["id"])
            return asked, bars, outgoing.list()
        finally:
            await app.stop()

    asked, bars, left = asyncio.run(scenario())
    assert asked == [{"type": "offer-stop", "id": wire["id"]}] and left == [] and bars == []


def test_removed_on_the_receiver_withdraws_on_the_sender_with_a_toast(make_app, tmp_path):  # noqa: F811
    _game, _where, wire, *_rest, outgoing = setup_pair(tmp_path / "pair")

    async def scenario():
        app = await started(make_app, "a")
        app.outgoing = outgoing
        app.links.store.add(PEER, "Legion Go 2", b"k" * 32, "192.168.1.30:47110")
        try:
            await app._replication_offer_news(
                Session(PEER, "127.0.0.1", None, None), {"type": "offer-state", "id": wire["id"], "state": "removed"}
            )
            return outgoing.list(), toasts(app)
        finally:
            await app.stop()

    left, said = asyncio.run(scenario())
    assert left == [] and said == ["Legion Go 2 stopped and removed Test Game."]


def test_toasts_on_the_sender_as_the_copy_goes(make_app, tmp_path):  # noqa: F811
    _game, _where, wire, *_rest, outgoing = setup_pair(tmp_path / "pair")

    async def scenario():
        app = await started(make_app, "a")
        app.outgoing = outgoing
        app.links.store.add(PEER, "Legion Go 2", b"k" * 32, "192.168.1.30:47110")
        session = Session(PEER, "127.0.0.1", None, None)
        try:
            for state, done in (("transferring", 1), ("transferring", 2), ("done", 3)):
                await app._replication_offer_news(
                    session, {"type": "offer-state", "id": wire["id"], "state": state, "stage": "copying", "done": done}
                )
            return toasts(app)
        finally:
            await app.stop()

    said = asyncio.run(scenario())
    assert said == ["Test Game is copying to Legion Go 2.", "Test Game arrived on Legion Go 2."]  # progress: no toast


def test_pairing_makes_this_device_reachable_too(make_app, monkeypatch):  # noqa: F811
    async def scenario():
        app = await started(make_app, "a")
        switched = []

        async def set_listener(on):
            switched.append(on)

        monkeypatch.setattr(app.links, "set_listener", set_listener)
        monkeypatch.setattr(app_module.replication_link, "available", lambda: True)
        from keepsake.replication.link import Pairing

        app.links.initiated["p1"] = Pairing(
            "p1", "initiator", "192.168.1.30:47110", state="paired", peer_name="Legion Go 2"
        )
        try:
            app._replication_two_way(app.links)
            app._replication_two_way(app.links)  # once per pairing
            await asyncio.sleep(0.05)
            return switched, app.settings.get("replicationListener"), toasts(app)
        finally:
            await app.stop()

    switched, setting, said = asyncio.run(scenario())
    assert switched.count(True) == 1 and switched[0] is True and setting is True  # stop() switches it off again
    assert said == ["Paired with Legion Go 2. Games can now go both ways between you."]


def test_the_export_carries_the_bars_without_titles(make_app, tmp_path):  # noqa: F811
    async def scenario():
        app = await started(make_app, "a")
        app._pulling["0123456789abcdef"] = {
            "state": "failed",
            "stage": "failed",
            "title": "Secret Title",
            "peer": PEER,
            "reason": "/home/u/Games is full",
        }
        try:
            return await app._replication_redacted()
        finally:
            await app.stop()

    data = asyncio.run(scenario())
    assert data["activity"] == [
        {"direction": "receiving", "stage": "failed", "percent": 0, "reason": "a folder is full"}
    ]
    assert "Secret Title" not in str(data)


def test_transfer_start_off_the_loop_leaves_nothing(tmp_path):
    from keepsake.replication import jobs, sleepguard

    guard = sleepguard.SleepGuard(bus_path=str(tmp_path / "no-bus"), platform="linux")
    manager = jobs.Transfers(str(tmp_path / "jobs.json"), lambda _p: None, guard=guard)
    work = transfer.Job(id="j", peer_id=PEER, share="a" * 32, root="b" * 64, target=str(tmp_path / "t"), peers=[PEER])
    with pytest.raises(RuntimeError):
        manager.start(work)
    assert manager.jobs == {} and manager._registry() == {} and not os.path.exists(work.staging)
