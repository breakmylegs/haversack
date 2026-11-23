"""Looks to the other handheld, end to end (R29 stage 1b, ADR-0092): themes, sound packs and the videos
Haversack set travel to a paired device and land beside what is there, never over it."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest

from keepsake.looks import animations as anim
from keepsake.looks import lookplan
from keepsake.replication import jobs, offers, sleepguard
from keepsake.replication.link import ServeError, Session
from keepsake.replication.source import Shares
from test_replication_transfer import PEER, FakeConnection

SENDER = "device-aaaa-0001"
WEBM = anim.EBML + b"synthetic video"


def write(path: Any, data: str | bytes = "x") -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data) if isinstance(data, bytes) else path.write_text(data)
    return path


def sender(tmp_path: Any) -> tuple[Any, anim.Animations]:
    hb = tmp_path / "source" / "homebrew"
    write(hb / "themes" / "Clean" / "theme.json", json.dumps({"name": "Clean"}))
    write(hb / "themes" / "Clean" / "shared.css", "body {}")
    write(hb / "themes" / "Shared" / "theme.json", json.dumps({"name": "Shared, sender's"}))
    write(hb / "themes" / "NoManifest" / "x.css", "x")
    write(hb / "sounds" / "Chimes" / "pack.json", json.dumps({"name": "Chimes"}))
    write(hb / "sounds" / "Chimes" / "click.wav", b"RIFF")
    steam = tmp_path / "source" / "steam"
    (steam / "config").mkdir(parents=True)
    write(tmp_path / "source" / "Videos" / "Aurora.webm", WEBM)
    anims = anim.Animations(
        str(steam), str(tmp_path / "source" / "data"), [("Videos", str(tmp_path / "source" / "Videos"))]
    )
    anims.apply("boot", "0:Aurora.webm")
    write(steam / "config" / "uioverrides" / "movies" / "steam_os_suspend.webm", WEBM + b" not Haversack's")
    return hb, anims


def test_what_can_be_sent_and_the_plan(tmp_path: Any) -> None:
    hb, anims = sender(tmp_path)
    assert lookplan.available(str(hb), anims) == {
        "themes": ["Clean", "Shared"],
        "sounds": ["Chimes"],
        "animations": ["deck_startup.webm"],  # only the video Haversack set, never another tool's
    }
    plan = lookplan.plan(str(hb), anims, ["themes", "animations"])
    assert {p: m for p, (_r, m) in plan.items()} == {"themes": ["Clean", "Shared"], "animations": ["deck_startup.webm"]}
    for bad in ([], ["wallpapers"], ["themes", "keys"]):
        with pytest.raises(lookplan.LookPlanError):
            lookplan.plan(str(hb), anims, bad)
    empty = tmp_path / "empty"
    with pytest.raises(lookplan.LookPlanError, match="nothing"):
        lookplan.plan(str(empty), anim.Animations(str(empty), str(empty), []), ["sounds"])
    assert (
        lookplan.describe({"themes": {"members": ["a", "b"]}, "sounds": {"members": ["c"]}})
        == "2 themes and 1 sound pack"
    )


def offer(**shares: Any) -> dict[str, Any]:
    return {"kind": "looks", "id": "offer-abcdef12", "shares": shares}


def share(members: list[Any], size: Any = 10) -> dict[str, Any]:
    return {"share": "s1", "root": "hash", "bytes": size, "members": members}


def test_the_receiver_refuses_anything_unexpected() -> None:
    assert lookplan.validate(offer(themes=share(["Clean", "Clean"])))["shares"]["themes"]["members"] == ["Clean"]
    for bad in (
        None,
        {**offer(themes=share(["Clean"])), "kind": "emulator"},
        {**offer(themes=share(["Clean"])), "id": "../x"},
        offer(),
        offer(keys=share(["prod.keys"])),
        offer(themes=share(["../escape"])),
        offer(themes=share([".hidden"])),
        offer(themes=share(["a/b"])),
        offer(themes=share([7])),
        offer(themes=share([])),
        offer(themes=share(["x" * 121])),
        offer(animations=share(["evil.webm"])),
        offer(themes=share(["Clean"], size=-1)),
        offer(themes=share(["Clean"], size=True)),
        offer(themes={"share": 3, "bytes": 1, "members": ["Clean"]}),
    ):
        with pytest.raises(lookplan.LookPlanError):
            lookplan.validate(bad)
    with pytest.raises(lookplan.LookPlanError):
        lookplan.validate(offer(themes=share([f"t{i}" for i in range(lookplan.MAX_MEMBERS + 1)])))


def receiver(tmp_path: Any, enabled: bool = True) -> tuple[Any, Any, Any]:
    hb = tmp_path / "target" / "homebrew"
    write(hb / "themes" / "Shared" / "theme.json", json.dumps({"name": "Shared, the receiver's own"}))
    runtime = tmp_path / "target" / "runtime"
    handler = lookplan.Handler(lambda: str(hb), str(runtime), lambda: enabled)
    return hb, runtime, handler


def pair(tmp_path: Any, parts: list[str], enabled: bool = True) -> tuple[Any, ...]:
    src, anims = sender(tmp_path)
    shares = Shares()
    outgoing = offers.Outgoing(str(tmp_path / "out.json"), str(tmp_path / "out"), shares)
    plan = lookplan.plan(str(src), anims, parts)
    wire = outgoing.prepare_parts(lookplan.KIND, "Looks", plan, PEER, {"from": {"name": "Test handheld A"}})

    async def connect() -> FakeConnection:
        return FakeConnection(shares)

    guard = sleepguard.SleepGuard(bus_path=str(tmp_path / "no-bus"), platform="linux")
    manager = jobs.Transfers(str(tmp_path / "jobs.json"), lambda _p: connect, guard=guard, retries=0)
    hb, runtime, handler = receiver(tmp_path, enabled)
    incoming = offers.Incoming(
        str(tmp_path / "in.json"),
        manager,
        lambda *_: 0,
        lambda: {"home": str(tmp_path / "target")},
        kinds={"looks": handler},
    )
    manager.on_finished = incoming.job_finished
    return hb, runtime, wire, incoming, manager


def deliver(incoming: Any, wire: dict[str, Any]) -> dict[str, Any]:
    handle = incoming.kind_handler("looks")
    return asyncio.run(handle(Session(SENDER, "127.0.0.1", None, None), {"offer": wire}))


def accept(incoming: Any, manager: Any, offer_id: str) -> None:
    async def scenario() -> None:
        incoming.accept(offer_id)
        while manager.tasks:
            await asyncio.gather(*list(manager.tasks.values()))
            await asyncio.sleep(0)

    asyncio.run(scenario())


def test_the_wire_offer_names_members_and_no_paths(tmp_path: Any) -> None:
    *_, wire, _incoming, _manager = pair(tmp_path, ["themes", "sounds", "animations"])
    assert wire["kind"] == "looks" and set(wire["shares"]) == {"themes", "sounds", "animations"}
    assert wire["shares"]["animations"]["members"] == ["deck_startup.webm"]
    text = json.dumps(wire)
    assert str(tmp_path) not in text and "homebrew" not in text and "uioverrides" not in text
    themes = tmp_path / "source" / "homebrew" / "themes"
    offered = sum(p.stat().st_size for name in ("Clean", "Shared") for p in (themes / name).rglob("*") if p.is_file())
    assert wire["shares"]["themes"]["bytes"] == offered  # the theme without a manifest is not even shared


def test_looks_arrive_beside_what_is_there_never_over_it(tmp_path: Any) -> None:
    hb, runtime, wire, incoming, manager = pair(tmp_path, ["themes", "sounds", "animations"])
    assert deliver(incoming, wire) == {"type": "offer-received", "id": wire["id"]}
    (listed,) = incoming.list()
    assert listed["state"] == "offered" and listed["title"] == "Looks: 2 themes, 1 sound pack and 1 video"
    accept(incoming, manager, wire["id"])
    assert (hb / "themes" / "Clean" / "shared.css").read_text() == "body {}"
    assert json.loads((hb / "themes" / "Shared" / "theme.json").read_text())["name"] == "Shared, the receiver's own"
    assert not (hb / "themes" / "NoManifest").exists()  # only themes with a manifest travel
    assert (hb / "sounds" / "Chimes" / "click.wav").read_bytes() == b"RIFF"
    video = runtime / "looks" / "animations" / "From Test handheld A" / "deck_startup.webm"
    assert video.read_bytes() == WEBM
    assert not list((runtime / "looks" / "animations" / "From Test handheld A").glob("steam_os_suspend*"))
    for folder in (hb / "themes", hb / "sounds", video.parent):
        assert not [n for n in os.listdir(folder) if n.startswith(lookplan.STAGING)]
    done = incoming._load()[wire["id"]]
    assert done["state"] == "done" and done["skipped"] == {"themes": ["Shared"]}
    assert done["reason"].startswith("3 added; 1 already here") and "Device, Looks" in done["reason"]


def test_nothing_is_copied_while_looks_is_off_on_the_receiver(tmp_path: Any) -> None:
    hb, _runtime, wire, incoming, manager = pair(tmp_path, ["themes"], enabled=False)
    deliver(incoming, wire)
    with pytest.raises(offers.OfferError, match="switch on Looks"):
        accept(incoming, manager, wire["id"])
    assert sorted(os.listdir(hb / "themes")) == ["Shared"]


def test_a_device_without_the_kind_refuses_it(tmp_path: Any) -> None:
    *_, wire, incoming, _manager = pair(tmp_path, ["sounds"])
    incoming.kinds = {}
    with pytest.raises(ServeError, match="does not take looks"):
        deliver(incoming, wire)
    incoming.kinds = {"looks": receiver(tmp_path)[2]}
    with pytest.raises(ServeError, match="will not use"):
        deliver(incoming, {**wire, "shares": {"themes": share(["../x"])}})


def test_finish_moves_only_what_was_offered(tmp_path: Any) -> None:
    hb, _runtime, handler = receiver(tmp_path)
    clean = handler.validate(offer(themes=share(["Clean"])))
    staged = handler.targets(clean, clean["id"])
    os.makedirs(os.path.join(staged["themes"], "Clean"))
    open(os.path.join(staged["themes"], "Clean", "theme.json"), "w").close()
    os.makedirs(os.path.join(staged["themes"], "Smuggled"))
    done = handler.finish(clean, staged)
    assert done["placed"] == {"themes": ["Clean"]} and not (hb / "themes" / "Smuggled").exists()
    assert not os.path.exists(staged["themes"])


def test_the_app_sends_only_with_looks_and_replication_on(tmp_path: Any) -> None:
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    home = tmp_path / "home"
    (home / ".steam" / "steam" / "config").mkdir(parents=True)
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, auto_refresh_manifest=False, home=str(home))

    async def run() -> None:
        with pytest.raises(ValueError, match="Looks is off"):
            await app.looks_send(PEER, ["themes"])
        await app.set_module_enabled("looks", True)
        with pytest.raises(ValueError, match="Replication is off"):
            await app.looks_send(PEER, ["themes"])
        assert (await app.looks_status())["sendable"] == {"themes": 0, "sounds": 0, "animations": 0}

    asyncio.run(run())


def test_a_leftover_copy_of_the_same_offer_stops_it(tmp_path: Any) -> None:
    hb, _runtime, handler = receiver(tmp_path)
    clean = handler.validate(offer(themes=share(["Clean"])))
    os.makedirs(hb / "themes" / f"{lookplan.STAGING}themes-{clean['id']}")
    with pytest.raises(lookplan.LookPlanError, match="in the way"):
        handler.targets(clean, clean["id"])


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need POSIX here")
@pytest.mark.posix
def test_linked_theme_folders_are_never_offered(tmp_path: Any) -> None:
    hb, anims = sender(tmp_path)
    write(tmp_path / "elsewhere" / "theme.json", "{}")
    os.symlink(tmp_path / "elsewhere", hb / "themes" / "Linked")
    assert "Linked" not in lookplan.available(str(hb), anims)["themes"]
