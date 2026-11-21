"""Slice 11 through the engine and the app: registry keys, Steam Cloud detection and suspend snapshots."""

import asyncio

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake import steamcloud
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths
from keepsake.store import LocalFolderStore
from sim import GAME, make_pair
from test_app_ux import Device

REG_MANIFEST = """---
Example Quest:
  files:
    "<winLocalAppData>/ExampleQuest":
      tags:
        - save
  registry:
    "HKEY_CURRENT_USER/Software/Example Studio/Example Quest":
      tags:
        - save
"""
HEADER = "WINE REGISTRY Version 2\n;; All keys relative to \\\\User\\\\S-1-5-21-0-0-0-1000\n\n#arch=win64\n"


def reg_device(tmp_path, name, appid, shared, extra):
    device = Device(tmp_path, name, appid, shared)
    manifest = tmp_path / f"{name}-manifest.yaml"
    manifest.write_text(REG_MANIFEST)
    device.app.manifest.import_file(str(manifest))
    device.user_reg = device.saves.parents[5] / "user.reg"
    device.user_reg.write_text(HEADER + extra, encoding="utf-8")
    return device


def test_registry_keys_travel_with_the_save_and_leave_other_keys_alone(tmp_path):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a = reg_device(
        tmp_path,
        "a",
        4171510507,
        shared,
        '\n[Software\\\\Example Studio\\\\Example Quest] 1700000000\n"Volume"=dword:00000050\n'
        '\n[Software\\\\A Only] 1700000000\n"x"="a"\n',
    )
    b = reg_device(tmp_path, "b", 4171510999, shared, '\n[Software\\\\B Only] 1700000000\n"y"="b"\n')

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        await a.app.update_game_config(a.key, {"syncRegistry": True})
        (a.saves / "slot.sav").write_bytes(b"progress")
        pushed = await a.app.sync_push(a.key)
        await b.app.update_game_config(b.key, {"enabled": True})  # picks up syncRegistry from A
        pulled = await b.app.sync_pull(b.key)
        after = await b.app.sync_push(b.key)
        return pushed, pulled, after

    pushed, pulled, after = asyncio.run(go())
    assert pushed["status"] == "published"
    assert b.app.game_configs.get(b.key)["syncRegistry"] is True
    assert pulled["action"] == "restored"
    text = b.user_reg.read_text(encoding="utf-8")
    assert '"Volume"=dword:00000050' in text
    assert '[Software\\\\B Only] 1700000000\n"y"="b"' in text and "A Only" not in text
    assert (b.saves / "slot.sav").read_bytes() == b"progress"
    assert after["status"] == "no-change"  # export after the merge equals the snapshot


def test_registry_stays_out_of_snapshots_unless_the_game_opts_in(tmp_path):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a = reg_device(
        tmp_path, "a", 4171510507, shared, '\n[Software\\\\Example Studio\\\\Example Quest] 1\n"Volume"=dword:1\n'
    )

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"progress")
        await a.app.sync_push(a.key)
        off = await a.app.list_snapshots(a.key)
        a.app.settings.set("registrySync", False)
        await a.app.update_game_config(a.key, {"syncRegistry": True})
        ctx = await a.app._snapshot_context(a.key)
        return off, ctx

    off, ctx = asyncio.run(go())
    assert off["snapshots"][0]["files"] == 1
    assert ctx["registryKeys"] == [] and "registry" not in ctx["files"]  # the global setting wins


def test_a_registry_merge_is_refused_while_the_game_runs(tmp_path, monkeypatch):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a = reg_device(tmp_path, "a", 4171510507, shared, '\n[Software\\\\Example Studio\\\\Example Quest] 1\n"V"="1"\n')
    game = asyncio.run(a.app._game(a.key))
    staging = a.app._registry_dir("example-quest")
    (tmp_path / "frag").write_text("x")
    with open(f"{staging}/user.reg", "w", encoding="utf-8") as handle:
        handle.write('WINE REGISTRY Version 2\n\n[Software\\\\Example Studio\\\\Example Quest]\n"V"="2"\n')
    monkeypatch.setattr("keepsake.app.find_game_processes", lambda *a, **k: [object()])
    with pytest.raises(Exception, match="running"):
        a.app._merge_registry(game, ["software\\example studio\\example quest"], "example-quest")
    assert '"V"="1"' in a.user_reg.read_text(encoding="utf-8")


# Steam Cloud


def test_steam_cloud_states(tmp_path):
    root = tmp_path / "Steam"
    (root / "userdata" / "7" / "10" / "remote").mkdir(parents=True)
    (root / "userdata" / "7" / "10" / "remote" / "save.dat").write_text("x")
    (root / "userdata" / "7" / "20").mkdir(parents=True)
    (root / "userdata" / "7" / "20" / "remotecache.vdf").write_text("x")
    (root / "userdata" / "7" / "30" / "remote").mkdir(parents=True)  # empty: no cloud files
    assert steamcloud.cloud_state(str(root), "7", 10, 1) == "cloud"
    assert steamcloud.cloud_state(str(root), "7", 20, 0) == "cloud"
    assert steamcloud.cloud_state(str(root), "7", 30, 5) == "no-cloud"
    assert steamcloud.cloud_state(str(root), "7", 40, 0) == "unknown"
    assert steamcloud.cloud_state(None, "7", 40, 5) == "unknown"
    assert steamcloud.cloud_state(str(root), "../7", 40, 5) == "unknown"


def test_bulk_enable_turns_on_only_played_steam_games_without_cloud(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    root = make_fake_steam(
        home,
        users={"7": [shortcut_entry(-123456789, "Example Quest", "/g.exe")]},
        apps=[(None, 1000010, "Cloudy Game", "Cloudy"), (None, 1000020, "Local Game", "Local")],
        most_recent="7",
    )
    (root / "userdata" / "7" / "1000010").mkdir(parents=True)
    (root / "userdata" / "7" / "1000010" / "remotecache.vdf").write_text("x")
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="0.11.0", home=str(home), auto_refresh_manifest=False
    )
    manifest = tmp_path / "m.yaml"
    manifest.write_text(
        '---\nCloudy Game:\n  files:\n    "<base>/save":\n      tags:\n        - save\n'
        'Local Game:\n  files:\n    "<base>/save":\n      tags:\n        - save\n'
    )
    app.manifest.import_file(str(manifest))
    app.settings.set("steamAutoSync", False)  # the manual "Sync them all" button (ADR-0063 does it on its own)

    async def go():
        labels = {m["name"]: m["steamCloud"] for m in await app.match_games()}
        result = await app.enable_steam_without_cloud()
        app.settings.set("steamCloudDetection", False)
        hidden = {m["name"]: m["steamCloud"] for m in await app.match_games()}
        return labels, result, hidden

    labels, result, hidden = asyncio.run(go())
    assert labels == {"Example Quest": None, "Cloudy Game": "cloud", "Local Game": "no-cloud"}
    assert result == {"enabled": ["Local Game"]}
    assert app.game_configs.get("steam:1000020")["enabled"] is True
    assert app.game_configs.get("steam:1000010")["enabled"] is False
    assert set(hidden.values()) == {None}
    with pytest.raises(ValueError, match="detection is off"):
        asyncio.run(app.enable_steam_without_cloud())


def _steam_app(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    root = make_fake_steam(
        home,
        users={"7": [shortcut_entry(-123456789, "Example Quest", "/g.exe")]},
        apps=[
            (None, 1000010, "Cloudy Game", "Cloudy"),
            (None, 1000020, "Local Game", "Local"),
            (None, 1000030, "Unknown Game", "Unknown"),
        ],
        most_recent="7",
    )
    (root / "userdata" / "7" / "1000010").mkdir(parents=True)
    (root / "userdata" / "7" / "1000010" / "remotecache.vdf").write_text("x")
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="0.27.0", home=str(home), auto_refresh_manifest=False
    )
    manifest = tmp_path / "m.yaml"
    manifest.write_text(
        '---\nCloudy Game:\n  files:\n    "<base>/save":\n      tags:\n        - save\n'
        'Local Game:\n  files:\n    "<base>/save":\n      tags:\n        - save\n'
    )
    app.manifest.import_file(str(manifest))
    return app


def test_played_steam_games_without_cloud_sync_automatically_once(tmp_path):
    app = _steam_app(tmp_path)
    # A key of its own but no known save locations: nothing Keepsake could sync, so it stays off.
    app.game_configs.update("steam:1000030", {"gameKey": "unknown-game"})
    toasts = []
    app.emit = lambda event, payload=None: _record(toasts, event, payload)

    async def go():
        first = {m["name"]: (m["enabled"], m["enabledSource"]) for m in await app.match_games()}
        await app.update_game_config("steam:1000020", {"enabled": False})  # the user turns it off
        second = {m["name"]: (m["enabled"], m["enabledSource"]) for m in await app.match_games()}
        return first, second

    first, second = asyncio.run(go())
    # Steam Cloud game stays off; the no-manifest game has nothing to sync; the shortcut is not a Steam game.
    assert first["Local Game"] == (True, "auto")
    assert first["Cloudy Game"] == (False, None)
    assert first["Unknown Game"] == (False, None)
    assert first["Example Quest"][0] is False
    assert second["Local Game"] == (False, "user")  # a game the user turned off stays off
    assert [p for e, p in toasts if e == "keepsake_toast" and "Local Game" in str(p)]
    assert len([p for e, p in toasts if e == "keepsake_toast"]) == 1


def test_automatic_steam_sync_has_a_switch_and_needs_saves_and_detection(tmp_path):
    app = _steam_app(tmp_path)
    app.settings.set("steamAutoSync", False)
    assert {m["name"]: m["enabled"] for m in asyncio.run(app.match_games())}["Local Game"] is False
    app.settings.set("steamAutoSync", True)
    app.settings.set("steamCloudDetection", False)
    assert {m["name"]: m["enabled"] for m in asyncio.run(app.match_games())}["Local Game"] is False
    app.settings.set("steamCloudDetection", True)
    asyncio.run(app.set_module_enabled("saves", False))
    assert {m["name"]: m["enabled"] for m in asyncio.run(app.match_games())}["Local Game"] is False
    asyncio.run(app.set_module_enabled("saves", True))
    assert {m["name"]: m["enabled"] for m in asyncio.run(app.match_games())}["Local Game"] is True


async def _record(store, event, payload):
    store.append((event, payload))


# Suspend snapshots


def play(device, changes):
    device.launch()
    device.write(changes)
    return device.exit()


def test_a_suspend_snapshot_is_offered_not_adopted(tmp_path):
    a, b, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    b.launch()
    b.exit()
    a.launch()
    a.write({"s.sav": b"mid-session"})
    snap = a.sync.provisional(a.ctx)
    assert snap["status"] == "published"
    assert a.engine.get_meta(GAME, snap["snapId"])["kind"] == "provisional"
    pulled = b.launch()
    assert pulled["reason"] == "up-to-date"  # not adopted
    assert pulled["suspended"]["snapId"] == snap["snapId"] and pulled["suspended"]["device"] == "aaaaaa"
    assert b.files() == {"s.sav": b"v1"}
    b.exit()
    assert a.exit()["status"] == "published"  # the real exit save from the same session
    later = b.launch()
    assert later["action"] == "restored" and "suspended" not in later  # superseded by the exit save
    assert b.files() == {"s.sav": b"mid-session"}


def test_own_suspend_snapshot_is_not_reported_back(tmp_path):
    a, _, _ = make_pair(tmp_path)
    play(a, {"s.sav": b"v1"})
    a.launch()
    a.write({"s.sav": b"v2"})
    a.sync.provisional(a.ctx)
    assert a.sync.suspended_elsewhere(GAME) is None


def test_on_suspend_respects_its_setting_and_only_snapshots_open_sessions(tmp_path):
    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"v1")
        await a.app.sync_push(a.key)
        a.app.settings.set("suspendSnapshots", True)
        idle = await a.app.on_suspend()  # no session open
        await a.app.sync_pull(a.key)  # launch: a session opens
        a.app.settings.set("suspendSnapshots", False)
        off = await a.app.on_suspend()  # session open, but the setting is off
        a.app.settings.set("suspendSnapshots", True)
        (a.saves / "slot.sav").write_bytes(b"v2")
        started = await a.app.on_suspend()
        results = await asyncio.gather(*a.app._background)
        listing = await a.app.list_snapshots(a.key)
        return off, idle, started, results, listing

    off, idle, started, results, listing = asyncio.run(go())
    assert off == {"started": 0} and idle == {"started": 0} and started == {"started": 1}
    assert results[-1]["status"] == "published"
    assert [s["kind"] for s in listing["snapshots"]] == ["provisional", "auto-exit"]
