"""Sending a game (slice 19a, ADR-0059): the plan, the offer, and accepting it through to Steam.

Synthetic folders, names and app IDs only (P12).
"""

import asyncio
import os

import pytest

from keepsake.replication import jobs, offers, sendgame, sleepguard, transfer
from keepsake.replication.link import Session
from keepsake.replication.source import Shares
from test_replication_devices import make_app  # noqa: F401 - the app fixture
from test_replication_transfer import PEER, FakeConnection, tree_of

APPID = 4000123
NEW_APPID = 4000999
SENDER = "device-aaaa-0001"


def make_game(tmp_path, inside_prefix=False):
    """A synthetic non-Steam game with a prefix, a tool and artwork, on the sending device."""
    home = tmp_path / "home"
    steam = home / ".local" / "share" / "Steam"
    prefix = steam / "steamapps" / "compatdata" / str(APPID)
    (prefix / "pfx" / "drive_c" / "users" / "steamuser" / "Saved Games" / "Test").mkdir(parents=True)
    (prefix / "pfx" / "drive_c" / "users" / "steamuser" / "Saved Games" / "Test" / "slot1.sav").write_bytes(b"save")
    (prefix / "pfx" / "drive_c" / "windows" / "temp").mkdir(parents=True)
    (prefix / "pfx" / "drive_c" / "windows" / "temp" / "junk.tmp").write_bytes(b"junk")
    (prefix / "version").write_text("GE-Proton9-99\n")
    library = home / "Games"
    if inside_prefix:
        game_dir = prefix / "pfx" / "drive_c" / "Games" / "Test Game"
    else:
        game_dir = library / "Test Game"
    (game_dir / "bin").mkdir(parents=True)
    (game_dir / "bin" / "game.exe").write_bytes(b"MZ" + os.urandom(3000))
    (game_dir / "data.pak").write_bytes(os.urandom(5000))
    (game_dir / "game.log").write_text("noise")
    tools = steam / "compatibilitytools.d"
    (tools / "GE-Proton9-99" / "files").mkdir(parents=True)
    (tools / "GE-Proton9-99" / "proton").write_text("#!/bin/sh\n")
    grid = steam / "userdata" / "123" / "config" / "grid"
    grid.mkdir(parents=True)
    for name in (f"{APPID}p.png", f"{APPID}_hero.jpg", f"{APPID}_icon.png"):
        (grid / name).write_bytes(os.urandom(200))
    exe = game_dir / "bin" / "game.exe"
    game = {
        "kind": "shortcut",
        "key": f"shortcut:123:{APPID}",
        "appid": APPID,
        "name": "Test Game",
        "exe": f'"{exe}"',
        "start_dir": f'"{game_dir / "bin"}"',
        "prefix": str(prefix),
        "launch_options": (
            f'STEAM_COMPAT_MOUNTS=/run/media/deck/disc WINEDLLOVERRIDES="x=n,b" {prefix}/tool.sh %command%'
        ),
        "compat_tool": "GE-Proton9-99",
        "artwork": [f"{APPID}p.png", f"{APPID}_hero.jpg", f"{APPID}_icon.png"],
        "steam_root": str(steam),
        "user_id": "123",
    }
    return game, {"home": str(home), "library": str(library), "tools": str(tools), "steam": str(steam)}


def receiving_places(tmp_path):
    home = tmp_path / "other"
    steam = home / ".local" / "share" / "Steam"
    (steam / "steamapps" / "compatdata").mkdir(parents=True)
    (home / "Games").mkdir(parents=True)
    return {
        "library": str(home / "Games"),
        "compatdata": str(steam / "steamapps" / "compatdata"),
        "tools": str(steam / "compatibilitytools.d"),
        "art": str(tmp_path / "other-runtime" / "replication-art"),
        "home": str(home),
    }


# The plan


def test_a_library_game_plans_its_folder_prefix_tool_and_art(tmp_path):
    game, where = make_game(tmp_path)
    plan = sendgame.plan(game, where["home"], where["library"], where["tools"])
    assert set(plan.roots) == {"install", "prefix", "tool"}
    assert plan.roots["install"] == os.path.realpath(os.path.join(where["library"], "Test Game"))
    assert plan.exe == {"scope": "install", "path": "bin/game.exe"}
    assert plan.start_dir == {"scope": "install", "path": "bin"}
    assert plan.launch_options == 'WINEDLLOVERRIDES="x=n,b" {prefix}/tool.sh %command%'
    assert plan.dropped_options == ["STEAM_COMPAT_MOUNTS=/run/media/deck/disc"]
    assert [(a["assetType"], a["file"]) for a in plan.art] == [(0, "capsule.png"), (1, "hero.jpg")]  # no icon
    assert plan.compat_tool == "GE-Proton9-99"


def test_a_game_inside_its_prefix_is_one_share(tmp_path):
    game, where = make_game(tmp_path, inside_prefix=True)
    plan = sendgame.plan(game, where["home"], where["library"], where["tools"])
    assert "install" not in plan.roots
    assert plan.exe == {"scope": "prefix", "path": "pfx/drive_c/Games/Test Game/bin/game.exe"}


def test_what_cannot_be_sent(tmp_path):
    game, where = make_game(tmp_path)
    with pytest.raises(sendgame.SendError, match="non-Steam"):
        sendgame.plan(game | {"kind": "steam"}, where["home"], where["library"], where["tools"])
    with pytest.raises(sendgame.SendError, match="not found"):
        sendgame.plan(game | {"exe": str(tmp_path / "missing.exe")}, where["home"], where["library"], where["tools"])
    loose = tmp_path / "home" / "loose.exe"
    loose.write_bytes(b"MZ")
    with pytest.raises(sendgame.SendError, match="home folder"):
        sendgame.plan(game | {"exe": str(loose), "start_dir": ""}, where["home"], where["library"], where["tools"])
    with pytest.raises(sendgame.SendError, match="folder name"):
        sendgame.plan(game | {"name": "bad/name"}, where["home"], where["library"], where["tools"])


def test_exclusions():
    prefix, install = sendgame.exclude_for("prefix"), sendgame.exclude_for("install")
    for rel in (
        "pfx/drive_c/windows/temp",
        "pfx/drive_c/users/steamuser/AppData/Local/Temp",
        "pfx/drive_c/users/x/Temp",
    ):
        assert prefix(rel) and not install(rel)
    for rel in ("a/game.log", "b/state.dxvk-cache", "vkd3d-proton.cache.write", "crash.dmp", "x/CrashDumps"):
        assert prefix(rel) and install(rel)
    for rel in ("bin/game.exe", "pfx/drive_c/users/steamuser/Saved Games/Test/slot1.sav", "logs.txt"):
        assert not prefix(rel) and not install(rel)


def test_launch_options_never_carry_this_devices_paths():
    roots = {"{install}": "/home/deck/Games/X", "{prefix}": "/home/deck/.steam/c/1", "{home}": "/home/deck"}
    text, dropped = sendgame.canonical_options(
        "PROTON_LOG=1 /home/deck/Games/X/fix.sh /media/disc/setup %command% -config /home/deck/x.ini", roots
    )
    assert text == "PROTON_LOG=1 {install}/fix.sh %command% -config {home}/x.ini"
    assert dropped == ["/media/disc/setup"]
    back = {"{install}": "/var/home/user/Games/X", "{prefix}": "/p", "{home}": "/var/home/user"}
    assert (
        sendgame.local_options(text, back)
        == "PROTON_LOG=1 /var/home/user/Games/X/fix.sh %command% -config /var/home/user/x.ini"
    )


# The offer on the wire


def good_offer():
    return {
        "id": "0123456789abcdef",
        "title": "Test Game",
        "from": {"name": "Test handheld A"},
        "shares": {
            "install": {"share": "a" * 32, "root": "b" * 64, "bytes": 10},
            "prefix": {"share": "c" * 32, "root": "d" * 64, "bytes": 20},
            "art": {"share": "e" * 32, "root": "f" * 64, "bytes": 1},
        },
        "exe": {"scope": "install", "path": "bin/game.exe"},
        "startDir": {"scope": "install", "path": "bin"},
        "launchOptions": "{prefix}/x %command%",
        "compatTool": "GE-Proton9-99",
        "art": [{"assetType": 0, "file": "capsule.png"}],
        "gameKey": "test-game",
        "savesEnabled": True,
        "extra": "dropped",
    }


def test_a_good_offer_is_kept_with_known_fields_only():
    offer = offers.validate(good_offer())
    assert "extra" not in offer and offer["from"] == "Test handheld A" and offer["savesEnabled"] is True


@pytest.mark.parametrize(
    "change",
    [
        lambda o: o.update(id="nope"),
        lambda o: o.update(title="a/b"),
        lambda o: o["shares"].update(other={"share": "a" * 32, "root": "b" * 64, "bytes": 1}),
        lambda o: o["shares"]["install"].update(root="xyz"),
        lambda o: o["shares"]["install"].update(bytes=-1),
        lambda o: o.update(shares={"art": o["shares"]["art"]}),
        lambda o: o.update(exe={"scope": "install", "path": "../../etc/passwd"}),
        lambda o: o.update(exe={"scope": "tool", "path": "x"}),
        lambda o: o.update(startDir={"scope": "install", "path": "/abs"}),
        lambda o: o.update(launchOptions="a\nb"),
        lambda o: o.update(launchOptions="{user}/x"),
        lambda o: o.update(compatTool="../../x"),
        lambda o: o.update(art=[{"assetType": 9, "file": "capsule.png"}]),
        lambda o: o.update(art=[{"assetType": 0, "file": "../x.png"}]),
        lambda o: o.update(gameKey="bad\nkey"),
    ],
)
def test_bad_offers_are_refused(change):
    offer = good_offer()
    change(offer)
    with pytest.raises((offers.OfferError, Exception)):
        offers.validate(offer)


# From offer to a game in Steam


class Ops:
    def __init__(self):
        self.queued = []

    def enqueue(self, kind, payload):
        self.queued.append((kind, payload))
        return len(self.queued)


def setup_pair(tmp_path, **game_args):
    game, where = make_game(tmp_path, **game_args)
    shares = Shares()
    outgoing = offers.Outgoing(str(tmp_path / "out.json"), str(tmp_path / "out"), shares)
    plan = sendgame.plan(game, where["home"], where["library"], where["tools"])
    wire = outgoing.prepare(
        plan, PEER, {"from": {"name": "Test handheld A"}, "gameKey": "test-game", "savesEnabled": True}
    )

    async def connect():
        return FakeConnection(shares)

    guard = sleepguard.SleepGuard(bus_path=str(tmp_path / "no-bus"), platform="linux")
    manager = jobs.Transfers(str(tmp_path / "jobs.json"), lambda _p: connect, guard=guard, retries=0)
    ops = Ops()
    places = receiving_places(tmp_path)
    incoming = offers.Incoming(str(tmp_path / "in.json"), manager, ops.enqueue, lambda: places)
    manager.on_finished = incoming.job_finished
    return game, where, wire, incoming, manager, ops, places, outgoing


def deliver(incoming, wire):
    reply = asyncio.run(incoming.handle_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire}))
    assert reply == {"type": "offer-received", "id": wire["id"]}


def test_an_offer_arrives_and_waits_for_the_user(tmp_path):
    _game, _where, wire, incoming, _manager, ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    (listed,) = incoming.list()
    assert listed["state"] == "offered" and listed["title"] == "Test Game" and listed["from"] == "Test handheld A"
    assert listed["peer"] == SENDER and listed["toolOffered"] and listed["bytes"] > 0
    assert os.listdir(places["library"]) == [] and ops.queued == []  # nothing written but the offer
    incoming.decline(wire["id"])
    assert incoming.list() == []


def run_accept(incoming, manager, offer_id, copy_tool=True):
    async def scenario():
        incoming.accept(offer_id, copy_tool)
        while manager.tasks:
            await asyncio.gather(*list(manager.tasks.values()))
            await asyncio.sleep(0)

    asyncio.run(scenario())


def test_accepting_copies_registers_and_finishes(tmp_path):
    _game, where, wire, incoming, manager, ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    install = os.path.join(places["library"], "Test Game")
    source_install = os.path.join(where["library"], "Test Game")
    expected = {k: v for k, v in tree_of(source_install).items() if not k.endswith(".log")}
    assert tree_of(install) == expected
    assert os.path.isfile(os.path.join(places["tools"], "GE-Proton9-99", "proton"))
    (kind, payload) = ops.queued[0]
    assert kind == "add-shortcut" and payload["name"] == "Test Game" and payload["compatTool"] == "GE-Proton9-99"
    assert payload["exe"] == os.path.join(install, "bin", "game.exe")
    assert incoming.list()[0]["state"] == "registering"
    # Steam added the shortcut: the prefix moves into place and every field is set.
    incoming.op_finished(1, True, {"appid": NEW_APPID})
    final_prefix = os.path.join(places["compatdata"], str(NEW_APPID))
    assert os.path.isfile(
        os.path.join(final_prefix, "pfx", "drive_c", "users", "steamuser", "Saved Games", "Test", "slot1.sav")
    )
    assert not os.path.exists(os.path.join(final_prefix, "pfx", "drive_c", "windows", "temp", "junk.tmp"))
    queued = {k: p for k, p in ops.queued[1:]}
    assert queued["set-shortcut-exe"] == {"appid": NEW_APPID, "value": os.path.join(install, "bin", "game.exe")}
    assert queued["set-launch-options"]["value"] == f'WINEDLLOVERRIDES="x=n,b" {final_prefix}/tool.sh %command%'
    assert queued["set-compat-tool"]["value"] == "GE-Proton9-99"
    art_ops = [(op_id, p) for op_id, (k, p) in enumerate(ops.queued, start=1) if k == "set-artwork"]
    assert [p["assetType"] for _, p in art_ops] == [0, 1]
    claimed = {
        "id": art_ops[0][0],
        "module": "replication",
        "kind": "set-artwork",
        "state": "claimed",
        "payload": art_ops[0][1],
    }
    assert os.path.getsize(incoming.staged_file(claimed)) == 200
    for op_id in range(2, len(ops.queued) + 1):
        result = incoming.op_finished(op_id, True, {})
    assert result["state"] == "done" and result["appid"] == NEW_APPID and result["reason"] is None
    sent_to_steam = " ".join(str(v) for _, p in ops.queued for v in p.values())
    assert not any(h in sent_to_steam for h in sendgame.PLACEHOLDERS)  # no placeholder reached Steam


def test_a_tool_steam_did_not_keep_says_to_restart_steam(tmp_path):
    _game, _where, wire, incoming, manager, ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    incoming.op_finished(1, True, {"appid": NEW_APPID})
    for op_id in range(2, len(ops.queued) + 1):
        result = incoming.op_finished(op_id, ops.queued[op_id - 1][0] != "set-compat-tool", {})
    assert result["state"] == "done" and "Restart Steam" in result["reason"]


def test_a_shortcut_steam_refused_fails_the_offer(tmp_path):
    _game, _where, wire, incoming, manager, _ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    result = incoming.op_finished(1, False, {"error": "Steam did not create the shortcut"})
    assert result["state"] == "failed" and "did not create" in result["reason"]


def test_stop_and_remove_undoes_everything_the_offer_made(tmp_path):
    _game, _where, wire, incoming, manager, ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    incoming.op_finished(1, True, {"appid": NEW_APPID})
    asyncio.run(incoming.stop(wire["id"]))
    assert os.listdir(places["library"]) == []
    assert os.listdir(places["compatdata"]) == []
    assert os.listdir(places["tools"]) == []
    assert not os.path.exists(os.path.join(places["art"], wire["id"]))
    assert ops.queued[-1] == ("remove-shortcut", {"appid": NEW_APPID})
    assert incoming.list() == []


def test_stop_and_remove_mid_copy(tmp_path):
    _game, _where, wire, incoming, _manager, ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)

    async def scenario():
        incoming.accept(wire["id"], True)
        await incoming.stop(wire["id"])

    asyncio.run(scenario())
    assert os.listdir(places["library"]) == [] and os.listdir(places["compatdata"]) == []
    assert not [k for k, _ in ops.queued if k == "remove-shortcut"]  # no shortcut was made, so none is removed


def test_preflight_refusals(tmp_path, monkeypatch):
    _game, _where, wire, incoming, _manager, _ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    with pytest.raises(offers.OfferError, match="choose to copy it"):
        incoming.preflight(wire["id"], copy_tool=False)
    os.makedirs(os.path.join(places["library"], "Test Game"))
    with pytest.raises(offers.OfferError, match="already exists"):
        incoming.preflight(wire["id"], copy_tool=True)
    os.rmdir(os.path.join(places["library"], "Test Game"))
    monkeypatch.setattr(offers.shutil, "disk_usage", lambda _p: type("U", (), {"free": 10})())
    with pytest.raises(offers.OfferError, match="not enough space"):
        incoming.preflight(wire["id"], copy_tool=True)


def test_a_tool_this_device_has_is_not_copied(tmp_path):
    _game, _where, wire, incoming, _manager, _ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    os.makedirs(os.path.join(places["tools"], "GE-Proton9-99"))
    checked = incoming.preflight(wire["id"], copy_tool=True)
    assert "tool" not in checked["targets"] and checked["toolMissing"] is False


def test_offers_survive_a_restart_on_the_sending_side(tmp_path):
    _game, _where, wire, _incoming, _manager, _ops, _places, outgoing = setup_pair(tmp_path)
    again = offers.Outgoing(outgoing.path, outgoing.work_dir, Shares())
    assert again.restore() == len(wire["shares"])
    for share in wire["shares"].values():
        restored = again.shares.get(share["share"])
        assert restored is not None and restored.manifest["root"] == share["root"] and restored.peers == {PEER}
    again.withdraw(wire["id"])
    assert all(again.shares.get(s["share"]) is None for s in wire["shares"].values())
    assert not os.path.exists(os.path.join(outgoing.work_dir, wire["id"])) and again.list() == []


def test_the_app_routes_steam_results_and_adopts_the_saves(make_app, monkeypatch):  # noqa: F811
    async def scenario():
        app = make_app("a")
        await app.start()
        await app.set_module_enabled("replication", True)
        try:
            with pytest.raises(ValueError, match="not paired"):
                await app.replication_send("shortcut:1:1", "device-zzzz-0009")
            op_id = app._ops().enqueue("replication", "set-shortcut-exe", {"appid": NEW_APPID, "value": "x"})
            record = {
                "offer": offers.validate(good_offer()),
                "peer": SENDER,
                "state": "registering",
                "ops": {"0": "add", str(op_id): "set-shortcut-exe"},
                "opsDone": ["0"],
                "targets": {},
                "appid": NEW_APPID,
            }
            app.incoming._save({"0123456789abcdef": record})
            key = f"shortcut:9:{NEW_APPID}"

            async def fake_discover(refresh=False):
                return {"games": [{"kind": "shortcut", "appid": NEW_APPID, "key": key}]}

            chosen, changed = [], []

            async def fake_key(k, value, title=None):
                chosen.append((k, value))

            async def fake_config(k, changes):
                changed.append((k, changes))

            monkeypatch.setattr(app, "discover_games", fake_discover)
            monkeypatch.setattr(app, "set_game_key", fake_key)
            monkeypatch.setattr(app, "update_game_config", fake_config)
            assert app._ops().claim()["id"] == op_id  # the frontend takes it, as in Gaming Mode
            await app.steam_ops_finish(op_id, True, {})
            assert chosen == [(key, "test-game")] and changed == [(key, {"enabled": True})]
            assert (await app.replication_offers())["incoming"][0]["state"] == "done"
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_an_offer_of_only_artwork_holds_no_game():
    offer = good_offer()
    offer["shares"] = {"art": offer["shares"]["art"], "tool": {"share": "1" * 32, "root": "2" * 64, "bytes": 1}}
    with pytest.raises(offers.OfferError, match="holds no game"):
        offers.validate(offer)


def test_registration_waits_for_every_copy(tmp_path):
    _game, _where, wire, incoming, _manager, ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    record = incoming._load()[wire["id"]]
    record.update(state="transferring", jobs={"install": "j-install", "prefix": "j-prefix"}, targets={})
    incoming._save({wire["id"]: record})
    incoming.job_finished(transfer.Job("j-install", PEER, "s", "r", str(tmp_path / "x"), state="done"))
    assert ops.queued == [] and incoming.list()[0]["state"] == "transferring"


def test_the_game_is_ready_only_after_every_steam_operation(tmp_path):
    _game, _where, wire, incoming, manager, _ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    incoming.op_finished(1, True, {"appid": NEW_APPID})
    assert incoming.op_finished(2, True, {})["state"] == "registering"
    assert incoming.op_finished(99, True, {}) is None  # not one of this offer's operations


def test_an_empty_compatdata_folder_is_replaced_and_a_full_one_is_not(tmp_path):
    _game, _where, wire, incoming, manager, _ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    os.makedirs(os.path.join(places["compatdata"], str(NEW_APPID)))  # Steam may make it right away
    incoming.op_finished(1, True, {"appid": NEW_APPID})
    assert os.path.isdir(os.path.join(places["compatdata"], str(NEW_APPID), "pfx"))

    other = tmp_path / "second"
    other.mkdir()
    _g, _w, wire2, incoming2, manager2, _ops2, places2, _ = setup_pair(other)
    deliver(incoming2, wire2)
    run_accept(incoming2, manager2, wire2["id"])
    taken = os.path.join(places2["compatdata"], str(NEW_APPID))
    os.makedirs(taken)
    with open(os.path.join(taken, "keep.txt"), "w") as handle:
        handle.write("not ours")
    incoming2.op_finished(1, True, {"appid": NEW_APPID})
    state = incoming2.list()[0]
    assert state["state"] == "failed" and "already exists" in state["reason"]
    assert os.path.isfile(os.path.join(taken, "keep.txt"))


def test_stop_and_remove_never_deletes_outside_its_places(tmp_path):
    _game, _where, wire, incoming, _manager, _ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "file.txt").write_text("keep me")
    record = incoming._load()[wire["id"]]
    record.update(state="failed", targets={"install": str(outside)}, jobs={})
    incoming._save({wire["id"]: record})
    asyncio.run(incoming.stop(wire["id"]))
    assert (outside / "file.txt").read_text() == "keep me"


def test_an_accepted_offer_cannot_be_declined(tmp_path):
    _game, _where, wire, incoming, manager, _ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    with pytest.raises(offers.OfferError, match="not accepted"):
        incoming.decline(wire["id"])


def test_artwork_outside_its_folder_is_never_served(tmp_path):
    _game, _where, wire, incoming, manager, ops, _places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    run_accept(incoming, manager, wire["id"])
    incoming.op_finished(1, True, {"appid": NEW_APPID})
    art_op = next(i for i, (k, _p) in enumerate(ops.queued, start=1) if k == "set-artwork")
    for name in ("../in.json", "../../escape.png"):
        claimed = {
            "id": art_op,
            "module": "replication",
            "kind": "set-artwork",
            "state": "claimed",
            "payload": {"file": name},
        }
        with pytest.raises(offers.OfferError):
            incoming.staged_file(claimed)


def test_clearing_a_finished_game_from_the_list_keeps_the_game(tmp_path):
    _game, _where, wire, incoming, manager, ops, places, _ = setup_pair(tmp_path)
    deliver(incoming, wire)
    with pytest.raises(offers.OfferError, match="finished"):
        incoming.dismiss(wire["id"])  # still only an offer: decline it instead
    run_accept(incoming, manager, wire["id"])
    incoming.op_finished(1, True, {"appid": NEW_APPID})
    for op_id in range(2, len(ops.queued) + 1):
        incoming.op_finished(op_id, True, {})
    incoming.dismiss(wire["id"])
    assert incoming.list() == []
    assert os.path.isfile(os.path.join(places["library"], "Test Game", "bin", "game.exe"))
    assert os.path.isdir(os.path.join(places["compatdata"], str(NEW_APPID)))
    assert not [k for k, _ in ops.queued if k == "remove-shortcut"]
