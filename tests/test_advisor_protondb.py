"""Keepsake's ProtonDB index (ADR-0035): building it, downloading it and using it in Advisor. Synthetic data only."""

import gzip
import importlib.util
import io
import json
import os
import pathlib
import random
import tarfile

import pytest

from keepsake.advisor import protondb
from test_advisor import make_advisor

SPEC = importlib.util.spec_from_file_location(
    "protondb_index", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "protondb_index.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

STEAM_GAME = 1999999101  # synthetic, matches test_advisor's Games()


def rec(
    appid,
    cpu,
    verdict="yes",
    t=1790000000,
    notes="Runs well",
    launch=None,
    proton="GE-Proton9-20",
    title="Example Quest",
):
    return {
        "app": {"steam": {"appId": str(appid)}, "title": title},
        "timestamp": t,
        "systemInfo": {"cpu": cpu, "gpu": "", "os": "SteamOS Holo"},
        "responses": {
            "type": "steamPlay",
            "verdict": verdict,
            "variant": "ge",
            "customProtonVersion": proton,
            "launchOptions": launch,
            "notes": {"verdict": notes},
        },
    }


def make_dump(tmp_path, records, name="reports_oct1_2026.tar.gz"):
    data = json.dumps(records, ensure_ascii=False).encode("utf-8")
    path = tmp_path / name
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo(builder.MEMBER)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return str(path)


def built_index(tmp_path):
    records = [
        rec(STEAM_GAME, "AMD Ryzen Z1 Extreme", notes="Smooth at /home/someone/Games, see https://example.com/x"),
        rec(STEAM_GAME, "AMD Ryzen Z2 Extreme", t=1795000000, launch="~/lsfg %command%"),
        rec(STEAM_GAME, "Intel Core i9 desktop", verdict="no"),  # counted, not kept as a handheld report
        rec(1999999102, "AMD Custom APU 0405", verdict="no", notes="Crashes", proton="Proton 9.0"),
        rec(1999999103, "Intel desktop"),  # no handheld report: left out
        {"app": {"steam": {"appId": "not-a-number"}}},
    ]
    return builder.build(make_dump(tmp_path, records), str(tmp_path / "out"))


def test_build_keeps_handheld_reports_and_strips_paths_and_links(tmp_path):
    path = built_index(tmp_path)
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        lines = handle.read().splitlines()
    assert header["schema"] == 1 and header["dump"] == "oct1_2026" and header["apps"] == 2
    assert "ODbL" in header["licence"] and header["attribution"] == protondb.ATTRIBUTION
    assert [line.split("\t")[0] for line in lines] == [str(STEAM_GAME), "1999999102"]
    entry = json.loads(lines[0].split("\t", 1)[1])
    assert (entry["n"], entry["works"], entry["handheld"]) == (3, 2, 2)
    assert [r["apu"] for r in entry["reports"]] == ["AMD Ryzen Z2 Extreme", "AMD Ryzen Z1 Extreme"]  # newest first
    assert entry["reports"][1]["notes"] == "Smooth at ~/Games, see [link]"


def test_report_text_loses_user_names_in_paths():
    clean = builder._text
    assert clean("game at /run/media/someone/CARD/Games now") == "game at /run/media/.../Games now"
    assert (
        clean("prefix C:\\Users\\someone\\AppData and c:/users/other/x")
        == "prefix C:/Users/...\\AppData and c:/Users/.../x"
    )
    assert clean("/var/home/someone/x and /home/b/y") == "~/x and ~/y"


def test_the_stream_reader_handles_small_chunks_and_split_characters():
    text = json.dumps([{"a": "é" * 50}, {"b": [1, 2, {"c": "ü"}]}, {"d": 3}], ensure_ascii=False)
    assert list(builder.records(io.StringIO(text), chunk=7)) == json.loads(text)
    with pytest.raises(ValueError, match="part way"):
        list(builder.records(io.StringIO(text[:-5]), chunk=7))  # cut inside a record
    with pytest.raises(ValueError, match="closing bracket"):
        list(builder.records(io.StringIO(text[:-10]), chunk=7))  # cut between records
    with pytest.raises(ValueError, match="empty"):
        list(builder.records(io.StringIO("  ")))
    assert list(builder.records(io.StringIO("[]"))) == []
    with pytest.raises(ValueError, match="not a JSON array"):
        list(builder.records(io.StringIO('{"a": 1}')))


def test_download_lookup_refresh_and_fail_safe(tmp_path):
    source = built_index(tmp_path)
    clock = [1_000_000.0]
    fetches = []

    def fetch(url):
        fetches.append(url)
        with open(source, "rb") as src:
            return src.read()

    cache = tmp_path / "cache"
    index = protondb.ProtonDbIndex(str(cache), fetch=fetch, now=lambda: clock[0])
    assert index.ensure()["dump"] == "oct1_2026" and fetches == [protondb.URL]
    assert index.lookup(STEAM_GAME)["handheld"] == 2 and index.lookup(1999999999) is None
    index.ensure()
    assert len(fetches) == 1  # fresh: not downloaded again
    os.utime(index.path, (0, 0))
    clock[0] = protondb.REFRESH_AFTER + 1.0  # now more than a month old

    index._fetch = lambda url: b"not gzip"
    assert index.ensure()["dump"] == "oct1_2026"  # a bad download never replaces the old copy
    assert index.lookup(STEAM_GAME) is not None
    index._fetch = lambda url: gzip.compress(b'{"schema": 99}\n')
    assert index.ensure(force=True)["dump"] == "oct1_2026"  # a wrong schema is refused the same way
    index.clear()
    index._fetch = lambda url: b"not gzip"
    with pytest.raises(protondb.ProtonDbError, match="Press Refresh"):
        index.ensure()  # failed within the hour: not retried unless forced
    with pytest.raises(protondb.ProtonDbError, match="not valid"):
        index.ensure(force=True)
    assert os.path.getsize(index.path) == 0  # emptied, never deleted (P16)


def test_a_success_clears_an_earlier_failure(tmp_path):
    data = open(built_index(tmp_path), "rb").read()
    answers = [b"not gzip", data, data]
    index = protondb.ProtonDbIndex(str(tmp_path / "cache"), fetch=lambda url: answers.pop(0), now=lambda: 5000.0)
    with pytest.raises(protondb.ProtonDbError):
        index.ensure()
    assert index.ensure(force=True)["dump"] == "oct1_2026"
    index.clear()
    assert index.ensure()["dump"] == "oct1_2026"  # not held back by the old failure
    assert answers == []


def test_lookup_matches_the_whole_app_id_only(tmp_path):
    data = open(built_index(tmp_path), "rb").read()
    index = protondb.ProtonDbIndex(str(tmp_path / "cache"), fetch=lambda url: data)
    index.ensure()
    assert index.lookup(STEAM_GAME) is not None
    assert index.lookup(999101) is None and index.lookup(1) is None  # tails of 1999999101
    # 999101 sorts after 1999999101 as text, so a loose match would stop at the wrong line first.
    tail = builder.build(
        make_dump(
            tmp_path, [rec(STEAM_GAME, "AMD Ryzen Z1 Extreme"), rec(999101, "AMD Ryzen Z1 Extreme", title="Tail Game")]
        ),
        str(tmp_path / "tail"),
    )
    both = protondb.ProtonDbIndex(str(tmp_path / "cache2"), fetch=lambda url: open(tail, "rb").read())
    both.ensure()
    assert both.lookup(999101)["title"] == "Tail Game"


def test_build_keeps_the_newest_five_handheld_reports(tmp_path):
    records = [rec(STEAM_GAME, "AMD Ryzen Z1 Extreme", t=1790000000 + i) for i in range(8)]
    path = builder.build(make_dump(tmp_path, records), str(tmp_path / "out"))
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        handle.readline()
        entry = json.loads(handle.readline().split("\t", 1)[1])
    assert entry["handheld"] == 8 and [r["t"] for r in entry["reports"]] == [1790000000 + i for i in (7, 6, 5, 4, 3)]


def test_an_oversized_index_is_refused(tmp_path, monkeypatch):
    data = open(built_index(tmp_path), "rb").read()
    monkeypatch.setattr(protondb, "MAX_BYTES", len(data) - 1)
    index = protondb.ProtonDbIndex(str(tmp_path / "cache"), fetch=lambda url: data)
    with pytest.raises(protondb.ProtonDbError, match="not valid"):
        index.ensure()
    assert not os.path.exists(index.path)


def test_advisor_uses_protondb_only_when_switched_on(tmp_path):
    advisor, _calls = make_advisor(tmp_path)
    source = built_index(tmp_path)
    fetches = []

    def fetch(url):
        fetches.append(url)
        with open(source, "rb") as src:
            return src.read()

    advisor.protondb = protondb.ProtonDbIndex(advisor.cache_dir, fetch=fetch)
    advisor.set_game(STEAM_GAME)
    off = advisor.view()
    assert fetches == [] and off["protondb"]["enabled"] is False and protondb.ATTRIBUTION not in off["attribution"]
    advisor.save_settings({"sourceProtonDb": True})
    advisor.load_reports()
    on = advisor.view()
    assert fetches == [protondb.URL] and on["protondb"]["summary"]["handheld"] == 2
    assert on["protondb"]["summary"]["share"] == 67 and protondb.ATTRIBUTION in on["attribution"]
    sources = [r.get("source") for r in on["recommendations"]]
    assert sources.count("protondb") == 2
    same_chip = next(
        r for r in on["recommendations"] if r.get("source") == "protondb" and "Z2" in r.get("apu_reported", "")
    )
    assert same_chip["device_match"] == "same_apu"  # the synthetic Legion Go 2 has a Z2 Extreme
    assert os.path.dirname(advisor.protondb.path) == advisor.cache_dir  # P16: its own cache only
    advisor.set_game(3500000002)  # a shortcut with no Steam app ID
    assert "Steam app ID" in advisor.view()["protondb"]["error"]
    advisor.save_settings({"sourceProtonDb": False})
    assert os.path.getsize(advisor.protondb.path) == 0  # turning it off frees the space


@pytest.mark.parametrize("seed", range(200))
def test_hostile_index_entries_never_break_advice(seed):
    rng = random.Random(seed)
    values = [None, 1, -5, 1e308, float("nan"), "x" * 500, [], {}, True, "yes", "ge", "GE-Proton9-1", 10**20]

    def anything():
        return rng.choice(values)

    entry = {
        "n": anything(),
        "works": anything(),
        "handheld": anything(),
        "reports": rng.choice(
            [
                anything(),
                [
                    {k: anything() for k in ("t", "verdict", "variant", "proton", "launch", "notes", "device", "apu")}
                    for _ in range(8)
                ],
            ]
        ),
    }
    out = protondb.normalise(entry, STEAM_GAME)
    assert len(out) <= protondb.MAX_REPORTS
    for r in out:
        assert isinstance(r["notes"], str) and len(r["notes"]) <= 300 and isinstance(r["report_date"], str)
    summary = protondb.summary(entry, {"dump": anything()}, STEAM_GAME)
    if summary:
        assert 0 <= summary["works"] <= summary["reports"]
