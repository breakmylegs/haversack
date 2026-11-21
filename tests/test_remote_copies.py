"""Games you can stream from another device: Steam Remote Play's entries (ADR-0064). Synthetic data only."""

from __future__ import annotations

import asyncio

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake import devicechecks, discovery, remotecopies
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths
from keepsake.statedb import StateDB
from keepsake.steamops import SteamOps, SteamOpsError

GONE = "/home/someone-else/Games/Example/game.exe"  # a path not on this device


# The file's view: never "remote"


@pytest.mark.parametrize(
    ("exe", "start", "prefix", "exists", "expected"),
    [
        (GONE, "", "/p", set(), "local"),  # a prefix here: local whatever the paths say
        (GONE, "", None, {GONE}, "local"),
        ("/home/x/a.exe", "/home/x", None, {"/home/x"}, "local"),  # the start folder is enough
        (GONE, "/home/someone-else/Games/Example", None, set(), "unsure"),  # an unusual path: still listed
        ("/run/media/card/Games/a.exe", "", None, set(), "unsure"),
        ("", "", None, set(), "unsure"),
        ("game.exe", "", None, set(), "unsure"),
    ],
)
def test_shortcut_presence_from_the_file(exe, start, prefix, exists, expected):
    assert discovery.shortcut_presence(exe, start, prefix, exists=lambda p: p in exists) == expected


@pytest.mark.parametrize(
    ("file", "steam", "expected"),
    [
        ("local", "local", "local"),
        ("unsure", "local", "local"),  # Steam says it is installed here
        ("local", "remote", "unsure"),  # in this device's file: never remote, only labelled
        ("unsure", "remote", "unsure"),
        ("local", "unsure", "local"),
        ("unsure", "unsure", "unsure"),
        ("local", None, "local"),
        ("unsure", None, "unsure"),
        ("remote", None, "unsure"),  # nothing from the file may come out remote
    ],
)
def test_combine_never_makes_a_shortcut_in_the_file_remote(file, steam, expected):
    assert remotecopies.combine(file, steam) == expected


def test_report_is_checked():
    clean = remotecopies.clean_report(
        [
            {"appid": 3000000001, "name": "A", "steam": "remote", "clients": ["Other", 5, " "], "hidden": True},
            {"appid": 3000000001, "name": "dup", "steam": "local"},
            {"appid": 0, "steam": "local"},
            {"appid": True, "steam": "local"},
            {"appid": 2**32, "steam": "local"},
            {"appid": 3000000002, "steam": "maybe"},
            "nonsense",
            {"appid": 3000000003, "name": "x" * 500, "steam": "local", "hidden": "yes"},
        ]
    )
    assert [e["appid"] for e in clean] == [3000000001, 3000000003]
    assert clean[0]["clients"] == ["Other"] and clean[0]["hidden"] is True
    assert len(clean[1]["name"]) == remotecopies.MAX_NAME and clean[1]["hidden"] is False
    with pytest.raises(ValueError):
        remotecopies.clean_report({"appid": 1})


def _shortcut(appid, name, presence):
    return {"kind": "shortcut", "appid": appid, "name": name, "key": f"shortcut:7:{appid}", "presence": presence}


def test_only_entries_steam_alone_reports_are_streaming_entries(tmp_path):
    store = remotecopies.RemoteCopies(str(tmp_path))
    store.save_report(
        [
            {"appid": 3000000001, "name": "Example Quest", "steam": "local"},
            {"appid": 3000000002, "name": "Odd Path", "steam": "remote"},  # in the file, Steam says it streams
            {"appid": 3000000009, "name": "Example Quest", "steam": "remote", "clients": ["Desk"]},
            {"appid": 3000000010, "name": "Puzzle", "steam": "unsure"},
        ]
    )
    games = store.apply(
        [
            _shortcut(3000000001, "Example Quest", "unsure"),
            _shortcut(3000000002, "Odd Path", "unsure"),
            _shortcut(3000000003, "No Report", "unsure"),
            {"kind": "steam", "appid": 1000010, "name": "Example Quest", "key": "steam:1000010"},
        ]
    )
    presence = {g["appid"]: g.get("presence") for g in games}
    assert presence == {3000000001: "local", 3000000002: "unsure", 3000000003: "unsure", 1000010: None}
    copies = {c["appid"]: c for c in store.copies(games)}
    assert copies[3000000009] == {
        "appid": 3000000009,
        "name": "Example Quest",
        "presence": "remote",
        "from": ["Desk"],
        "clash": True,  # also installed here
        "hidden": False,
    }
    assert copies[3000000002]["presence"] == "unsure"  # in the file: never certain, never hidden
    assert copies[3000000010]["presence"] == "unsure"
    assert set(copies) == {3000000009, 3000000002, 3000000010}
    assert store.copies(games)[0]["appid"] == 3000000009  # certain ones first


def test_the_guard_notices_local_shortcuts_hidden_from_elsewhere(tmp_path):
    clock = iter(range(100, 200))
    store = remotecopies.RemoteCopies(str(tmp_path), clock=lambda: next(clock))
    base = [
        {"appid": 3000000001, "name": "Mine", "steam": "local"},
        {"appid": 3000000002, "name": "Stream", "steam": "remote"},
        {"appid": 3000000003, "name": "New", "steam": "local", "hidden": True},  # hidden before we saw it
    ]
    assert store.save_report(base)["newlyHidden"] == []
    store.record(3000000002, "Stream", "hidden")
    later = [
        {"appid": 3000000001, "name": "Mine", "steam": "local", "hidden": True},
        {"appid": 3000000002, "name": "Stream", "steam": "remote", "hidden": True},
        {"appid": 3000000003, "name": "New", "steam": "local", "hidden": True},
    ]
    assert store.save_report(later)["newlyHidden"] == [{"appid": 3000000001, "name": "Mine"}]
    assert store.save_report(later)["newlyHidden"] == []  # told once
    again = [{**e, "hidden": False} if e["appid"] == 3000000002 else e for e in later]
    store.save_report(again)
    assert store.tidy_log()["hidden"]["3000000002"]["state"] == "came-back"


def test_our_own_pending_hide_is_not_reported_as_a_surprise(tmp_path):
    store = remotecopies.RemoteCopies(str(tmp_path))
    store.save_report([{"appid": 3000000005, "name": "Odd", "steam": "local"}])
    store.record(3000000005, "Odd", "pending")
    found = store.save_report([{"appid": 3000000005, "name": "Odd", "steam": "local", "hidden": True}])
    assert found["newlyHidden"] == []


def test_the_guard_ignores_streaming_entries_hidden_elsewhere(tmp_path):
    store = remotecopies.RemoteCopies(str(tmp_path))
    store.save_report([{"appid": 3000000007, "name": "Theirs", "steam": "remote"}])
    found = store.save_report([{"appid": 3000000007, "name": "Theirs", "steam": "remote", "hidden": True}])
    assert found == {"newlyHidden": []}


def test_check_findings():
    games = [_shortcut(1, "A", "local"), _shortcut(2, "B", "unsure"), _shortcut(3, "C", "unsure")]
    games.append({"kind": "steam", "appid": 9, "name": "S", "key": "steam:9", "presence": "local"})
    copies = [
        {"appid": 7, "name": "A", "presence": "remote", "clash": True},
        {"appid": 2, "name": "B", "presence": "unsure", "clash": False},  # Steam says this shortcut streams
    ]
    log = {"hidden": {"7": {"state": "hidden"}, "4": {"state": "came-back"}, "5": {"state": "undone"}}}
    synced = {"shortcut:7:2", "shortcut:7:3"}  # C is synced and only unsure from the file: no failure
    found = remotecopies.check(copies, games, lambda key: key in synced, log)
    assert found == {
        "local": 1,
        "remote": 1,
        "unsure": 1,
        "clashes": ["A"],
        "syncedOnCopy": ["B"],
        "hidden": 1,
        "cameBack": 1,
    }


# The app

MINE, ODD = (discovery.unsigned_appid(-1000000001 - i) for i in range(2))
STREAM, PUZZLE = 3000000020, 3000000021  # Steam Remote Play entries: only in Steam's report


def _app(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    game_dir = home / "Games" / "Mine"
    game_dir.mkdir(parents=True)
    (game_dir / "game.exe").write_text("x")
    make_fake_steam(
        home,
        users={
            "7": [
                shortcut_entry(-1000000001, "Mine", (game_dir / "game.exe").as_posix()),
                shortcut_entry(-1000000002, "Odd Path", GONE),  # a real shortcut with an unusual exe path
            ]
        },
        most_recent="7",
    )
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="0.27.0", home=str(home), auto_refresh_manifest=False
    )
    events = []

    async def emit(event, *args):
        events.append((event, args))

    app.emit = emit
    return app, events


def _verified(app):
    """The tidy-up's hidden switch (not a user setting) as a later version would set it."""
    app.settings._data = {**app.settings._data, "streamTidyVerified": True}


def _report(hidden=(), odd="unsure"):
    return [
        {"appid": MINE, "name": "Mine", "steam": "local", "hidden": MINE in hidden},
        {"appid": ODD, "name": "Odd Path", "steam": odd, "hidden": ODD in hidden},
        {"appid": STREAM, "name": "Mine", "steam": "remote", "clients": ["Desk"], "hidden": STREAM in hidden},
        {"appid": PUZZLE, "name": "Puzzle", "steam": "unsure", "hidden": PUZZLE in hidden},
    ]


def test_real_shortcuts_stay_listed_and_streaming_entries_never_appear(tmp_path):
    app, _events = _app(tmp_path)

    async def go():
        plain = {g["appid"]: g["presence"] for g in (await app.discover_games())["games"]}
        await app.remote_copies_report(_report(odd="remote"))
        after = {g["appid"]: g["presence"] for g in (await app.discover_games())["games"]}
        matched = {m["key"] for m in await app.match_games()}
        return plain, after, matched

    plain, after, matched = asyncio.run(go())
    assert plain == {MINE: "local", ODD: "unsure"}  # an unusual path or a missing prefix never loses a game
    assert after == {MINE: "local", ODD: "unsure"}  # even when Steam says it streams: labelled, kept
    assert matched == {f"shortcut:7:{MINE}", f"shortcut:7:{ODD}"}
    assert app._advisor_map_game(STREAM)["kind"] == "unknown"  # a streaming entry is never given to Advisor
    assert app._advisor_map_game(MINE)["name"] == "Mine"


def test_tidy_up_is_off_until_verified(tmp_path):
    app, _events = _app(tmp_path)

    async def go():
        await app.start()
        await app.remote_copies_report(_report())
        status = await app.remote_copies_status()
        with pytest.raises(ValueError, match="not available yet"):
            await app.tidy_copies([STREAM])
        app.settings.set("tidyAutomatically", True)
        automatic = await app.remote_copies_report(_report())
        claimed = await app.steam_ops_claim()
        await app.stop()
        return status, automatic, claimed

    status, automatic, claimed = asyncio.run(go())
    assert status["tidyAvailable"] is False
    assert automatic["tidied"] == 0 and claimed is None
    with pytest.raises(ValueError, match="unknown or read-only"):  # not a setting the frontend can change
        app.settings.set("streamTidyVerified", True)


def test_tidy_up_hides_only_certain_streaming_entries_and_undo_shows_them(tmp_path):
    app, events = _app(tmp_path)
    _verified(app)

    async def go():
        await app.start()
        await app.remote_copies_report(_report())
        status = await app.remote_copies_status()
        for appids in ([STREAM, PUZZLE], [MINE], [ODD]):  # unsure, local, or in the file: never
            with pytest.raises(ValueError, match="not certainly"):
                await app.tidy_copies(appids)
        with pytest.raises(ValueError):
            await app.tidy_copies([])
        queued = await app.tidy_copies([STREAM])
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": True})
        hidden_state = (await app.remote_copies_status())["log"][str(STREAM)]["state"]
        undo = await app.undo_tidy()
        op2 = await app.steam_ops_claim()
        await app.steam_ops_finish(op2["id"], True, {"readBack": False})
        log = (await app.remote_copies_status())["log"]
        await app.stop()
        return status, queued, op, hidden_state, undo, op2, log

    status, queued, op, hidden_state, undo, op2, log = asyncio.run(go())
    assert status["tidyAvailable"] is True
    assert {c["appid"]: c["presence"] for c in status["copies"]} == {STREAM: "remote", PUZZLE: "unsure"}
    assert queued == {"queued": 1}
    assert (op["kind"], op["module"], op["payload"]) == ("set-hidden", "core", {"appid": STREAM, "hidden": True})
    assert hidden_state == "hidden"
    assert undo == {"queued": 1}
    assert op2["payload"] == {"appid": STREAM, "hidden": False}
    assert log[str(STREAM)]["state"] == "undone"
    assert ("keepsake_steam_ops", ()) in events


def test_a_failed_read_back_is_recorded(tmp_path):
    app, _events = _app(tmp_path)
    _verified(app)

    async def go():
        await app.start()
        await app.remote_copies_report(_report())
        await app.tidy_copies([STREAM])
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": False})
        state = (await app.remote_copies_status())["log"][str(STREAM)]["state"]
        await app.stop()
        return state

    assert asyncio.run(go()) == "failed"


def test_automatic_tidy_up_skips_entries_the_user_brought_back(tmp_path):
    app, _events = _app(tmp_path)
    _verified(app)

    async def go():
        await app.start()
        first = await app.remote_copies_report(_report())
        app.settings.set("tidyAutomatically", True)
        second = await app.remote_copies_report(_report())
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": True})
        await app.undo_tidy()
        op2 = await app.steam_ops_claim()
        await app.steam_ops_finish(op2["id"], True, {"readBack": False})
        third = await app.remote_copies_report(_report())
        await app.stop()
        return first, second, third

    first, second, third = asyncio.run(go())
    assert first["tidied"] == 0  # off by default
    assert second["tidied"] == 1  # only the certain entry
    assert third["tidied"] == 0


def test_automatic_tidy_up_never_hides_an_uncertain_entry_and_undo_covers_pending(tmp_path):
    app, _events = _app(tmp_path)
    _verified(app)

    async def go():
        await app.start()
        await app.remote_copies_report(_report())
        queued = await app.tidy_copies([STREAM, PUZZLE, MINE, ODD], automatic=True)
        op = await app.steam_ops_claim()
        undo = await app.undo_tidy()  # the hide has not run yet: Undo still shows it again
        await app.stop()
        return queued, op, undo

    queued, op, undo = asyncio.run(go())
    assert queued == {"queued": 1} and op["payload"] == {"appid": STREAM, "hidden": True}
    assert undo == {"queued": 1}


def test_undo_covers_an_entry_that_came_back(tmp_path):
    app, _events = _app(tmp_path)
    _verified(app)

    async def go():
        await app.start()
        await app.remote_copies_report(_report())
        await app.tidy_copies([STREAM])
        op = await app.steam_ops_claim()
        await app.steam_ops_finish(op["id"], True, {"readBack": True})
        await app.remote_copies_report(_report(hidden={STREAM}))
        await app.remote_copies_report(_report())  # Steam showed it again
        state = (await app.remote_copies_status())["log"][str(STREAM)]["state"]
        undo = await app.undo_tidy()
        await app.stop()
        return state, undo

    assert asyncio.run(go()) == ("came-back", {"queued": 1})


def test_unhide_local_only_for_local_shortcuts(tmp_path):
    app, events = _app(tmp_path)

    async def go():
        await app.start()
        await app.remote_copies_report(_report())
        outcome = await app.remote_copies_report(_report(hidden={MINE}))
        with pytest.raises(ValueError):
            await app.unhide_local(STREAM)
        await app.unhide_local(MINE)
        op = await app.steam_ops_claim()
        await app.stop()
        return outcome, op

    outcome, op = asyncio.run(go())
    assert outcome["newlyHidden"] == [{"appid": MINE, "name": "Mine"}]
    assert any(e == "keepsake_toast" and "Mine was hidden" in str(a) for e, a in events)
    assert op["payload"] == {"appid": MINE, "hidden": False}


def test_device_check(tmp_path):
    app, _events = _app(tmp_path)

    async def go():
        ctx = app._device_context()
        before = await devicechecks.run("remote-shortcuts", ctx)
        await app.remote_copies_report(_report())
        app.game_configs.update(f"shortcut:7:{ODD}", {"enabled": True})  # synced, only unsure from the file
        passed = await devicechecks.run("remote-shortcuts", ctx)
        await app.remote_copies_report(_report(odd="remote"))  # now Steam says it streams
        failed = await devicechecks.run("remote-shortcuts", ctx)
        return before, passed, failed

    before, passed, failed = asyncio.run(go())
    assert before["status"] == "skip"
    assert passed["title"] == "Games you can stream from another device"
    assert passed["status"] == "pass"
    assert passed["details"] == {"local": 1, "remote": 1, "unsure": 1, "hidden": 0, "cameBack": 0, "clashes": 1}
    assert "Also installed here: Mine" in passed["found"] and "Desk" not in passed["found"]
    assert failed["status"] == "fail" and "Steam says stream: Odd Path" in failed["found"]
    bare = asyncio.run(devicechecks.run("remote-shortcuts", devicechecks.Context("", "", "", "", {}, "")))
    assert bare["status"] == "skip"


def test_steam_ops_validates_set_hidden():
    ops = SteamOps(StateDB(":memory:"))
    with pytest.raises(SteamOpsError):
        ops.enqueue("core", "set-hidden", {"appid": 5})
    with pytest.raises(SteamOpsError):
        ops.enqueue("core", "set-hidden", {"appid": 5, "hidden": "yes"})
    assert ops.enqueue("core", "set-hidden", {"appid": 5, "hidden": True}) == 1


def test_a_windows_host_keeps_every_shortcut_local(tmp_path):
    root = tmp_path / "Steam"
    make_fake_steam(tmp_path, users={"7": [shortcut_entry(-1000000003, "Native", GONE)]}, most_recent="7")
    steam = tmp_path / ".local" / "share" / "Steam"
    games = discovery.discover(str(tmp_path), "windows", windows_paths=[str(steam)])["games"]
    assert [(g["name"], g["presence"]) for g in games] == [("Native", "local")]
    assert not root.exists()
