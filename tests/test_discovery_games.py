import os

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake import discovery

# Synthetic IDs only (principle 12).
SIGNED = -123456789  # unsigned 4171510507
UNSIGNED = 4171510507
OTHER = 3000000001  # stored unsigned-looking but beyond int32: written signed by the fixture


def build(tmp_path):
    card = tmp_path / "card"
    root = make_fake_steam(
        tmp_path,
        users={
            "111": [
                shortcut_entry(SIGNED, "Example Quest", str(card / "steamapps/compatdata/4171510507/pfx/drive_c/Game/game.exe")),
                shortcut_entry(123456, "No Prefix Game", "/opt/game/run.sh", start_dir="/opt/game"),
            ],
            "222": [shortcut_entry(OTHER, "Other User Game", "/x/y.exe")],
            "333": None,  # user with no shortcuts file
        },
        most_recent="222",
        extra_libraries=[card],
        apps=[
            (None, 620, "Example Puzzle", "ExamplePuzzle"),
            (card, 1493710, "Proton Experimental", "Proton - Experimental"),
            (None, 228980, "Steamworks Common Redistributables", "Steamworks Shared"),
            (card, 4000, "Card Game", "CardGame"),
        ],
        prefixes=[(card, UNSIGNED), (card, 4000), (None, OTHER)],
    )
    return root, card


def by_name(result):
    return {g["name"]: g for g in result["games"]}


def test_default_user_from_loginusers(tmp_path):
    root, _ = build(tmp_path)
    assert discovery.default_user_id(str(root)) == "222"


def test_default_user_falls_back_without_loginusers(tmp_path):
    root, _ = build(tmp_path)
    os.remove(root / "config" / "loginusers.vdf")
    assert discovery.default_user_id(str(root)) in {"111", "222", "333"}


def test_default_user_ignores_users_without_userdata(tmp_path):
    root, _ = build(tmp_path)
    (root / "config" / "loginusers.vdf").write_text(
        '"users" { "76561197960266728" { "MostRecent" "1" } }'  # id3 1000, no userdata folder
    )
    assert discovery.default_user_id(str(root)) != "1000"


def test_discover_shortcuts_all_users_default_first(tmp_path):
    build(tmp_path)
    result = discovery.discover(str(tmp_path))
    shortcuts = [g for g in result["games"] if g["kind"] == "shortcut"]
    assert shortcuts[0]["name"] == "Other User Game"
    assert shortcuts[0]["is_default_user"] is True
    assert {g["user_id"] for g in shortcuts} == {"111", "222"}
    assert all(g["appid"] >= 0 for g in shortcuts)


def test_signed_id_maps_to_unsigned_prefix_on_card(tmp_path):
    _, card = build(tmp_path)
    game = by_name(discovery.discover(str(tmp_path)))["Example Quest"]
    assert game["appid"] == UNSIGNED
    assert game["key"] == f"shortcut:111:{UNSIGNED}"
    assert game["prefix"] == os.path.realpath(card / "steamapps" / "compatdata" / str(UNSIGNED))
    assert game["prefix_library_index"] == 1
    assert game["exe_inside_prefix"] is True
    assert game["base_dir"] == os.path.realpath(card / "steamapps/compatdata/4171510507/pfx/drive_c/Game")


def test_large_appid_written_signed_is_read_unsigned(tmp_path):
    root, _ = build(tmp_path)
    game = by_name(discovery.discover(str(tmp_path)))["Other User Game"]
    assert game["appid"] == OTHER
    assert game["prefix"] == os.path.realpath(root / "steamapps" / "compatdata" / str(OTHER))
    assert game["prefix_library_index"] == 0


def test_missing_prefix_is_flagged_and_start_dir_is_base(tmp_path):
    build(tmp_path)
    game = by_name(discovery.discover(str(tmp_path)))["No Prefix Game"]
    assert game["prefix"] is None
    assert game["notes"] == ["no-prefix"]
    assert game["base_dir"] == os.path.realpath("/opt/game")


def test_steam_apps_classified_and_tools_skipped(tmp_path):
    root, card = build(tmp_path)
    games = by_name(discovery.discover(str(tmp_path)))
    assert "Proton Experimental" not in games
    assert "Steamworks Common Redistributables" not in games
    puzzle = games["Example Puzzle"]
    assert puzzle["kind"] == "steam" and puzzle["key"] == "steam:620"
    assert puzzle["prefix"] is None  # native game
    assert puzzle["base_dir"] == os.path.join(os.path.realpath(root), "steamapps", "common", "ExamplePuzzle")
    card_game = games["Card Game"]
    assert card_game["prefix_library_index"] == 1
    assert card_game["last_played"] == 1700000000


def test_corrupt_shortcuts_file_reported_not_fatal(tmp_path):
    root, _ = build(tmp_path)
    (root / "userdata" / "111" / "config" / "shortcuts.vdf").write_bytes(b"\x00shortcuts\x00\x09bad")
    games = discovery.discover(str(tmp_path))["games"]
    assert any(g["notes"] == ["shortcuts-unreadable"] and g["user_id"] == "111" for g in games)
    assert any(g["name"] == "Other User Game" for g in games)


def test_bad_app_manifest_skipped(tmp_path):
    root, _ = build(tmp_path)
    (root / "steamapps" / "appmanifest_999.acf").write_text('"AppState" { "appid" ')
    (root / "steamapps" / "appmanifest_998.acf").write_text('"AppState" { "appid" "notanumber" }')
    names = set(by_name(discovery.discover(str(tmp_path))))
    assert "Example Puzzle" in names


def test_no_steam_at_all(tmp_path):
    assert discovery.discover(str(tmp_path)) == {"roots": [], "games": []}


def test_results_carry_no_account_names(tmp_path):
    build(tmp_path)
    text = repr(discovery.discover(str(tmp_path)))
    assert "acct" not in text


def test_cross_check():
    assert discovery.cross_check("/a/compatdata/1", [])["status"] == "unknown"
    assert discovery.cross_check("/a/compatdata/1", ["/a/compatdata/1/", "/a/compatdata/1"])["status"] == "match"
    mismatch = discovery.cross_check("/a/compatdata/1", ["/b/compatdata/2"])
    assert mismatch["status"] == "mismatch" and mismatch["reason"] == "different-prefix"
    mixed = discovery.cross_check("/a/compatdata/1", ["/a/compatdata/1", "/b/compatdata/2"])
    assert mixed["status"] == "mismatch"
    assert discovery.cross_check(None, ["/a"])["reason"] == "no-discovered-prefix"


def test_mismatch_recorded_blocks_until_match(tmp_path):
    rt = str(tmp_path)
    key = "shortcut:111:1"
    assert discovery.sync_blocked(rt, key) is False
    discovery.record_cross_check(rt, key, {"status": "mismatch", "observed": ["/b"], "reason": "x"}, "/a")
    assert discovery.sync_blocked(rt, key) is True
    discovery.record_cross_check(rt, key, {"status": "unknown", "observed": []}, "/a")
    assert discovery.sync_blocked(rt, key) is True
    discovery.record_cross_check(rt, key, {"status": "match", "observed": ["/a"]}, "/a")
    assert discovery.sync_blocked(rt, key) is False


def test_unreadable_mismatch_file_blocks_everything_and_is_kept(tmp_path):
    path = tmp_path / discovery.MISMATCH_FILE
    path.write_text("{broken")
    assert discovery.sync_blocked(str(tmp_path), "any") is True
    discovery.record_cross_check(str(tmp_path), "any", {"status": "match", "observed": ["/a"]}, "/a")
    assert path.read_text() == "{broken"


@pytest.mark.posix
@pytest.mark.skipif(os.name == "nt", reason="symlinks need POSIX")
def test_var_home_symlink_gives_same_prefixes(tmp_path):
    real = tmp_path / "var" / "home" / "user"
    real.mkdir(parents=True)
    (tmp_path / "home").mkdir()
    os.symlink(real, tmp_path / "home" / "user")
    make_fake_steam(real, users={"5": [shortcut_entry(SIGNED, "G", "/g.exe")]}, prefixes=[(None, UNSIGNED)])
    via_link = discovery.discover(str(tmp_path / "home" / "user"))["games"][0]["prefix"]
    via_real = discovery.discover(str(real))["games"][0]["prefix"]
    assert via_link == via_real and via_link is not None
