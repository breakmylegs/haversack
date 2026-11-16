"""Advisor I (v2 slice 14): device profiles, tools, sources, ranking, game mapping and the read-only rule.

Every fixture is synthetic (principle 12, docs/advisor-port-audit.md section 3).
"""

import asyncio
import json
import os
import re
import threading
import time
from datetime import UTC, datetime

import pytest

from keepsake import devices, net
from keepsake.advisor import anticheat, deckverified, recommend, stack
from keepsake.advisor.service import Advisor, AdvisorError

GO = {"sys_vendor": "LENOVO", "product_name": "83E1", "cpu_model": "AMD Ryzen Z1 Extreme"}
GO2 = {"sys_vendor": "LENOVO", "product_name": "83N0", "cpu_model": "AMD Ryzen Z2 Extreme"}
NOW = datetime(2026, 11, 16, tzinfo=UTC)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def fake_root(tmp_path, facts):
    root = tmp_path / "root"
    for field in ("sys_vendor", "product_name", "board_name"):
        write(str(root / "sys/class/dmi/id" / field), facts.get(field, ""))
    write(str(root / "sys/class/dmi/id/product_serial"), "SYNTHETIC-SERIAL")  # must never be read
    write(str(root / "proc/cpuinfo"), f"processor\t: 0\nmodel name\t: {facts.get('cpu_model', '')}\n")
    write(str(root / "sys/class/drm/card0/device/vendor"), "0x1002")
    write(str(root / "etc/os-release"), 'ID=steamos\nPRETTY_NAME="SteamOS"\nVERSION_ID=3.7\n')
    return str(root)


# Device profiles (Core)


def test_device_detection_picks_the_most_specific_profile(tmp_path):
    profiles = devices.load_profiles()
    facts = devices.read_facts(fake_root(tmp_path, GO))
    assert "SYNTHETIC-SERIAL" not in json.dumps(facts) and facts["gpu_vendor"] == "amd"
    assert devices.resolve(profiles, facts)[0]["id"] == "lenovo-legion-go"
    assert devices.resolve(profiles, {**GO, "cpu_model": "AMD Ryzen Z1"})[0]["id"] == "lenovo-legion-go-z1"
    assert devices.resolve(profiles, GO2)[0]["id"] == "lenovo-legion-go-2-z2e"
    profile, how = devices.resolve(profiles, {"sys_vendor": "Synthetic", "product_name": "X1"})
    assert how == "generic" and profile["generic"] and profile["tdp_bands_w"]["derived"]
    assert devices.resolve(profiles, {}, "lenovo-legion-go-2-z2e") == (devices.resolve(profiles, GO2)[0], "override")
    for profile in profiles:  # Q2: manufacturer and Valve sources only, never the GPL projects
        assert not any(re.search(r"InputPlumber|hhd-dev|LeGoTDP", s) for s in profile["sources"]), profile["id"]
        assert {"usb4_ports", "wifi", "captured"} <= set(profile)


# The acceptance case: advice differs correctly between the two devices


def go_profiles():
    profiles = devices.load_profiles()
    return profiles, devices.resolve(profiles, GO)[0], devices.resolve(profiles, GO2)[0]


def test_general_advice_differs_between_legion_go_and_legion_go_2():
    profiles, go, go2 = go_profiles()
    tools = stack.load_tools()
    selected = {"power": "steam-native"}
    on_go = recommend.build([], profiles, tools, go, selected, "medium", False, NOW)[-1]
    on_go2 = recommend.build([], profiles, tools, go2, selected, "medium", False, NOW)[-1]
    # No VRR on the Legion Go: a cap that divides 144 Hz. VRR on the Legion Go 2: the target itself.
    assert on_go["display"]["fps_cap"] == 36 and 144 % 36 == 0
    assert on_go2["display"]["fps_cap"] == 45 and on_go2["display"]["vrr"] is True
    # Half of 2560x1600 with integer scaling, against native 1920x1200.
    assert on_go["scaling"] == {"steam_filter": "Integer", "scaling_mode": None, "game_resolution": "1280x800"}
    assert on_go2["scaling"]["game_resolution"] == "1920x1200" and on_go2["scaling"]["steam_filter"] == "Linear"
    assert "Turn on Variable Refresh Rate in Steam, Performance." in on_go2["lines"]["display"]
    assert not any("Variable Refresh" in line for line in on_go["lines"]["display"])
    assert on_go["power"]["tdp_w"] == 15 and on_go2["power"]["tdp_w"] == 16  # each device's own band
    heavy = recommend.build([], profiles, tools, go2, selected, "heavy", False, NOW)[-1]
    assert heavy["scaling"]["game_resolution"] == "1280x800" and heavy["scaling"]["steam_filter"] == "FSR"


def report(device="Lenovo Legion Go 2", fps="40", vrr="On", tdp="18", when="2026-10-01T00:00:00Z", votes=3):
    return {
        "html_url": "https://github.com/DeckSettings/game-reports-steamos/issues/1",
        "title": "Synthetic report",
        "updated_at": when,
        "reactions": {"reactions_thumbs_up": votes, "reactions_thumbs_down": 0},
        "data": {
            "device": device,
            "frame_limit": fps,
            "enable_vrr": vrr,
            "tdp_limit": tdp,
            "scaling_filter": "FSR",
            "game_graphics_settings": "- Graphics Preset: Medium\n- Upscaling: FSR 4 Quality\n",
            "custom_launch_options": "~/lsfg %command%",
            "average_battery_power_draw": "20",
        },
    }


def test_a_report_is_validated_against_each_device():
    profiles, go, go2 = go_profiles()
    tools = stack.load_tools()
    rec = deckverified.normalise(report())
    on_go2 = recommend.build([rec], profiles, tools, go2, {}, "medium", False, NOW)[0]
    on_go = recommend.build([rec], profiles, tools, go, {}, "medium", False, NOW)[0]
    assert on_go2["device_match"] == "exact" and on_go2["confidence"] == "high"
    assert on_go["device_match"] == "family" and on_go["confidence"] == "medium"
    assert not any("VRR" in f or "divide" in f for f in on_go2["flags"])  # 40 is inside 30 to 144 Hz
    assert any("does not divide 144 Hz" in f for f in on_go["flags"])
    assert any("This screen has no VRR" in f for f in on_go["flags"]) and on_go["display"]["vrr"] is False
    for rec_out in (on_go, on_go2):
        assert rec_out["upscaler"] == {"name": None, "mode": None}  # FSR 4 is never recommended
        assert any("lsfg-vk" in f for f in rec_out["flags"])  # frame generation needs a tool not selected
    assert on_go2["lines"]["battery"] == ["Reported battery draw 20 W. On your 74 Wh battery that is about 3h 42m."]


def test_ranking_prefers_your_device_then_recent_then_votes():
    profiles, _go, go2 = go_profiles()
    old = deckverified.normalise(report(when="2020-01-01T00:00:00Z", votes=50))
    deck = deckverified.normalise(report(device="Steam Deck OLED", votes=99))
    fresh = deckverified.normalise(report(votes=1))
    ranked = recommend.build([deck, old, fresh], profiles, stack.load_tools(), go2, {}, "medium", False, NOW)
    assert ranked[1]["confidence"] == "medium"  # your device, but over a year old: not high
    assert [(r["device_match"], r["votes"]) for r in ranked] == [
        ("exact", 1),
        ("exact", 50),
        ("steam_deck", 99),
        ("generic", 0),
    ]


# Tools


def test_stack_detection_conflicts_and_manual_choice(tmp_path):
    decky = tmp_path / "homebrew"
    write(str(decky / "plugins/a/plugin.json"), json.dumps({"name": "SimpleDeckyTDP"}))
    write(str(decky / "plugins/b/plugin.json"), json.dumps({"name": "LeGoTDP"}))
    write(str(decky / "plugins/c/plugin.json"), json.dumps({"name": "PowerControl"}))
    write(str(decky / "settings/loader.json"), json.dumps({"disabled_plugins": ["PowerControl"]}))
    tools = stack.load_tools()
    _profiles, go, _go2 = go_profiles()
    detected = stack.detect(tools, str(decky), str(tmp_path / "home"), "deck", go, root=str(tmp_path / "none"))
    assert {t["id"]: t.get("disabled", False) for t in detected["tools"]} == {
        "simpledeckytdp": False,
        "powercontrol": True,
        "legotdp": False,
    }
    assert [c["kind"] for c in stack.conflicts(tools, detected, go)] == ["multiple_power"]
    assert stack.select(tools, detected, {})["power"] == "simpledeckytdp"
    assert stack.select(tools, detected, {"power": "legotdp"})["power"] == "legotdp"
    rec = recommend.build([], *go_profiles()[:1], tools, go, {"power": "legotdp"}, "medium", False, NOW)[-1]
    assert rec["lines"]["power"] == ["Select Balanced (15 W) in LeGoTDP, or set SPL (Sustained) to 15 W."]


# Sources


class FakeHttp:
    def __init__(self, status=200, body=b'{"reports": []}', error=None):
        self.status, self.body, self.error, self.calls = status, body, error, []

    def __call__(self, url, headers=None, max_bytes=None, allowed=None, timeout=None):
        self.calls.append((url, allowed))
        if self.error:
            raise self.error
        net.check_url(url, allowed or net.ALLOWED_HOSTS)
        return net.HttpResponse(self.status, {}, self.body)


def test_deck_verified_fetch_and_normalise():
    http = FakeHttp(body=json.dumps({"reports": [report()]}).encode())
    assert len(deckverified.fetch(1999999101, None, http)["reports"]) == 1
    assert http.calls[0] == (
        "https://deckverified.games/deck-verified/api/v1/game_details?appid=1999999101",
        frozenset({"deckverified.games"}),
    )
    deckverified.fetch(None, "Example Quest & Co", http)
    assert http.calls[1][0].endswith("?name=Example+Quest+%26+Co")
    assert deckverified.fetch(1, None, FakeHttp(status=204)) == {"reports": []}
    for bad in (FakeHttp(status=429), FakeHttp(body=b"<html>"), FakeHttp(error=net.NetError("down"))):
        with pytest.raises(deckverified.SourceError):
            deckverified.fetch(1, None, bad)
    hostile = deckverified.normalise({**report(), "html_url": "https://evil.example/x", "data": "not a dict"})
    assert hostile["source_url"] == "" and hostile["power"]["tdp_w"] is None  # links only to GitHub reports


def awacy(*games):
    return json.dumps(list(games)).encode()


def test_anticheat_list_weekly_lookup_and_retry(tmp_path):
    clock = {"now": time.time()}
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) == 2:
            raise anticheat.AntiCheatError("down")
        return awacy(
            {
                "name": "Synthetic Arena",
                "status": "Denied",
                "storeIds": {"steam": "1999999102"},
                "slug": "synthetic-arena",
            },
            {"name": "Synthetic Racer", "status": "Running", "storeIds": {}},
            {"name": "Bad", "status": "Unknown"},
        )

    ac = anticheat.AntiCheatList(str(tmp_path), fetch=fetch, now=lambda: clock["now"])
    ac.ensure()
    entry = ac.lookup(1999999102)
    assert entry["blocked"] and entry["url"].endswith("/game/synthetic-arena") and "MIT" in entry["attribution"]
    assert ac.lookup(None, "synthetic racer")["status"] == "Running" and ac.lookup(None, "Bad") is None
    ac.ensure()
    assert len(calls) == 1  # fresh for a week: nothing is sent
    os.utime(ac.path, (0, 0))
    ac.ensure()  # a week old: the refresh fails and the old copy stays
    assert len(calls) == 2 and ac.lookup(1999999102)
    ac.ensure()
    assert len(calls) == 2  # no retry within the hour


# The service: Steam game, shortcut mapping and the read-only rule


class Games:
    """A synthetic Games list: one Steam game, one shortcut with a manifest Steam ID, one without."""

    def __call__(self, appid):
        return {
            1999999101: {"name": "Example Quest", "kind": "steam", "steamAppid": 1999999101},
            3500000001: {
                "name": "Example Quest (shortcut)",
                "kind": "shortcut",
                "steamAppid": 1999999101,
                "manifestTitle": "Example Quest",
            },
            3500000002: {"name": "Homebrew Thing", "kind": "shortcut"},
        }.get(appid, {"name": "", "kind": "unknown"})


def make_advisor(tmp_path, facts=GO2):
    calls = []

    def fetch_reports(appid, name):
        calls.append((appid, name))
        return {"reports": [report()]}

    root = fake_root(tmp_path, facts)
    decky = tmp_path / "homebrew"
    write(str(decky / "plugins/a/plugin.json"), json.dumps({"name": "SimpleDeckyTDP"}))
    advisor = Advisor(
        str(tmp_path / "settings"),
        str(tmp_path / "runtime/advisor-cache"),
        str(decky),
        str(tmp_path / "home"),
        "deck",
        Games(),
        root=root,
        fetch_reports=fetch_reports,
        anticheat_fetch=lambda: awacy(
            {"name": "Example Quest", "status": "Supported", "storeIds": {"steam": "1999999101"}}
        ),
    )
    advisor.detect()
    return advisor, calls


def snapshot(folder, skip):
    out = {}
    for base, _dirs, files in os.walk(folder):
        for name in files:
            path = os.path.join(base, name)
            if not any(path.startswith(s) for s in skip):
                with open(path, "rb") as handle:
                    out[path] = handle.read()
    return out


def test_advice_for_a_steam_game_and_shortcuts_writes_nothing_else(tmp_path):
    advisor, calls = make_advisor(tmp_path)
    own = [str(tmp_path / "settings" / "advisor.json"), str(tmp_path / "runtime" / "advisor-cache")]
    before = snapshot(str(tmp_path), own)
    advisor.set_game(1999999101)
    steam = advisor.view()
    advisor.set_game(3500000001)  # a shortcut mapped through the manifest's Steam ID
    mapped = advisor.view()
    advisor.set_game(3500000002)  # a shortcut with no Steam ID: looked up by name
    by_name = advisor.view()
    advisor.save_settings({"steamIdOverrides": {"3500000002": 1999999101}, "workload": "heavy"})
    advisor.set_game(3500000002)
    overridden = advisor.view()
    advisor.load_reports(True)
    assert snapshot(str(tmp_path), own) == before  # P16: nothing outside its own settings and cache changed
    assert calls == [(1999999101, None), (None, "Homebrew Thing"), (1999999101, None)]  # the rest came from cache
    assert steam["device"]["id"] == "lenovo-legion-go-2-z2e" and steam["game"]["mapping"] == "steam"
    assert steam["stack"]["selected"]["power"] == "simpledeckytdp"
    assert steam["recommendations"][0]["confidence"] == "high" and steam["anticheat"]["entry"]["status"] == "Supported"
    assert mapped["game"]["mapping"] == "manifest" and mapped["recommendations"][0]["confidence"] == "high"
    assert by_name["game"]["mapping"] == "name" and by_name["recommendations"][0]["confidence"] == "low"
    assert overridden["game"]["mapping"] == "manual" and overridden["recommendations"][-1]["workload"] == "heavy"
    assert steam["recommendations"][-1]["source"] == "fallback"  # general advice is always offered last
    assert {c["id"] for c in advisor.health()} == {"advisor-device", "advisor-sources"}


def test_a_failed_refresh_keeps_cached_reports(tmp_path):
    advisor, _calls = make_advisor(tmp_path)
    advisor.set_game(1999999101)

    def down(appid, name):
        raise deckverified.SourceError("Deck Verified could not be reached.")

    advisor._fetch_reports = down
    advisor.load_reports(True)
    view = advisor.view()
    assert view["source"]["cached"] and view["source"]["error"] == "Deck Verified could not be reached."
    assert view["recommendations"][0]["source"] == "deckverified"
    assert advisor.health()[1]["status"] == "warn"


def test_settings_are_validated(tmp_path):
    advisor, _calls = make_advisor(tmp_path)
    for bad in (
        {"workload": "extreme"},
        {"deviceOverride": "synthetic-device"},
        {"stackOverrides": {"power": "unknown-tool"}},
        {"stackOverrides": {"teleport": "auto"}},
        {"steamIdOverrides": {"3500000002": True}},
        {"steamIdOverrides": {"3500000002": 3500000003}},
        {"sourceAntiCheat": "yes"},
        {"anything": 1},
    ):
        with pytest.raises(AdvisorError):
            advisor.save_settings(bad)
    advisor.save_settings({"deviceOverride": "lenovo-legion-go"})
    assert advisor.device["id"] == "lenovo-legion-go" and advisor.device_how == "override"


ADVISOR_SOURCES = os.path.join(os.path.dirname(__file__), "..", "py_modules", "keepsake", "advisor")
FRONTEND = os.path.join(os.path.dirname(__file__), "..", "src", "pages")


def test_advisor_code_has_no_way_to_write_elsewhere():
    """P16, statically: no process launching, deleting, moving, raw writes or Steam calls in Advisor code."""
    forbidden = re.compile(
        r"subprocess|os\.system|shutil|os\.(remove|unlink|rename|replace|rmdir|symlink|chmod)|open\([^)]*['\"][wax+]"
    )
    for name in os.listdir(ADVISOR_SOURCES):
        if name.endswith(".py"):
            with open(os.path.join(ADVISOR_SOURCES, name), encoding="utf-8") as handle:
                assert not forbidden.search(handle.read()), name
    for name in os.listdir(FRONTEND):
        if name.startswith("Advisor"):
            with open(os.path.join(FRONTEND, name), encoding="utf-8") as handle:
                text = handle.read()
            assert "SteamClient" not in text and "steamOps" not in text, (
                name
            )  # advice is shown and copied, never applied


# Through the app


def test_the_running_game_reaches_advisor_without_delaying_it(tmp_path):
    from keepsake.store import LocalFolderStore
    from test_app_ux import Device

    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    gate = threading.Event()

    def slow_fetch(appid, name):
        gate.wait(10)
        return {"reports": []}

    async def go():
        await a.app.start()
        a.app.advisor._fetch_reports = slow_fetch
        a.app.advisor.anticheat._fetch = lambda: awacy({"name": "x", "status": "Running", "storeIds": {}})
        handled = await asyncio.wait_for(a.app.on_game_event("start", 4171510507), 2)  # returns at once
        gate.set()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if (a.app.advisor.game or {}).get("appid") == 4171510507 and ("keepsake_advisor", ()) in a.events:
                break
        view = await a.app.advisor_view()
        await a.app.stop()
        return handled, view

    handled, view = asyncio.run(go())
    assert handled == {"handled": 0}  # Saves does not sync it, but Advisor heard it start
    assert view["running"] and view["game"]["name"] == "Example Quest" and view["game"]["shortcut"]
    assert view["recommendations"][-1]["source"] == "fallback"


def test_a_game_outside_the_games_list_gets_general_advice_and_no_lookups(tmp_path):
    advisor, calls = make_advisor(tmp_path)
    advisor.set_game(12345)
    view = advisor.view()
    assert calls == [] and view["game"]["steamAppid"] is None  # fail closed: nothing sent anywhere
    assert [r["source"] for r in view["recommendations"]] == ["fallback"]


def test_the_app_maps_a_shortcut_through_the_manifest_steam_id(tmp_path):
    from keepsake.store import LocalFolderStore
    from test_app_ux import Device

    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        "Example Quest:\n  files:\n    <winAppData>/ExampleQuest:\n      tags:\n        - save\n"
        "  steam:\n    id: 1999999103\n",
        encoding="utf-8",
    )
    a.app.manifest.import_file(str(manifest_file))
    mapped = a.app._advisor_map_game(4171510507)
    assert mapped == {
        "name": "Example Quest",
        "kind": "shortcut",
        "launchOptions": "",
        "compatTool": "",
        "manifestTitle": "Example Quest",
        "steamAppid": 1999999103,
    }
    assert a.app._advisor_map_game(12345) == {"name": "", "kind": "unknown"}


def test_equally_specific_profiles_keep_registry_order():
    first = {"id": "first", "match": {"sys_vendor": ["Synthetic"]}}
    second = {"id": "second", "match": {"board_name": ["S1"]}}
    assert devices.resolve([first, second], {"sys_vendor": "Synthetic", "board_name": "S1"})[0]["id"] == "first"


def test_a_slow_answer_for_an_earlier_game_never_replaces_the_current_one(tmp_path):
    advisor, _calls = make_advisor(tmp_path)

    def fetch_reports(appid, name):
        if name == "Homebrew Thing":  # while this answer is on its way, the player picks the Steam game
            advisor._fetch_reports = lambda a, n: {"reports": [report(device="Steam Deck OLED")]}
            advisor.set_game(1999999101)
        return {"reports": [report()]}

    advisor._fetch_reports = fetch_reports
    advisor.set_game(3500000002)
    view = advisor.view()
    assert view["game"]["appid"] == 1999999101
    assert [r["device_reported"] for r in view["recommendations"]] == ["Steam Deck OLED", ""]
