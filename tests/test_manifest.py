import os

import pytest

from keepsake import manifest
from keepsake.net import HttpResponse, NetError

SAMPLE = """---
"Example Quest II: Game of the Year Edition":
  files:
    "<winLocalAppData>/ExampleQuest2/Saves":
      tags:
        - save
    "<winDocuments>/ExampleQuest2/settings.ini":
      tags:
        - config
    "<base>/untagged.txt": {}
  installDir:
    ExampleQuest2: {}
  steam:
    id: 1111
  id:
    steamExtra:
      - 1112
  cloud:
    steam: true
Example Racer:
  files:
    <home>/.config/exampleracer:
      tags:
        - save
        - config
      when:
        - os: linux
  registry:
    HKEY_CURRENT_USER/Software/Example Racer:
      tags:
        - save
  steam:
    id: 2222
No Data Game:
  steam:
    id: 3333
EQ2:
  alias: "Example Quest II: Game of the Year Edition"
Duplicate Name:
  files:
    <base>/a:
      tags:
        - save
"Duplicate-Name":
  files:
    <base>/b:
      tags:
        - save
Broken Entry:
  files: [not, supported]
"""


@pytest.fixture
def index():
    return manifest.build_index(SAMPLE.splitlines(keepends=True), etag='"e1"')


def test_build_index_compacts_and_filters(index):
    quest = index["games"]["Example Quest II: Game of the Year Edition"]
    assert quest["f"] == [
        ["<winLocalAppData>/ExampleQuest2/Saves", "s", []],
        ["<winDocuments>/ExampleQuest2/settings.ini", "c", []],
    ]
    assert quest["s"] == 1111 and quest["se"] == [1112] and quest["i"] == ["ExampleQuest2"] and quest["cs"] is True
    racer = index["games"]["Example Racer"]
    assert racer["f"] == [["<home>/.config/exampleracer", "sc", [["linux", None]]]]
    assert racer["r"][0][0] == "HKEY_CURRENT_USER/Software/Example Racer"
    assert "No Data Game" not in index["games"]
    assert index["steamNoData"] == [3333]
    assert index["aliases"] == {"EQ2": "Example Quest II: Game of the Year Edition"}
    assert index["skipped"] == 1 and index["skippedTitles"] == ["Broken Entry"]
    quest_title = "Example Quest II: Game of the Year Edition"
    assert index["steam"] == {"1111": quest_title, "1112": quest_title, "2222": "Example Racer"}


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("Example Quest II: Game of the Year Edition", "example quest 2"),
        ("EXAMPLE QUEST 2", "example quest 2"),
        ("Example Quest™ II - GOTY", "example quest 2"),
        ("The Witch & The Hunter", "witch and the hunter"),
        ("Pokémon-like Adventure: Definitive Edition", "pokemon like adventure"),
        ("Assassin's Tale Deluxe Edition", "assassins tale"),
        ("I Am Bread", "i am bread"),
    ],
)
def test_normalise_title(raw, normalised):
    assert manifest.normalise_title(raw) == normalised


def test_game_key():
    assert manifest.game_key("Goat Simulator 3") == "goat-simulator-3"
    assert manifest.game_key("Pokémon: Café!") == "pokemon-cafe"
    assert manifest.game_key("!!!") == "game"


def test_match_order(index):
    shortcut = {"kind": "shortcut", "name": "Example Quest 2", "appid": 4171510507}
    assert manifest.match_game(index, shortcut, {})["method"] == "title"
    assert manifest.match_game(index, shortcut, {})["gameKey"] == "example-quest-ii-game-of-the-year-edition"
    steam = {"kind": "steam", "name": "Whatever Steam Calls It", "appid": 1112}
    assert manifest.match_game(index, steam, {})["title"] == "Example Quest II: Game of the Year Edition"
    assert manifest.match_game(index, {"kind": "steam", "name": "x", "appid": 3333}, {})["method"] == "no-save-data"
    manual = manifest.match_game(index, shortcut, {"matchTitle": "Example Racer"})
    assert manual["method"] == "manual" and manual["title"] == "Example Racer"
    stale_manual = manifest.match_game(index, shortcut, {"matchTitle": "Not In Manifest"})
    assert stale_manual["method"] == "title"


def test_alias_and_user_alias(index):
    assert manifest.match_game(index, {"kind": "shortcut", "name": "EQ2"}, {})["title"].startswith("Example Quest")
    user = manifest.match_game(index, {"kind": "shortcut", "name": "My Racer"}, {"aliases": ["Example Racer"]})
    assert user["title"] == "Example Racer"


def test_ambiguous_titles_are_not_guessed(index):
    result = manifest.match_game(index, {"kind": "shortcut", "name": "duplicate name"}, {})
    assert result["method"] == "ambiguous"
    assert result["title"] is None
    assert result["candidates"] == ["Duplicate Name", "Duplicate-Name"]


def test_no_match_offers_candidates(index):
    result = manifest.match_game(index, {"kind": "shortcut", "name": "Racer Example Turbo"}, {})
    assert result["method"] == "none" and "Example Racer" in result["candidates"]
    assert manifest.match_game(None, {"kind": "shortcut", "name": "x"}, {})["method"] == "no-manifest"


def test_search_titles(index):
    assert manifest.search_titles(index, "racer")[0] == "Example Racer"
    assert manifest.search_titles(index, "   ") == []


class FakeDownloader:
    def __init__(self, status=200, body=SAMPLE, etag='"e2"', error=None):
        self.status, self.body, self.etag, self.error = status, body, etag, error
        self.calls = []

    def __call__(self, url, dest, headers=None, max_bytes=None, progress=None):
        self.calls.append((url, dict(headers or {})))
        if self.error:
            raise self.error
        if self.status == 200:
            with open(dest, "w", encoding="utf-8") as handle:
                handle.write(self.body)
            if progress is not None:
                progress(len(self.body) // 2, len(self.body))
                progress(len(self.body), len(self.body))
        return HttpResponse(status=self.status, headers={"etag": self.etag})


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def test_refresh_downloads_indexes_and_cleans_up(tmp_path):
    downloader = FakeDownloader()
    store = manifest.ManifestStore(str(tmp_path), download=downloader, clock=Clock())
    result = store.refresh()
    assert result["ok"] and result["changed"] and result["games"] == 4
    assert downloader.calls[0][0] == manifest.MANIFEST_URL
    assert "refs/heads/data" in manifest.MANIFEST_URL
    assert [p for p in os.listdir(tmp_path) if p.endswith(".yaml")] == []
    assert store.status()["available"] is True


def test_refresh_weekly_with_etag(tmp_path):
    clock = Clock()
    downloader = FakeDownloader()
    store = manifest.ManifestStore(str(tmp_path), download=downloader, clock=clock)
    store.refresh()
    assert store.refresh()["reason"] == "fresh"
    assert len(downloader.calls) == 1
    clock.now += manifest.REFRESH_SECONDS
    downloader.status = 304
    assert store.refresh()["reason"] == "not-modified"
    assert downloader.calls[1][1]["If-None-Match"] == '"e2"'
    assert store.status()["stale"] is False


def test_refresh_failures_keep_old_index(tmp_path):
    store = manifest.ManifestStore(str(tmp_path), download=FakeDownloader(), clock=Clock())
    store.refresh()
    store._download = FakeDownloader(error=NetError("offline"))
    assert store.refresh(force=True)["reason"] == "offline"
    store._download = FakeDownloader(body="---\nBroken:\n  files: [x]\n")
    assert store.refresh(force=True)["reason"] == "empty-index"
    store._download = FakeDownloader(status=500)
    assert store.refresh(force=True)["reason"] == "http-500"
    fresh = manifest.ManifestStore(str(tmp_path))
    assert len(fresh.load()["games"]) == 4


def test_refresh_reports_each_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "PROGRESS_EVERY", 2)
    seen = []
    store = manifest.ManifestStore(str(tmp_path), download=FakeDownloader(), clock=Clock())
    assert store.refresh(True, progress=seen.append)["ok"]
    stages = [s["stage"] for s in seen]
    assert stages[0] == "checking" and stages[-1] == "saving"
    downloading = [s for s in seen if s["stage"] == "downloading"]
    assert downloading[-1]["bytes"] == downloading[-1]["total"] == len(SAMPLE)
    counts = [s["entries"] for s in seen if s["stage"] == "indexing"]
    assert counts and counts == list(range(2, 2 * len(counts) + 1, 2))  # every PROGRESS_EVERY entries
    assert stages.index("downloading") < stages.index("indexing") < stages.index("saving")
    quiet = []
    assert store.refresh(False, progress=quiet.append)["reason"] == "fresh" and quiet == []  # nothing to do


def test_refresh_failure_reports_no_saving(tmp_path):
    seen = []
    store = manifest.ManifestStore(str(tmp_path), download=FakeDownloader(error=NetError("down")), clock=Clock())
    assert store.refresh(True, progress=seen.append)["reason"] == "offline"
    assert [s["stage"] for s in seen] == ["checking"]
