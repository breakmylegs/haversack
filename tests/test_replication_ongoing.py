"""Keeping games in step (slice 20a, ADR-0060), and Replication never writing save files (P14).

Synthetic folders and app IDs only.
"""

import asyncio
import os

import pytest

from keepsake.replication import offers, ongoing, transfer
from keepsake.replication.link import Session
from test_replication_devices import make_app  # noqa: F401 - the app fixture
from test_replication_sendgame import NEW_APPID, SENDER, deliver, run_accept, setup_pair
from test_replication_transfer import PEER

SAVE = "pfx/drive_c/users/steamuser/Saved Games/Test/slot1.sav"


def received_game(tmp_path):
    """A game sent and fully received, as slice 19 leaves it."""
    game, where, wire, incoming, manager, ops, places, outgoing = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    incoming.op_finished(1, True, {"appid": NEW_APPID})
    for op_id in range(2, len(ops.queued) + 1):
        incoming.op_finished(op_id, True, {})
    target = {
        "install": os.path.join(places["library"], "Test Game"),
        "prefix": os.path.join(places["compatdata"], str(NEW_APPID)),
    }
    source = {"install": os.path.join(where["library"], "Test Game"), "prefix": game["prefix"]}
    return source, target, incoming, manager, outgoing


def base_of(scopes, keep):
    return {s: m["root"] for s, m in ongoing.scan(scopes, keep).items()}


def test_an_update_replaces_game_files_and_never_writes_saves(tmp_path):
    source, target, incoming, manager, outgoing = received_game(tmp_path)
    keep = {"prefix": [SAVE]}
    base = base_of(source, keep)
    # The receiving device played on: its save differs from the sender's.
    with open(os.path.join(target["prefix"], *SAVE.split("/")), "wb") as handle:
        handle.write(b"progress made on the receiving device")
    # The sending device patched the game, removed a file, and has its own newer save.
    with open(os.path.join(source["install"], "data.pak"), "wb") as handle:
        handle.write(b"patched")
    os.remove(os.path.join(source["install"], "bin", "game.exe"))
    with open(os.path.join(source["prefix"], *SAVE.split("/")), "wb") as handle:
        handle.write(b"progress made on the sending device")

    wire, roots = outgoing.prepare_update("aaaaaaaaaaaaaaaa", "Test Game", source, keep, base, PEER, {})
    assert set(wire["shares"]) == {"install"}  # the prefix only differs by its save: nothing to send
    assert wire["update"] == {"link": "aaaaaaaaaaaaaaaa", "base": {"install": base["install"]}}
    reply = asyncio.run(incoming.handle_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire}))
    assert reply["type"] == "offer-received"

    async def apply():
        incoming.accept_update(wire["id"], target, keep)
        while manager.tasks:
            await asyncio.gather(*list(manager.tasks.values()))
            await asyncio.sleep(0)

    asyncio.run(apply())
    assert open(os.path.join(target["install"], "data.pak"), "rb").read() == b"patched"
    assert not os.path.exists(os.path.join(target["install"], "bin", "game.exe"))
    with open(os.path.join(target["prefix"], *SAVE.split("/")), "rb") as handle:
        assert handle.read() == b"progress made on the receiving device"  # P14: Saves' file, untouched
    record = next(o for o in incoming.list() if o["id"] == wire["id"])
    assert record["state"] == "done" and record["update"] and record["link"] == "aaaaaaaaaaaaaaaa"
    assert roots["install"] == wire["shares"]["install"]["root"]


def test_an_update_into_the_prefix_keeps_the_receivers_save_file(tmp_path):
    """Even if a save path reached the copy, the receiving device's own file wins (carry_over)."""
    source, target, incoming, manager, outgoing = received_game(tmp_path)
    receiver_save = os.path.join(target["prefix"], *SAVE.split("/"))
    with open(receiver_save, "wb") as handle:
        handle.write(b"mine")
    os.makedirs(os.path.join(source["prefix"], "pfx", "drive_c", "Mods"))
    with open(os.path.join(source["prefix"], "pfx", "drive_c", "Mods", "mod.dll"), "wb") as handle:
        handle.write(b"new mod")
    base = base_of(source, {})
    with open(os.path.join(source["prefix"], "pfx", "drive_c", "Mods", "mod.dll"), "wb") as handle:
        handle.write(b"newer mod")
    with open(os.path.join(source["prefix"], *SAVE.split("/")), "wb") as handle:
        handle.write(b"theirs")
    wire, _ = outgoing.prepare_update("bbbbbbbbbbbbbbbb", "Test Game", {"prefix": source["prefix"]}, {}, base, PEER, {})
    asyncio.run(incoming.handle_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire}))

    async def apply():
        incoming.accept_update(wire["id"], {"prefix": target["prefix"]}, {"prefix": [SAVE]})
        while manager.tasks:
            await asyncio.gather(*list(manager.tasks.values()))
            await asyncio.sleep(0)

    asyncio.run(apply())
    assert open(os.path.join(target["prefix"], "pfx", "drive_c", "Mods", "mod.dll"), "rb").read() == b"newer mod"
    assert open(receiver_save, "rb").read() == b"mine"


def test_stopping_an_update_leaves_the_game_as_it_was(tmp_path):
    source, target, incoming, _manager, outgoing = received_game(tmp_path)
    before = sorted(os.listdir(target["install"]))
    base = base_of(source, {})
    with open(os.path.join(source["install"], "data.pak"), "wb") as handle:
        handle.write(b"patched")
    wire, _ = outgoing.prepare_update("cccccccccccccccc", "Test Game", source, {}, base, PEER, {})
    asyncio.run(incoming.handle_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire}))

    async def scenario():
        incoming.accept_update(wire["id"], target, {})
        await incoming.stop(wire["id"])

    asyncio.run(scenario())
    assert sorted(os.listdir(target["install"])) == before and os.path.isdir(target["prefix"])
    assert open(os.path.join(target["install"], "data.pak"), "rb").read() != b"patched"


def test_an_update_with_no_change_is_not_offered(tmp_path):
    source, _target, _incoming, _manager, outgoing = received_game(tmp_path)
    base = base_of(source, {})
    with pytest.raises(offers.OfferError, match="nothing has changed"):
        outgoing.prepare_update("dddddddddddddddd", "Test Game", source, {}, base, PEER, {})


def test_an_update_offer_must_be_a_valid_update(tmp_path):
    from test_replication_sendgame import good_offer

    offer = good_offer()
    offer["shares"].pop("art")
    offer["art"] = []
    offer["update"] = {"link": "eeeeeeeeeeeeeeee", "base": {"install": "a" * 64}}
    del offer["exe"], offer["startDir"]
    assert offers.validate(offer)["update"] == {"link": "eeeeeeeeeeeeeeee", "base": {"install": "a" * 64}}
    for bad in (
        {"link": "nope", "base": {}},
        {"link": "eeeeeeeeeeeeeeee", "base": {"tool": "a" * 64}},
        {"link": "eeeeeeeeeeeeeeee", "base": {"install": "zz"}},
        "not a dict",
    ):
        with pytest.raises(offers.OfferError, match="update"):
            offers.validate(offer | {"update": bad})
    with_tool = offer | {"shares": {**offer["shares"], "tool": {"share": "1" * 32, "root": "2" * 64, "bytes": 1}}}
    with pytest.raises(offers.OfferError, match="update"):
        offers.validate(with_tool)  # an update carries game files only


def test_accepting_an_update_needs_the_games_folders(tmp_path):
    source, target, incoming, _manager, outgoing = received_game(tmp_path)
    base = base_of(source, {})
    with open(os.path.join(source["install"], "data.pak"), "wb") as handle:
        handle.write(b"patched")
    wire, _ = outgoing.prepare_update("ffffffffffffffff", "Test Game", source, {}, base, PEER, {})
    asyncio.run(incoming.handle_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire}))
    with pytest.raises(offers.OfferError, match="not found"):
        incoming.accept_update(wire["id"], {"install": str(tmp_path / "gone")}, {})
    with pytest.raises(offers.OfferError, match="not waiting"):
        incoming.accept_update("0000000000000000", target, {})


def test_carry_over_copies_kept_files_and_refuses_escapes(tmp_path):
    target = tmp_path / "Game"
    (target / "saves").mkdir(parents=True)
    (target / "saves" / "a.sav").write_bytes(b"keep me")
    job = transfer.Job("j", PEER, "s", "r", str(target), keep=["saves/a.sav", "../outside", "missing.sav"])
    tree = os.path.join(job.staging, "tree")
    os.makedirs(os.path.join(tree, "saves"))
    with open(os.path.join(tree, "saves", "a.sav"), "wb") as handle:
        handle.write(b"from the other device")
    assert transfer.carry_over(job) == 1
    assert open(os.path.join(tree, "saves", "a.sav"), "rb").read() == b"keep me"
    assert not os.path.exists(tmp_path / "outside")
    again = transfer.Job.from_journal(job.journal())
    assert again.keep == job.keep


def test_links_take_their_base_from_the_first_scan(tmp_path):
    links = ongoing.GameLinks(str(tmp_path / "games.json"))
    links.add("1111111111111111", "Test Game", PEER, 4000001, {"install": "/x", "tool": "/t"}, {})
    assert links.get("1111111111111111")["scopes"] == {"install": "/x"}  # tools and art are not kept in step
    assert links.changed("1111111111111111", {"install": "a" * 64}) is False  # the first scan is the base
    assert links.changed("1111111111111111", {"install": "a" * 64}) is False
    assert links.changed("1111111111111111", {"install": "b" * 64}) is True
    assert links.for_appid(4000001)[0] == "1111111111111111" and links.for_appid(5) is None
    with pytest.raises(ongoing.LinkError, match="policy"):
        links.update("1111111111111111", policy="sometimes")
    links.update("1111111111111111", policy="auto")
    assert links.list()[0]["policy"] == "auto"
    with pytest.raises(ongoing.LinkError):
        links.add("bad", "x", PEER, None, {}, {})
    links.remove("1111111111111111")
    assert links.list() == []


def test_the_states():
    assert ongoing.state_after(False, False) == "in-sync"
    assert ongoing.state_after(True, False) == "changed-here"
    assert ongoing.state_after(False, True) == "update-available"
    assert ongoing.state_after(True, True) == "both-changed"


def test_scans_leave_out_saves_whatever_their_case(tmp_path):
    root = tmp_path / "prefix"
    (root / "Saves").mkdir(parents=True)
    (root / "Saves" / "Slot.SAV").write_bytes(b"x")
    (root / "game.dat").write_bytes(b"y")
    keep = {"prefix": ongoing.keep_relative(str(root), [str(root / "Saves" / "Slot.SAV")])}
    assert keep == {"prefix": ["Saves/Slot.SAV"]}
    paths = [
        e["path"] for e in ongoing.scan({"prefix": str(root)}, {"prefix": ["saves/slot.sav"]})["prefix"]["entries"]
    ]
    assert "Saves/Slot.SAV" not in paths and "game.dat" in paths
    assert ongoing.keep_relative(str(root), [str(tmp_path / "elsewhere.sav"), str(root)]) == []


def test_both_sides_changed_asks_the_user(make_app, monkeypatch):  # noqa: F811
    async def scenario():
        app = make_app("a")
        await app.start()
        await app.set_module_enabled("replication", True)
        try:
            app.game_links.add(
                "1234567812345678", "Test Game", SENDER, NEW_APPID, {"install": "/x"}, {"install": "a" * 64}
            )
            offer = {"id": "abcdefabcdefabcd", "update": True, "link": "1234567812345678"}

            monkeypatch.setattr(app.incoming, "list", lambda: [offer])

            async def linked(_link):
                return {"key": "shortcut:1:4000999", "appid": NEW_APPID}

            monkeypatch.setattr(app, "_linked_game", linked)
            monkeypatch.setattr(app, "_replication_keep", lambda game, scopes: {})
            monkeypatch.setattr(
                "keepsake.app.scan_game", lambda scopes, keep: {"install": {"root": "b" * 64}}
            )  # this device changed too
            accepted = []
            monkeypatch.setattr(app.incoming, "begin_update", lambda *a: accepted.append(a) or [])
            with pytest.raises(ValueError, match="changed on this device too"):
                await app.replication_apply_update("abcdefabcdefabcd")
            assert app.game_links.get("1234567812345678")["state"] == "both-changed" and accepted == []
            await app.replication_apply_update("abcdefabcdefabcd", take_theirs=True)
            assert accepted and app.game_links.get("1234567812345678")["state"] == "updating"
            app._replication_update_done(
                {"offer": {"update": {"link": "1234567812345678"}, "shares": {"install": {"root": "c" * 64}}}}
            )
            link = app.game_links.get("1234567812345678")
            assert link["state"] == "in-sync" and link["base"] == {"install": "c" * 64}
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_an_auto_update_is_applied_by_itself_and_a_manual_one_waits(make_app, monkeypatch):  # noqa: F811
    async def scenario():
        app = make_app("a")
        await app.start()
        await app.set_module_enabled("replication", True)
        try:
            app.game_links.add("1234567812345678", "Test Game", SENDER, NEW_APPID, {"install": "/x"}, {})
            applied = []

            async def apply(offer_id, take_theirs=False):
                applied.append(offer_id)

            monkeypatch.setattr(app, "replication_apply_update", apply)
            app._replication_offer_arrived({"id": "o1", "update": {"link": "1234567812345678"}})
            await asyncio.sleep(0)
            assert applied == [] and app.game_links.get("1234567812345678")["state"] == "update-available"
            app.game_links.update("1234567812345678", policy="auto")
            app._replication_offer_arrived({"id": "o2", "update": {"link": "1234567812345678"}})
            await asyncio.sleep(0)
            assert applied == ["o2"]
            app._replication_offer_arrived({"id": "o3"})  # a new game, not an update: nothing to do here
        finally:
            await app.stop()

    asyncio.run(scenario())


@pytest.mark.posix
@pytest.mark.skipif(os.name != "posix", reason="needs symbolic links")
def test_carry_over_never_follows_a_link_in_the_new_copy_out_of_it(tmp_path):
    target = tmp_path / "Game"
    (target / "saves").mkdir(parents=True)
    (target / "saves" / "a.sav").write_bytes(b"keep me")
    outside = tmp_path / "outside"
    outside.mkdir()
    job = transfer.Job("j", PEER, "s", "r", str(target), keep=["saves/a.sav"])
    tree = os.path.join(job.staging, "tree")
    os.makedirs(tree)
    os.symlink(str(outside), os.path.join(tree, "saves"))  # a hostile copy points its folder elsewhere
    assert transfer.carry_over(job) == 0
    assert os.listdir(outside) == []
