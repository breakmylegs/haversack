"""Hosts and the Windows save layout (ADR-0038). Synthetic games and folders only."""

import os
import sys

import pytest

from keepsake import hosts, resolve

windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows known folders")
RECORD = {"f": [["<winAppData>/ExampleQuest", "s", []]], "i": ["Example Quest"], "s": 1999999101}


def test_host_detection():
    assert hosts.host({"DECKY_PLUGIN_DIR": "/home/deck/homebrew/plugins/Keepsake"}, "linux") == "decky"
    assert hosts.host({}, "linux") == "linux-desktop"
    assert hosts.host({}, "win32") == "windows"
    assert set(hosts.HOSTS) == {"decky", "linux-desktop", "windows"}


def test_every_windows_root_has_a_known_folder():
    assert set(hosts.KNOWN_FOLDERS) == set(resolve.WIN_ROOTS)


@windows
def test_known_folders_on_this_windows_machine_match_windows_own_answers():
    roots = hosts.windows_roots()
    same = os.path.normcase
    assert same(roots["winAppData"]) == same(os.environ["APPDATA"])
    assert same(roots["winLocalAppData"]) == same(os.environ["LOCALAPPDATA"])
    assert same(roots["winPublic"]) == same(os.environ["PUBLIC"])
    assert same(roots["winProgramData"]) == same(os.environ["PROGRAMDATA"])
    assert roots["winLocalAppDataLow"].endswith("LocalLow")
    assert roots["winSavedGames"].endswith("Saved Games")
    assert roots["winDocuments"]  # may sit in OneDrive: never assumed to be %USERPROFILE%\Documents


def test_hosts_says_nothing_about_windows_folders_elsewhere(monkeypatch):
    monkeypatch.setattr(hosts.sys, "platform", "linux")
    assert hosts.known_folder("winAppData") is None and hosts.known_folder("notAFolder") is None


def known(tmp_path):
    return {root: str(tmp_path / "win" / root) for root in resolve.WIN_ROOTS}


def test_windows_layout_maps_every_windows_root(tmp_path):
    game = {"os": "windows", "base_dir": None}
    roots = resolve.logical_roots(game, home=str(tmp_path), known=known(tmp_path))
    assert resolve.platform_of(game) == "windows"
    assert roots["winAppData"] == os.path.realpath(str(tmp_path / "win" / "winAppData"))
    assert roots["home"] is None and roots["xdgData"] is None  # Linux roots do not apply on Windows


def write(path, data=b"save"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def test_a_proton_save_and_a_windows_save_are_the_same_logical_files(tmp_path, monkeypatch):
    prefix = tmp_path / "compatdata" / "3000000001"
    write(str(prefix / "pfx/drive_c/users/steamuser/AppData/Roaming/ExampleQuest/slot1.sav"))
    folders = known(tmp_path)
    write(os.path.join(folders["winAppData"], "examplequest", "SLOT1.sav"))  # Windows ignores case
    monkeypatch.setattr(hosts, "windows_roots", lambda: folders)
    on_proton = resolve.preview({"prefix": str(prefix)}, "Example Quest", RECORD, {}, str(tmp_path), include_files=True)
    on_windows = resolve.preview({"os": "windows"}, "Example Quest", RECORD, {}, str(tmp_path), include_files=True)
    assert on_proton["platform"] == "proton" and on_windows["platform"] == "windows"
    assert on_proton["files"] == {"winAppData": ["ExampleQuest/slot1.sav"]}
    assert [f.casefold() for f in on_windows["files"]["winAppData"]] == ["examplequest/slot1.sav"]


def test_windows_paths_apply_on_windows_and_the_user_name_is_checked():
    assert resolve.applies([["windows", None]], "windows") and not resolve.applies([["linux", None]], "windows")
    path = "<home>/AppData/Roaming/<osUserName>/Example"
    assert resolve.to_logical(path, "windows", [], None, os_user="someone") == [("winAppData", "someone/Example")]
    for unsafe in (None, "", "a/b", ".."):
        with pytest.raises(resolve.SkipPath):
            resolve.to_logical(path, "windows", [], None, os_user=unsafe)
    assert resolve.to_logical(path, "proton", [], None) == [("winAppData", "steamuser/Example")]
