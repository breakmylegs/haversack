import os

import pytest

from helpers import dumps_binary_vdf, shortcut_entry
from keepsake import discovery


def test_unsigned_appid():
    assert discovery.unsigned_appid(-123456789) == 4171510507
    assert discovery.unsigned_appid(4171510507) == 4171510507
    assert discovery.unsigned_appid(-1) == 0xFFFFFFFF
    assert discovery.unsigned_appid(0) == 0


def make_steam(home, libraries_extra=()):
    root = home / ".local" / "share" / "Steam"
    (root / "steamapps").mkdir(parents=True)
    lines = ['"libraryfolders"', "{", f'"0" {{ "path" "{root.as_posix()}" }}']
    for i, lib in enumerate(libraries_extra, start=1):
        (lib / "steamapps").mkdir(parents=True, exist_ok=True)
        lines.append(f'"{i}" {{ "path" "{lib.as_posix()}" }}')
    lines.append("}")
    (root / "steamapps" / "libraryfolders.vdf").write_text("\n".join(lines))
    return root


def test_steam_roots_and_libraries(tmp_path):
    card = tmp_path / "card"
    root = make_steam(tmp_path, [card])
    roots = discovery.steam_roots(str(tmp_path))
    assert roots == [os.path.realpath(root)]
    libs = discovery.library_folders(str(root))
    assert libs == [os.path.realpath(root), os.path.realpath(card)]


def test_library_folders_bad_file_falls_back_to_root(tmp_path):
    root = make_steam(tmp_path)
    (root / "steamapps" / "libraryfolders.vdf").write_text('"libraryfolders" {')
    assert discovery.library_folders(str(root)) == [os.path.realpath(root)]


def test_read_shortcuts_signed_and_unsigned(tmp_path):
    path = tmp_path / "shortcuts.vdf"
    data = {
        "shortcuts": {
            "0": shortcut_entry(-123456789, "Game A", "/x/a.exe", last_play=1700000000),
            "1": shortcut_entry(123456, "Game B", "/x/b.exe"),
            "2": {"AppName": "No id"},
        }
    }
    path.write_bytes(dumps_binary_vdf(data))
    shortcuts = discovery.read_shortcuts(str(path))
    assert [(s.name, s.appid_signed, s.appid_unsigned) for s in shortcuts] == [
        ("Game A", -123456789, 4171510507),
        ("Game B", 123456, 123456),
    ]
    assert shortcuts[0].last_play_time == 1700000000


def test_find_compatdata_prefers_base_library_and_needs_pfx(tmp_path):
    base = tmp_path / "base"
    card = tmp_path / "card"
    (card / "steamapps" / "compatdata" / "42" / "pfx").mkdir(parents=True)
    (base / "steamapps" / "compatdata" / "42").mkdir(parents=True)  # no pfx
    assert discovery.find_compatdata(42, [str(base), str(card)]) == str(card / "steamapps" / "compatdata" / "42")
    (base / "steamapps" / "compatdata" / "42" / "pfx").mkdir()
    assert discovery.find_compatdata(42, [str(base), str(card)]) == str(base / "steamapps" / "compatdata" / "42")
    assert discovery.find_compatdata(7, [str(base)]) is None


def test_steam_user_ids_skip_zero_and_non_digits(tmp_path):
    root = tmp_path / "Steam"
    for name in ("0", "111", "222", "ac"):
        (root / "userdata" / name / "config").mkdir(parents=True)
    assert sorted(discovery.steam_user_ids(str(root))) == ["111", "222"]


@pytest.mark.posix
@pytest.mark.skipif(os.name == "nt", reason="symlinks need POSIX")
def test_var_home_symlink_resolves(tmp_path):
    real = tmp_path / "var" / "home" / "user"
    real.mkdir(parents=True)
    link = tmp_path / "home"
    link.mkdir()
    os.symlink(real, link / "user")
    make_steam(real)
    assert discovery.steam_roots(str(link / "user")) == discovery.steam_roots(str(real))
