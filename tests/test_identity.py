import asyncio

from helpers import make_fake_steam, shortcut_entry
from keepsake import identity, manifest
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths
from keepsake.store import LocalFolderStore

# Hints and fingerprints


def test_local_hints_inside_and_outside_prefix():
    inside = {
        "name": "Example Quest: Deluxe Edition",
        "exe_name": "EQGame.exe",
        "base_dir": "/x/compatdata/5/pfx/drive_c/Games/Example Quest/Binaries/Win64",
    }
    hints = identity.local_hints(inside)
    assert hints == {"exe": "eqgame.exe", "folders": ["example quest"], "name": "example quest"}
    outside = {"name": "Native Game", "exe_name": None, "base_dir": "/run/media/card/Games/native_game/bin"}
    assert identity.local_hints(outside)["folders"] == ["native game"]


def test_save_dirs_are_relative_and_shallow():
    dirs = identity.save_dirs(
        {
            "winLocalAppData": ["EQ/Saves/slot1.sav", "EQ/Saves/deep/x.sav", "EQ/config.ini"],
            "winDocuments": ["My Games/EQ/profile.dat"],
        }
    )
    assert dirs == ["winDocuments/My Games/EQ", "winLocalAppData/EQ", "winLocalAppData/EQ/Saves"]


def test_manifest_index_keeps_launch_exes():
    text = """---
Example Quest:
  files:
    "<winLocalAppData>/EQ":
      tags:
        - save
  installDir:
    Example Quest: {}
  launch:
    "<base>/Binaries/EQGame.exe":
      - when:
          - os: windows
    "<base>/<game>.exe":
      - when:
          - os: windows
"""
    index = manifest.build_index(text.splitlines(keepends=True))
    assert index["games"]["Example Quest"]["x"] == ["eqgame.exe"]
    assert index["schema"] == 2


# Scoring

INDEX = {
    "games": {
        "Example Quest": {"f": [], "i": ["Example Quest"], "x": ["eqgame.exe"]},
        "Other Game": {"f": [], "i": ["Other Game"], "x": ["game.exe"]},
        "Another Game": {"f": [], "i": ["Another"], "x": ["game.exe"]},
    }
}


def test_exe_and_folder_from_manifest_match_automatically():
    hints = {"exe": "eqgame.exe", "folders": ["example quest"], "name": "eq iso rip"}
    ranked = identity.candidates(hints, INDEX, [], None)
    assert ranked[0]["gameKey"] == "example-quest" and ranked[0]["score"] == 6.0
    assert ranked[0]["signals"] == ["exe", "folder"]
    assert identity.automatic_choice(ranked, set())["gameKey"] == "example-quest"


def test_generic_exe_alone_is_only_a_suggestion():
    ranked = identity.candidates({"exe": "game.exe", "folders": [], "name": "whatever"}, INDEX, [], None)
    assert {c["gameKey"] for c in ranked} == {"other-game", "another-game"}
    assert all(c["score"] == 0.5 for c in ranked)
    assert identity.automatic_choice(ranked, set()) is None


def test_close_runner_up_or_taken_key_blocks_automatic_match():
    tie = [{"gameKey": "a", "score": 7.0, "strongSignals": 2}, {"gameKey": "b", "score": 6.0, "strongSignals": 2}]
    assert identity.automatic_choice(tie, set()) is None
    alone = [{"gameKey": "a", "score": 7.0, "strongSignals": 2}]
    assert identity.automatic_choice(alone, set())["gameKey"] == "a"
    assert identity.automatic_choice(alone, {"a"}) is None
    one_signal = [{"gameKey": "a", "score": 7.0, "strongSignals": 1}]
    assert identity.automatic_choice(one_signal, set()) is None


def test_other_device_identity_with_save_folders():
    records = [
        {
            "gameKey": "my-iso-game",
            "deviceId": "dev-a",
            "title": None,
            "exe": "rpg.exe",
            "folders": ["my rpg"],
            "name": "my rpg",
            "saveDirs": ["winLocalAppData/MyRpg/Saves", "winDocuments/My Games/MyRpg"],
        },
        {"gameKey": "mine", "deviceId": "dev-b", "exe": "rpg.exe", "folders": [], "name": "", "saveDirs": []},
    ]
    present = {"winLocalAppData/MyRpg/Saves"}
    ranked = identity.candidates(
        {"exe": "rpg.exe", "folders": [], "name": "rpg from disc"},
        None,
        records,
        present.__contains__,
        exclude_device="dev-b",
    )
    assert [c["gameKey"] for c in ranked] == ["my-iso-game"]  # own record excluded
    assert ranked[0]["signals"] == ["exe", "saves"] and ranked[0]["score"] == 7.0
    assert identity.automatic_choice(ranked, set())["gameKey"] == "my-iso-game"


def test_partial_saves_and_names_score_less():
    records = [
        {
            "gameKey": "k",
            "deviceId": "d",
            "exe": None,
            "folders": [],
            "name": "example quest remake",
            "saveDirs": ["a/1", "a/2", "a/3"],
        }
    ]
    ranked = identity.candidates(
        {"exe": None, "folders": [], "name": "example quest"}, None, records, lambda d: d == "a/1"
    )
    assert ranked[0]["signals"] == ["name-partial", "saves-partial"] and ranked[0]["score"] == 3.0


def test_proposal_for_uncertain_matches():
    ranked = [
        {"gameKey": "a", "score": 4.0, "strongSignals": 1},
        {"gameKey": "b", "score": 3.5, "strongSignals": 1},
        {"gameKey": "c", "score": 1.0, "strongSignals": 0},
    ]
    found = identity.proposal(ranked, set(), set())
    assert found["candidate"]["gameKey"] == "a" and [c["gameKey"] for c in found["alternatives"]] == ["b", "c"]
    assert identity.proposal(ranked, set(), {"a"})["candidate"]["gameKey"] == "b"  # "not this game" remembered
    assert identity.proposal(ranked, {"a", "b"}, set()) is None  # c is too weak to propose
    assert identity.proposal([], set(), set()) is None


def test_ambiguous_manifest_names_are_proposed_not_guessed():
    # Both normalise to "twin game" but have different game keys, so neither can be chosen alone.
    index = {"games": {"Twin Game": {"f": []}, "The Twin Game": {"f": []}}}
    ranked = identity.candidates({"exe": None, "folders": [], "name": "twin game"}, index, [], None)
    assert identity.automatic_choice(ranked, set()) is None
    found = identity.proposal(ranked, set(), set())
    assert found["candidate"]["score"] == 3.0 and len(found["alternatives"]) == 1


def test_identity_records_round_trip_through_a_store(tmp_path):
    store = LocalFolderStore(str(tmp_path))
    record = identity.identity_record(
        "example-quest",
        "dev-a",
        "Example Quest",
        {"exe": "eq.exe", "folders": [], "name": "eq"},
        ["winLocalAppData/EQ"],
        now=1.0,
    )
    assert identity.publish_identity(store, record)
    assert identity.publish_identity(store, record)  # already there is fine
    store.put_new("games/other/identity/junk.json", b"{not json")
    store.put_new("games/other/snapshots/x.json", b"{}")
    assert identity.cloud_identities(store) == [record]


def test_game_key_override_wins_over_the_manifest():
    game = {"kind": "shortcut", "name": "Example Quest"}
    index = manifest.build_index(
        '---\nExample Quest:\n  files:\n    "<base>/s":\n      tags:\n        - save\n'.splitlines(keepends=True)
    )
    assert manifest.match_game(index, game, {"gameKey": "my-key"})["gameKey"] == "my-key"
    assert manifest.match_game(index, game, {"gameKey": "my-key"})["title"] == "Example Quest"
    custom = manifest.match_game(index, {"kind": "shortcut", "name": "Unknown"}, {"gameKey": "unknown"})
    assert custom["method"] == "manual-key" and custom["title"] is None
    assert manifest.match_game(None, game, {"gameKey": "k"})["gameKey"] == "k"


# Two devices through the app


def make_device(tmp_path, name, appid_signed, shortcut_name, exe_folder, shared):
    home = tmp_path / name
    home.mkdir()
    unsigned = appid_signed & 0xFFFFFFFF
    pfx = f"steamapps/compatdata/{unsigned}/pfx/drive_c"
    root = make_fake_steam(home, users={"7": []}, prefixes=[(None, unsigned)])
    exe = root / pfx / "Games" / exe_folder / "RPG.exe"
    exe.parent.mkdir(parents=True)
    from helpers import dumps_binary_vdf

    (root / "userdata/7/config/shortcuts.vdf").write_bytes(
        dumps_binary_vdf({"shortcuts": {"0": shortcut_entry(appid_signed, shortcut_name, str(exe))}})
    )
    saves = root / pfx / "users/steamuser/AppData/Local/MyRpg/Saves"
    saves.mkdir(parents=True)
    paths = PluginPaths(*(str(home / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(home / "proc"), version="0.9.0", home=str(home), auto_refresh_manifest=False)
    app._store = lambda: shared  # both devices share one cloud
    app.manifest._cache = {"schema": 2, "games": {}, "titles": {}, "steam": {}, "steamNoData": [], "aliases": {}}
    return app, f"shortcut:7:{unsigned}", saves, root / pfx / "users/steamuser/AppData/Local"


def test_same_game_with_different_names_and_prefixes_is_matched_across_devices(tmp_path):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a, key_a, saves_a, local_a = make_device(tmp_path, "deva", -100000001, "My RPG", "My RPG", shared)
    b, key_b, saves_b, _ = make_device(tmp_path, "devb", -200000002, "RPG (disc 1)", "MyRPG Install", shared)
    assert key_a != key_b  # different compatdata numbers

    async def device_a():
        (saves_a / "slot1.sav").write_bytes(b"level 9")
        await a.add_custom_path(key_a, str(local_a / "MyRpg"))
        await a.new_game_key(key_a)
        await a.update_game_config(key_a, {"enabled": True})
        return await a.sync_push(key_a)

    pushed = asyncio.run(device_a())
    assert pushed["status"] == "published"
    assert any("/identity/" in o.key for o in shared.list("games/my-rpg/"))

    async def device_b():
        await b.add_custom_path(key_b, str(saves_b.parent))
        matches = await b.match_games()
        return matches, await b.get_game(key_b)

    matches, detail = asyncio.run(device_b())
    match_b = next(m for m in matches if m["key"] == key_b)
    assert match_b["gameKey"] == "my-rpg"  # matched by exe and save folders, not by name
    assert detail["config"]["gameKeySource"] == "auto"
    assert detail["suggestions"][0]["signals"] == ["exe", "saves"]
    assert asyncio.run(b.sync_pull(key_b))["action"] == "restored"
    assert (saves_b / "slot1.sav").read_bytes() == b"level 9"


def test_no_automatic_match_when_evidence_is_weak(tmp_path):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a, key_a, saves_a, local_a = make_device(tmp_path, "deva", -100000001, "My RPG", "My RPG", shared)
    b, _, _, _ = make_device(tmp_path, "devb", -200000002, "Something Else", "Other", shared)

    async def run():
        (saves_a / "slot1.sav").write_bytes(b"x")
        await a.add_custom_path(key_a, str(local_a / "MyRpg"))
        await a.new_game_key(key_a)
        await a.sync_push(key_a)
        # B has the save folder but a different exe name and name: one signal only.
        b_game = (await b.discover_games())["games"][0]
        b_game["exe_name"] = "other.exe"
        return await b.identity_candidates(b_game, None)

    ranked = asyncio.run(run())
    assert identity.automatic_choice(ranked, set()) is None
    assert ranked and ranked[0]["gameKey"] == "my-rpg"  # still offered as a suggestion


def test_uncertain_match_asks_for_approval_and_remembers_a_no(tmp_path):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a, key_a, saves_a, local_a = make_device(tmp_path, "deva", -100000001, "My RPG", "My RPG", shared)
    b, key_b, _, _ = make_device(tmp_path, "devb", -200000002, "Disc Game", "Install", shared)
    events = []

    async def emit(event, *args):
        events.append((event, args))

    b.emit = emit

    async def run():
        (saves_a / "slot1.sav").write_bytes(b"x")
        await a.add_custom_path(key_a, str(local_a / "MyRpg"))
        await a.new_game_key(key_a)
        await a.sync_push(key_a)
        # B's shortcut has another exe name: only the save folders match, so it is not certain.
        import keepsake.identity as ident

        real_hints = ident.local_hints
        ident.local_hints = lambda game: {**real_hints(game), "exe": "different.exe"}
        try:
            first = await b.match_games()
            second = await b.match_games()  # same proposal: no second toast
            detail = await b.get_game(key_b)
            await b.approve_match(key_b)
            approved = b.game_configs.get(key_b)
            await b.set_game_key(key_b, None)
            third = await b.match_games()  # proposed again after clearing
            await b.reject_match(key_b)
            fourth = await b.match_games()  # "not this game" is remembered
        finally:
            ident.local_hints = real_hints
        return first, second, detail, approved, third, fourth

    first, second, detail, approved, third, fourth = asyncio.run(run())
    row = next(m for m in first if m["key"] == key_b)
    assert row["gameKey"] is None and row["proposal"]["candidate"]["gameKey"] == "my-rpg"
    assert next(m for m in second if m["key"] == key_b)["proposal"] == row["proposal"]  # stays until decided
    assert detail["proposal"]["candidate"]["signals"] == ["saves"]
    toasts = [e for e in events if "looks like" in str(e)]
    assert len(toasts) == 2  # once at first, once after the key was cleared and it was proposed again
    assert approved["gameKey"] == "my-rpg" and approved["gameKeySource"] == "user"
    assert next(m for m in third if m["key"] == key_b)["proposal"] is not None
    assert next(m for m in fourth if m["key"] == key_b)["proposal"] is None
