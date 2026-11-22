"""An emulator game from one device to the other, end to end (R26 stage 2, ADR-0087): offer, accept, copy,
put in place without replacing anything, and the shortcut from the receiver's own Steam ROM Manager parser."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from keepsake.replication import emulators as emu
from keepsake.replication import emuplan, jobs, offers, sleepguard
from keepsake.replication.link import Session
from keepsake.replication.source import Shares
from test_replication_transfer import PEER, FakeConnection

SENDER = "device-aaaa-0001"
APPID = 4000777


def write(path: Any, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def emudeck(home: Any) -> Any:
    write(
        home / ".config" / "EmuDeck" / "settings.sh",
        f'romsPath="{home}/Emulation/roms"\nbiosPath="{home}/Emulation/bios"\n',
    )
    (home / "Emulation" / "roms" / "switch").mkdir(parents=True, exist_ok=True)
    return home / "Emulation" / "roms"


class Ops:
    def __init__(self) -> None:
        self.queued: list[tuple[str, dict[str, Any]]] = []

    def enqueue(self, kind: str, payload: dict[str, Any]) -> int:
        self.queued.append((kind, payload))
        return len(self.queued)


def pair(tmp_path: Any, with_keys: bool = False) -> tuple[Any, ...]:
    source, target = tmp_path / "source", tmp_path / "target"
    roms = emudeck(source)
    write(roms / "switch" / "Title [0100ABCD00000000].nsp", "game data")
    write(roms / "switch" / "Other.nsp", "the sender's copy")
    write(source / "Applications" / "Eden.AppImage", "elf")
    write(source / ".config" / "eden" / "qt-config.ini", "[UI]\n")
    write(source / ".local" / "share" / "eden" / "keys" / "prod.keys", "k")
    target_roms = emudeck(target)
    write(target_roms / "switch" / "Kept.nsp", "the receiver's own")
    srm = target / ".config" / "steam-rom-manager" / "userData"
    write(
        srm / "userConfigurations.json",
        json.dumps(
            [
                {
                    "romDirectory": "${romsdirglobal}/switch",
                    "executable": {"path": "/tools/launchers/eden.sh"},
                    "executableArgs": '"${filePath}"',
                }
            ]
        ),
    )
    write(srm / "userSettings.json", json.dumps({"environmentVariables": {"romsDirectory": str(target_roms)}}))

    game = next(g for g in emu.games(str(roms)) if g.name.startswith("Title"))
    eden = next(e for e in emu.emulators(str(source)) if e["name"] == "Eden")
    plan = emuplan.plan(str(source), str(roms), game, eden, emuplan.summary(str(target)), with_keys)
    shares = Shares()
    outgoing = offers.Outgoing(str(tmp_path / "out.json"), str(tmp_path / "out"), shares)
    wire = outgoing.prepare_emulator(plan, PEER, {"from": {"name": "Test handheld A"}})

    async def connect() -> FakeConnection:
        return FakeConnection(shares)

    guard = sleepguard.SleepGuard(bus_path=str(tmp_path / "no-bus"), platform="linux")
    manager = jobs.Transfers(str(tmp_path / "jobs.json"), lambda _p: connect, guard=guard, retries=0)
    ops = Ops()
    incoming = offers.Incoming(str(tmp_path / "in.json"), manager, ops.enqueue, lambda: {"home": str(target)})
    manager.on_finished = incoming.job_finished
    return target, target_roms, wire, incoming, manager, ops


def accept(incoming: Any, manager: Any, offer_id: str) -> None:
    async def scenario() -> None:
        incoming.accept(offer_id)
        while manager.tasks:
            await asyncio.gather(*list(manager.tasks.values()))
            await asyncio.sleep(0)

    asyncio.run(scenario())


def deliver(incoming: Any, wire: dict[str, Any]) -> None:
    reply = asyncio.run(incoming.handle_emu_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": wire}))
    assert reply == {"type": "offer-received", "id": wire["id"]}


def test_the_wire_offer_has_no_paths(tmp_path: Any) -> None:
    _target, _roms, wire, *_ = pair(tmp_path)
    assert wire["kind"] == "emulator" and set(wire["shares"]) == {"rom", "app", "config"}
    text = json.dumps(wire)
    assert str(tmp_path) not in text and "prod.keys" not in text


def test_an_emulator_game_arrives_is_placed_and_gets_a_shortcut(tmp_path: Any) -> None:
    target, target_roms, wire, incoming, manager, ops = pair(tmp_path)
    deliver(incoming, wire)
    (listed,) = incoming.list()
    assert listed["state"] == "offered" and listed["title"].startswith("Title")
    accept(incoming, manager, wire["id"])
    placed = target_roms / "switch" / "Title [0100ABCD00000000].nsp"
    assert placed.read_text() == "game data"
    assert not (target_roms / "switch" / "Other.nsp").exists()  # only the one game travels
    assert (target_roms / "switch" / "Kept.nsp").read_text() == "the receiver's own"
    assert (target / "Applications" / "Eden.AppImage").read_text() == "elf"
    assert (target / ".config" / "eden" / "qt-config.ini").exists()
    assert not (target / ".local" / "share" / "eden" / "keys").exists()  # no keys without the confirmation
    assert not [n for n in os.listdir(target_roms / "switch") if n.startswith(".keepsake-emu-")]
    kind, payload = ops.queued[0]
    assert kind == "add-shortcut" and payload["exe"] == "/tools/launchers/eden.sh"
    assert os.path.normpath(payload["launchOptions"].strip('"')) == os.path.normpath(placed)
    assert payload["name"].startswith("Title")
    incoming.op_finished(1, True, {"appid": APPID})
    queued = {k: p for k, p in ops.queued[1:]}
    assert queued["set-shortcut-exe"] == {"appid": APPID, "value": "/tools/launchers/eden.sh"}
    assert os.path.normpath(queued["set-launch-options"]["value"].strip('"')) == os.path.normpath(placed)
    for op_id in range(2, len(ops.queued) + 1):
        incoming.op_finished(op_id, True, {})
    assert incoming.list()[0]["state"] == "done"


def test_keys_travel_only_when_asked(tmp_path: Any) -> None:
    target, _roms, wire, incoming, manager, _ops = pair(tmp_path, with_keys=True)
    assert "keys" in wire["shares"]
    deliver(incoming, wire)
    accept(incoming, manager, wire["id"])
    assert (target / ".local" / "share" / "eden" / "keys" / "prod.keys").read_text() == "k"


def test_a_game_already_there_is_never_replaced(tmp_path: Any) -> None:
    _target, target_roms, wire, incoming, manager, ops = pair(tmp_path)
    write(target_roms / "switch" / "Title [0100ABCD00000000].nsp", "the receiver's version")
    deliver(incoming, wire)
    accept(incoming, manager, wire["id"])
    assert (target_roms / "switch" / "Title [0100ABCD00000000].nsp").read_text() == "the receiver's version"
    record = incoming.list()[0]
    assert record["state"] == "done" and ops.queued == []  # nothing new, so no shortcut


def test_a_device_without_an_emulator_setup_refuses_on_accept(tmp_path: Any) -> None:
    target, _roms, wire, incoming, _manager, _ops = pair(tmp_path)
    os.remove(target / ".config" / "EmuDeck" / "settings.sh")
    os.rename(target / "Emulation", target / "Gone")
    deliver(incoming, wire)
    try:
        incoming.accept(wire["id"])
        raise AssertionError("accept should refuse")
    except offers.OfferError as exc:
        assert "emulator setup" in str(exc)


def test_a_bad_emulator_offer_is_refused_and_not_stored(tmp_path: Any) -> None:
    from keepsake.replication.link import ServeError

    _target, _roms, wire, incoming, _manager, _ops = pair(tmp_path)
    for change in ({"system": "../../etc"}, {"emulator": "EvilEmu"}, {"shares": {"shell": wire["shares"]["rom"]}}):
        bad = {**wire, **change}
        try:
            asyncio.run(incoming.handle_emu_offer(Session(SENDER, "127.0.0.1", None, None), {"offer": bad}))
            raise AssertionError(f"accepted {change}")
        except ServeError:
            pass
    assert incoming.list() == []
