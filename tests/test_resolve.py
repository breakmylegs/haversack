import os

import pytest

from keepsake import resolve
from keepsake.resolve import SkipPath, to_logical

NAMES = ["ExampleGame", "Example Game"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("<winLocalAppData>/Example/Saves", [("winLocalAppData", "Example/Saves")]),
        ("<winAppData>\\Example\\*.sav", [("winAppData", "Example/*.sav")]),
        ("<home>/Saved Games/Example", [("winSavedGames", "Example")]),
        ("<home>/AppData/LocalLow/Dev/Example", [("winLocalAppDataLow", "Dev/Example")]),
        ("<home>/Documents/My Games/Example", [("winDocuments", "My Games/Example")]),
        ("<winDocuments>/<game>/save", [("winDocuments", "ExampleGame/save"), ("winDocuments", "Example Game/save")]),
        ("<base>/saves", [("base", "saves")]),
        ("<root>/<game>/saves", [("base", "saves")]),
        ("<root>/userdata/<storeUserId>/<storeGameId>/remote", [("steamUserdata", "620/remote")]),
        ("<winPublic>/Documents/Example", [("winPublic", "Documents/Example")]),
        ("<winProgramData>/Example", [("winProgramData", "Example")]),
        ("<winDocuments>/<osUserName>/x", [("winDocuments", "steamuser/x")]),
        ("<base>", [("base", "")]),
        ("<winAppData>/Dev/Game/<storeUserId>/save", [("winAppData", "Dev/Game/*/save")]),
        ("<winLocalAppData>Low/Dev/Game", [("winLocalAppDataLow", "Dev/Game")]),
    ],
)
def test_proton_mapping(path, expected):
    assert to_logical(path, "proton", NAMES, 620) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("<home>/.local/share/example", [("home", ".local/share/example")]),
        ("<xdgConfig>/example", [("xdgConfig", "example")]),
        ("<xdgData>/example/saves", [("xdgData", "example/saves")]),
        ("<base>/saves", [("base", "saves")]),
    ],
)
def test_native_mapping(path, expected):
    assert to_logical(path, "native", NAMES, None) == expected


@pytest.mark.parametrize(
    ("path", "platform", "reason"),
    [
        ("<winDir>/x", "proton", "unsupported root"),
        ("<home>/Pictures/x", "proton", "unsupported root"),  # <home> alone has no Windows root
        ("<winAppData>/<unknownThing>/x", "proton", "unknown placeholder"),
        ("<winAppData>/../../etc", "proton", "relative path segment"),
        ("<base>/./x", "proton", "relative path segment"),
        ("<winAppData>/C:/x", "proton", "drive letter"),
        ("C:/Games/Example", "proton", "absolute or unknown path"),
        ("/etc/passwd", "native", "absolute or unknown path"),
        ("<osUserName>/x", "native", "unsupported root"),
        ("<home>/<osUserName>/x", "native", "needs the OS user name"),
        ("<base>/<storeGameId>", "proton", "needs a store game id"),
        ("<winAppData>/Example", "native", "unsupported root"),
        ("<winAppData>/save_<storeUserId>.dat", "proton", "store user id inside a name"),
        ("<xdgData>/example", "proton", "unsupported root"),
    ],
)
def test_unknown_or_unsafe_paths_are_skipped(path, platform, reason):
    with pytest.raises(SkipPath, match=reason):
        to_logical(path, platform, NAMES, None)


def test_game_placeholder_without_names():
    with pytest.raises(SkipPath, match="game folder"):
        to_logical("<winDocuments>/<game>", "proton", [], None)


def test_applies():
    assert resolve.applies([], "proton")
    assert resolve.applies([["windows", "steam"]], "proton")  # store ignored
    assert not resolve.applies([["linux", None]], "proton")
    assert resolve.applies([["linux", None]], "native")
    assert resolve.applies([[None, "gog"]], "native")
    assert not resolve.applies([["mac", None]], "native")


def proton_game(tmp_path):
    prefix = tmp_path / "compatdata" / "777"
    (prefix / "pfx" / "drive_c" / "users" / "steamuser" / "AppData" / "Local").mkdir(parents=True)
    return {
        "key": "shortcut:1:777",
        "kind": "shortcut",
        "name": "Example Game",
        "prefix": str(prefix),
        "base_dir": str(prefix / "pfx" / "drive_c" / "Games" / "Example"),
        "steam_root": str(tmp_path / "Steam"),
        "user_id": "1",
    }


def test_logical_roots_proton_and_native(tmp_path):
    game = proton_game(tmp_path)
    roots = resolve.logical_roots(game)
    local = os.path.join(game["prefix"], "pfx", "drive_c", "users", "steamuser", "AppData", "Local")
    assert roots["winLocalAppData"] == local
    assert roots["winSavedGames"].endswith(os.path.join("steamuser", "Saved Games"))
    assert roots["winPublic"].endswith(os.path.join("users", "Public"))
    assert roots["home"] is None
    assert roots["steamUserdata"] == os.path.join(str(tmp_path / "Steam"), "userdata", "1")
    native = resolve.logical_roots(
        {"prefix": None, "base_dir": "/opt/g"}, home=str(tmp_path), env={"XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    )
    assert native["home"] == os.path.realpath(tmp_path)
    assert native["xdgConfig"] == os.path.realpath(tmp_path / "cfg")
    assert native["xdgData"] == os.path.realpath(tmp_path / ".local" / "share")
    assert native["winAppData"] is None and native["steamUserdata"] is None


def test_too_broad_base_is_refused(tmp_path):
    game = proton_game(tmp_path)
    home = str(tmp_path / "home")
    os.makedirs(home)
    drive_c = os.path.join(game["prefix"], "pfx", "drive_c")
    good = os.path.join(drive_c, "Games", "Example")
    assert resolve.safe_base(good, game, home)
    for broad in (os.path.abspath(os.sep), home, str(tmp_path), drive_c, game["steam_root"], os.path.dirname(drive_c)):
        assert not resolve.safe_base(broad, game, home), broad
    assert resolve.logical_roots({**game, "base_dir": os.path.abspath(os.sep)}, home=home)["base"] is None
    assert resolve.logical_roots({**game, "base_dir": good}, home=home)["base"] == good


def write(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_scan_case_insensitive_in_prefix_and_exclusions(tmp_path):
    root = tmp_path / "root"
    write(root / "MyGame" / "Saves" / "slot0.sav", b"12345")
    write(root / "MyGame" / "Saves" / "debug.log")
    write(root / "MyGame" / "Saves" / "Logs" / "today.txt")
    write(root / "MyGame" / "Saves" / "ShaderCache" / "blob.bin")
    write(root / "MyGame" / "Saves" / "keep" / "notes.txt")
    result = resolve.ScanResult()
    excluded = resolve.scan(str(root), "mygame/SAVES", True, ["*/keep/*"], result)
    assert result.files == {"MyGame/Saves/slot0.sav": 5}
    assert excluded == 4
    sensitive = resolve.ScanResult()
    resolve.scan(str(root), "mygame/SAVES", False, [], sensitive)
    assert sensitive.files == {}


def test_scan_globs_and_double_star(tmp_path):
    root = tmp_path / "root"
    write(root / "A" / "one.sav")
    write(root / "A" / "deep" / "er" / "two.sav")
    write(root / "A" / "other.cfg")
    result = resolve.ScanResult()
    resolve.scan(str(root), "A/*.sav", False, [], result)
    assert set(result.files) == {"A/one.sav"}
    result = resolve.ScanResult()
    resolve.scan(str(root), "A/**/two.sav", False, [], result)
    assert set(result.files) == {"A/deep/er/two.sav"}


def test_scan_missing_root_and_no_matches(tmp_path):
    result = resolve.ScanResult()
    assert resolve.scan(str(tmp_path / "missing"), "x", True, [], result) == 0
    assert result.files == {}


def test_scan_truncates(tmp_path, monkeypatch):
    monkeypatch.setattr(resolve, "MAX_FILES", 3)
    root = tmp_path / "root"
    for i in range(5):
        write(root / "S" / f"{i}.sav")
    result = resolve.ScanResult()
    resolve.scan(str(root), "S", False, [], result)
    assert len(result.files) == 3 and result.truncated


@pytest.mark.posix
@pytest.mark.skipif(os.name == "nt", reason="symlinks need POSIX")
def test_symlinks_escaping_the_root_are_rejected(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    write(outside / "secret.txt")
    write(root / "Game" / "ok.sav")
    os.symlink(outside, root / "Game" / "linkdir")
    os.symlink(outside / "secret.txt", root / "Game" / "linkfile.sav")
    os.symlink(outside, root / "Escape")
    result = resolve.ScanResult()
    resolve.scan(str(root), "Game", False, [], result)
    assert set(result.files) == {"Game/ok.sav"}
    assert "Game/linkdir" in result.escaped and "Game/linkfile.sav" in result.escaped
    result = resolve.ScanResult()
    resolve.scan(str(root), "Escape/secret.txt", False, [], result)
    assert result.files == {} and result.escaped == ["Escape/secret.txt"]


RECORD = {
    "f": [
        ["<winLocalAppData>/Example/Saves", "s", []],
        ["<winLocalAppData>/Example/Config", "c", []],
        ["<winDir>/example.ini", "s", []],
        ["<home>/.example", "s", [["linux", None]]],
        ["<winAppData>/<game>/profile", "s", []],
    ],
    "i": ["ExampleGame"],
    "s": 620,
}


def test_preview_end_to_end(tmp_path):
    game = proton_game(tmp_path)
    local = tmp_path / "compatdata/777/pfx/drive_c/users/steamuser/AppData/Local"
    roaming = tmp_path / "compatdata/777/pfx/drive_c/users/steamuser/AppData/Roaming"
    write(local / "example" / "saves" / "slot.sav", b"abc")
    write(local / "Example" / "Config" / "gfx.ini")
    write(roaming / "examplegame" / "profile" / "p.dat", b"zz")
    base = tmp_path / "compatdata/777/pfx/drive_c/Games/Example"
    write(base / "extra" / "custom.sav")

    result = resolve.preview(game, "Example Game", RECORD, {"customPaths": [{"root": "base", "rel": "extra"}]})
    assert result["platform"] == "proton"
    assert result["totalFiles"] == 3
    by_path = {e["path"]: e for e in result["entries"]}
    assert by_path["<winLocalAppData>/Example/Saves"]["samples"] == ["example/saves/slot.sav"]
    # <game> expands to each installDir name and the title: one entry per variant.
    profile = [e for e in result["entries"] if e["path"] == "<winAppData>/<game>/profile"]
    assert [e["pattern"] for e in profile] == ["ExampleGame/profile", "Example Game/profile"]
    assert sum(e["files"] for e in profile) == 1
    assert by_path["<base>/extra"]["source"] == "custom"
    reasons = {s["path"]: s["reason"] for s in result["skipped"]}
    assert reasons["<winLocalAppData>/Example/Config"] == "config files are off for this game"
    assert reasons["<winDir>/example.ini"].startswith("unsupported root")
    assert reasons["<home>/.example"] == "for another operating system"

    with_config = resolve.preview(game, "Example Game", RECORD, {"includeConfig": True})
    assert with_config["totalFiles"] == 3  # slot.sav, gfx.ini, p.dat


def test_preview_without_match(tmp_path):
    result = resolve.preview(proton_game(tmp_path), None, None, {})
    assert result["totalFiles"] == 0 and "no manifest match" in result["warnings"]
