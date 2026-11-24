import pytest

from keepsake.gameconfig import GameConfigError, GameConfigStore, validate


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
