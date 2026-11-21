"""v0.30.2: an accepted game always copies or fails, and both devices see which, with a plain reason.

The stall: accepting ran in a worker thread, where a transfer (an asyncio task) cannot start, so
the offer sat "transferring" with nothing running, and the sending device was never told.
Synthetic folders, names and app IDs only (P12).
"""

import asyncio
import json

import pytest

from keepsake.replication import offers
from keepsake.replication.link import ServeError, Session
from test_replication_devices import make_app  # noqa: F401 - the app fixture
from test_replication_sendgame import SENDER, deliver, receiving_places, run_accept, setup_pair
from test_replication_transfer import PEER, FakeConnection


def told_list(incoming):
    told = []
    incoming.on_state = lambda offer_id, record: told.append((offer_id, record["state"], record.get("reason")))
    return told


def test_accepting_from_a_worker_thread_fails_plainly_instead_of_stalling(tmp_path):
    """The v0.30.1 code path: start the copies off the event loop. Now a failure, never a stall."""
    _game, _where, wire, incoming, manager, _ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    told = told_list(incoming)

    async def scenario():
        jobs = await asyncio.to_thread(incoming.begin, wire["id"], True)
        await asyncio.to_thread(incoming.start_jobs, wire["id"], jobs)  # wrong thread, as before

    asyncio.run(scenario())
    (listed,) = incoming.list()
    assert listed["state"] == "failed" and listed["reason"].startswith("the copy could not start")
    assert told[0][1] == "transferring" and told[-1][1] == "failed"
    assert manager.tasks == {} and manager.jobs == {} and manager._registry() == {}  # nothing left half-started


def test_begin_in_a_thread_then_start_on_the_loop_copies(tmp_path):
    _game, _where, wire, incoming, manager, _ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    told = told_list(incoming)

    async def scenario():
        jobs = await asyncio.to_thread(incoming.begin, wire["id"], True)
        incoming.start_jobs(wire["id"], jobs)
        assert manager.tasks  # running
        while manager.tasks:
            await asyncio.gather(*list(manager.tasks.values()))
            await asyncio.sleep(0)

    asyncio.run(scenario())
    assert incoming.list()[0]["state"] == "registering"
    assert [state for _id, state, _r in told] == ["transferring", "registering"]


def test_a_copy_that_fails_fails_the_offer_with_its_reason(tmp_path):
    _game, _where, wire, incoming, manager, _ops, _places, outgoing = setup_pair(tmp_path)
    deliver(incoming, wire)
    told = told_list(incoming)
    outgoing.withdraw(wire["id"])  # the sending device no longer serves it
    run_accept(incoming, manager, wire["id"])
    (listed,) = incoming.list()
    assert listed["state"] == "failed" and listed["reason"]  # was left "transferring" before
    assert told[-1][1] == "failed" and told[-1][2] == listed["reason"]


def test_decline_and_stop_and_remove_tell_the_sender(tmp_path):
    _game, _where, wire, incoming, manager, _ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    told = told_list(incoming)
    incoming.decline(wire["id"])
    assert told == [(wire["id"], "declined", None)]
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    asyncio.run(incoming.stop(wire["id"]))
    assert told[-1] == (wire["id"], "removed", None)


@pytest.mark.parametrize(
    ("reason", "sent"),
    [
        ("/home/deck/Games/Factorio already exists; rename it", "a folder already exists; rename it"),
        ("not enough space in /run/media/SDCARD/Games: 9 GiB needed", "not enough space in a folder 9 GiB needed"),
        ("cannot write C:\\Games\\x.bin\nretry", "cannot write a folder retry"),
        ("~/Games/x is busy", "a folder is busy"),
        ("chunk 1/2 failed its hash", "chunk 1/2 failed its hash"),
        ("x" * 1000, "x" * offers.MAX_REASON),
        (None, None),
    ],
)
def test_reasons_sent_to_the_other_device_carry_no_paths(reason, sent):
    assert offers.wire_reason(reason) == sent


def test_the_sender_records_news_only_about_its_own_offers_to_that_device(tmp_path):
    _game, _where, wire, _incoming, _manager, _ops, _places, outgoing = setup_pair(tmp_path)
    assert outgoing.list()[0]["remoteState"] == "offered"
    changed = outgoing.record_state(PEER, wire["id"], "failed", "/home/deck/Games/X already exists")
    assert changed == {
        "id": wire["id"],
        "title": "Test Game",
        "state": "failed",
        "reason": "a folder already exists",
        "stateChanged": True,
    }
    assert outgoing.record_state(PEER, wire["id"], "failed", "/home/deck/Games/X already exists") is None  # no change
    (listed,) = outgoing.list()
    assert listed["remoteState"] == "failed" and listed["remoteReason"] == "a folder already exists"
    with pytest.raises(ServeError):
        outgoing.record_state("device-cccc-0003", wire["id"], "done", None)  # another paired device
    with pytest.raises(ServeError):
        outgoing.record_state(PEER, "0123456789abcdef", "done", None)  # not an offer it made
    with pytest.raises(ServeError):
        outgoing.record_state(PEER, wire["id"], "offered-and-copied", None)  # not a state
    with pytest.raises(ServeError):
        outgoing.record_state(PEER, "../x", "done", None)


def test_the_app_accepts_on_the_loop_and_tells_the_sender(make_app, tmp_path, monkeypatch):  # noqa: F811
    _game, _where, wire, _incoming, _manager, _ops, _places, outgoing = setup_pair(tmp_path / "pair")

    async def scenario():
        app = make_app("b")
        await app.start()
        await app.set_module_enabled("replication", True)
        sent = []

        class News:  # v0.31.0: the shared news sender
            sent: list = []  # noqa: RUF012 - what the export reads

            def tell(self, peer_id, about, message, final=False):
                sent.append((peer_id, message))

            async def close(self):
                pass

        async def connect():
            return FakeConnection(outgoing.shares)

        app._news = News()
        places = receiving_places(tmp_path / "b-places")
        app.incoming.places = lambda: places
        app.transfers.connect_for = lambda _peer: connect
        try:
            await app.incoming.handle_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire})
            for _ in range(100):  # v0.31.0: no Accept, it starts by itself (ADR-0072)
                await asyncio.sleep(0.01)
                if app.transfers.tasks:
                    break
            assert app.transfers.tasks  # the copy is running: the stall was "transferring" with no task
            while app.transfers.tasks:
                await asyncio.gather(*list(app.transfers.tasks.values()))
                await asyncio.sleep(0)
            for _ in range(5):
                await asyncio.sleep(0)
            assert (await app.replication_offers())["incoming"][0]["state"] == "registering"
            states = [m["state"] for _p, m in sent]
            assert states[0] == "transferring" and states[-1] == "registering"
            assert all(p == SENDER and m["type"] == "offer-state" and m["id"] == wire["id"] for p, m in sent)
            # The Device checks' export carries the states, redacted.
            app._device_results["x"] = {"id": "x", "status": "pass", "found": ""}
            monkeypatch.setattr("keepsake.app.devicechecks.CHECKS", [type("C", (), {"id": "x"})()])
            exported = await app.device_checks_export()
            saved = (tmp_path / "b" / "settings" / exported["file"]).read_text(encoding="utf-8")
            data = json.loads(saved)["replication"]
            assert data["incoming"][0]["state"] == "registering" and data["incoming"][0]["jobs"]
            assert {j["state"] for j in data["incoming"][0]["jobs"]} == {"done"}
            assert "Test Game" not in saved and "Test handheld" not in saved and str(tmp_path) not in saved
            assert str(tmp_path).replace("\\", "\\\\") not in saved and SENDER not in saved
            # A failure goes to the sending device without this device's paths.
            app._replication_offer_state(
                wire["id"], {"state": "failed", "reason": "/home/u/Games/X already exists", "peer": SENDER, "offer": {}}
            )
            for _ in range(5):
                await asyncio.sleep(0)
            assert sent[-1][1]["state"] == "failed" and sent[-1][1]["reason"] == "a folder already exists"
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_the_app_shows_news_from_the_receiver_and_refuses_strangers(make_app, tmp_path):  # noqa: F811
    _game, _where, wire, _incoming, _manager, _ops, _places, _ = setup_pair(tmp_path / "pair")

    async def scenario():
        app = make_app("a")
        await app.start()
        await app.set_module_enabled("replication", True)
        toasts = []

        async def emit(event, *args):
            if event == "keepsake_toast":
                toasts.append(args[0])

        app.emit = emit
        try:
            app.outgoing._save({wire["id"]: {"peer": PEER, "title": "Test Game", "shares": {}, "created": 1.0}})
            handler = app.links.handlers["offer-state"]
            message = {"type": "offer-state", "id": wire["id"], "state": "failed", "reason": "not enough space"}
            reply = await handler(Session(PEER, "127.0.0.1", None, None), message)
            assert reply == {"type": "offer-state-received", "id": wire["id"]}
            outgoing = (await app.replication_offers())["outgoing"][0]
            assert outgoing["remoteState"] == "failed" and outgoing["remoteReason"] == "not enough space"
            assert toasts == ["Test Game did not arrive on the other device: not enough space"]
            with pytest.raises(ServeError):
                await handler(Session("device-cccc-0003", "127.0.0.1", None, None), message)
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_any_failure_while_offering_shows_on_the_sender(make_app, monkeypatch):  # noqa: F811
    async def scenario():
        app = make_app("a")
        await app.start()
        await app.set_module_enabled("replication", True)
        toasts = []

        async def emit(event, *args):
            if event == "keepsake_toast":
                toasts.append(args[0])

        def broken(*args):
            raise KeyError("manifestFile")  # not one of the errors the old code caught

        app.emit = emit
        monkeypatch.setattr(app.outgoing, "prepare", broken)
        try:
            app._sending["k"] = {"state": "preparing", "title": "Test Game", "peer": PEER}
            plan = type("Plan", (), {"title": "Test Game", "roots": {}})()
            await app._send_game("k", plan, PEER, {})
            assert app._sending["k"]["state"] == "failed" and "manifestFile" in app._sending["k"]["reason"]
            assert toasts and toasts[0].startswith("Test Game was not offered")
        finally:
            await app.stop()

    asyncio.run(scenario())
