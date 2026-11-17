"""Steam for Windows discovery (ADR-0038, P1). Synthetic Steam folders and app IDs only."""

import os
import sys

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake import discovery, hosts, resolve

APPID = 1999999101


def windows_steam(tmp_path):
    """A Steam for Windows install: the same files, found through the registry path instead of the home folder."""
    return make_fake_steam(
        tmp_path / "pc",
        users={"7": [shortcut_entry(-123456789, "Example Quest", "C:/Games/Quest/Quest.exe", "C:/Games/Quest")]},
        apps=[(None, APPID, "Synthetic Steam Game", "SyntheticGame")],
        # Stray compatdata folders (for the game and the shortcut) must not become prefixes on Windows.
        prefixes=[(None, APPID), (None, 4171510507)],
        most_recent="7",
    )


def same(path):
    return os.path.normcase(os.path.realpath(path))


def test_windows_roots_come_from_steam_for_windows_not_the_home_folder(tmp_path):
    root = windows_steam(tmp_path)
    nothing = tmp_path / "empty"
    nothing.mkdir()
    found = discovery.steam_roots(str(tmp_path / "pc"), "windows", [str(nothing), str(root), str(root)])
    assert [same(p) for p in found] == [same(root)]
    assert discovery.steam_roots(str(tmp_path / "pc"), "windows", []) == []  # the home folder is not searched


def test_windows_games_are_native_with_no_prefix_and_the_windows_save_layout(tmp_path, monkeypatch):
    root = windows_steam(tmp_path)
    games = {g["kind"]: g for g in discovery.discover(str(tmp_path / "pc"), "windows", [str(root)])["games"]}
    steam, shortcut = games["steam"], games["shortcut"]
    assert steam["os"] == shortcut["os"] == "windows"
    assert steam["prefix"] is None and shortcut["prefix"] is None
    assert "no-prefix" not in shortcut["notes"]  # expected on Windows, so not a problem
    assert steam["base_dir"].replace("\\", "/").endswith("steamapps/common/SyntheticGame")
    assert resolve.platform_of(steam) == "windows"
    folders = {r: str(tmp_path / "win" / r) for r in resolve.WIN_ROOTS}
    monkeypatch.setattr(hosts, "windows_roots", lambda: folders)
    roots = resolve.logical_roots(steam, home=str(tmp_path / "pc"))
    assert roots["winAppData"] == os.path.realpath(folders["winAppData"])


def test_decky_keeps_the_linux_layout_on_any_machine(tmp_path):
    windows_steam(tmp_path)
    games = discovery.discover(str(tmp_path / "pc"))["games"]  # default host: decky
    steam = next(g for g in games if g["kind"] == "steam")
    assert steam["os"] == "linux" and steam["prefix"] is not None and resolve.platform_of(steam) == "proton"


def test_windows_library_paths_with_escaped_backslashes(tmp_path):
    root = windows_steam(tmp_path)
    library = tmp_path / "D-drive" / "SteamLibrary"
    (library / "steamapps").mkdir(parents=True)

    def escaped(path):  # how Steam for Windows writes paths in libraryfolders.vdf: "C:\\Program Files..."
        return str(path).replace("\\", "\\\\")

    (root / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n"0" {{ "path" "{escaped(root)}" }}\n"1" {{ "path" "{escaped(library)}" }}\n}}\n'
    )
    assert same(library) in [same(p) for p in discovery.library_folders(str(root))]


def test_fallback_folders_come_from_the_environment():
    paths = discovery.windows_steam_paths({"ProgramFiles(x86)": "X:/PF86", "ProgramFiles": "X:/PF"})
    assert paths[-2:] == [os.path.join("X:/PF86", "Steam"), os.path.join("X:/PF", "Steam")]


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows registry")
def test_reading_the_real_registry_never_fails():
    assert all(isinstance(p, str) and p for p in discovery.windows_steam_paths({}))
