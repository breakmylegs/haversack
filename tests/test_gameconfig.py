import asyncio
import os

import pytest

from helpers import make_fake_steam, shortcut_entry
from keepsake.app import KeepsakeApp
from keepsake.gameconfig import GameConfigError, GameConfigStore, custom_path_from_absolute, validate
from keepsake.paths import PluginPaths
from keepsake.safepath import PathEscapeError


def test_validate_defaults_and_cleaning():
    config = validate(
        {"aliases": [" EQ2 ", "EQ2"], "exclusions": ["*.bak"], "customPaths": [{"root": "base", "rel": "/saves/"}]}
    )
    assert config["aliases"] == ["EQ2"]
    assert config["customPaths"] == [{"root": "base", "rel": "saves"}]
    assert config["includeConfig"] is False and config["matchTitle"] is None


@pytest.mark.parametrize(
    "bad",
    [
        {"unknown": 1},
        {"includeConfig": "yes"},
        {"customPaths": [{"root": "nowhere", "rel": "x"}]},
        {"customPaths": [{"root": "base", "rel": "../escape"}]},
        {"customPaths": [{"root": "base", "rel": "C:/x"}]},
        {"exclusions": ["/abs/*"]},
        {"exclusions": ["../*"]},
        {"aliases": ["x"] * 11},
        {"matchTitle": ""},
    ],
)
def test_validate_rejects(bad):
    with pytest.raises(GameConfigError):
        validate(bad)


def test_custom_path_from_absolute_picks_most_specific_root(tmp_path):
    base = tmp_path / "pfx" / "drive_c" / "Games" / "G"
    local = tmp_path / "pfx" / "drive_c" / "users" / "steamuser" / "AppData" / "Local"
    (base / "saves").mkdir(parents=True)
    (local / "G").mkdir(parents=True)
    roots = {"base": str(base), "winLocalAppData": str(local), "winAppData": None}
    assert custom_path_from_absolute(str(base / "saves"), roots) == {"root": "base", "rel": "saves"}
    assert custom_path_from_absolute(str(local / "G"), roots) == {"root": "winLocalAppData", "rel": "G"}
    with pytest.raises(PathEscapeError):
        custom_path_from_absolute(str(tmp_path), roots)
    with pytest.raises(PathEscapeError):
        custom_path_from_absolute(str(base), roots)  # the root itself is not a sub-folder


def test_store_round_trip_and_unreadable(tmp_path):
    store = GameConfigStore(str(tmp_path))
    assert store.get("k")["aliases"] == []
    store.update("k", {"includeConfig": True})
    assert GameConfigStore(str(tmp_path)).get("k")["includeConfig"] is True
    (tmp_path / "games.json").write_text("{broken")
    with pytest.raises(GameConfigError):
        store.update("k", {"includeConfig": False})
    assert (tmp_path / "games.json").read_text() == "{broken"


MANIFEST = """---
Example Quest:
  files:
    "<winLocalAppData>/ExampleQuest/Saves":
      tags:
        - save
  steam:
    id: 1111
"""


def test_app_match_preview_and_custom_path(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    root = make_fake_steam(
        home, users={"7": [shortcut_entry(-123456789, "Example Quest", "/g.exe")]}, prefixes=[(None, 4171510507)]
    )
    prefix = root / "steamapps" / "compatdata" / "4171510507" / "pfx" / "drive_c"
    save = prefix / "users" / "steamuser" / "AppData" / "Local" / "examplequest" / "saves" / "slot1.sav"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"save")
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="0.4.0", home=str(home), auto_refresh_manifest=False
    )
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(MANIFEST)
    app.manifest.import_file(str(manifest_file))
    key = "shortcut:7:4171510507"

    async def run():
        matches = await app.match_games()
        preview = await app.preview_game(key)
        with pytest.raises(ValueError):
            await app.update_game_config(key, {"matchTitle": "Not A Real Title"})
        extra = prefix / "users" / "steamuser" / "Documents" / "Extra"
        extra.mkdir(parents=True)
        (extra / "bonus.sav").write_bytes(b"b")
        await app.add_custom_path(key, str(extra))
        with pytest.raises(PathEscapeError):
            await app.add_custom_path(key, str(tmp_path))
        return matches, preview, await app.preview_game(key)

    matches, preview, after = asyncio.run(run())
    assert matches[0]["method"] == "title" and matches[0]["gameKey"] == "example-quest"
    assert preview["totalFiles"] == 1 and preview["gameKey"] == "example-quest"
    assert preview["entries"][0]["samples"] == ["examplequest/saves/slot1.sav"]
    assert after["totalFiles"] == 2
    assert app.game_configs.get(key)["customPaths"] == [{"root": "winDocuments", "rel": "Extra"}]
    assert os.path.exists(os.path.join(paths.settings_dir, "games.json"))
