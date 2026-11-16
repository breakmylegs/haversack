"""Advisor II (v2 slice 15): Proton and launch options, current values, frame generation, upscaling and AI (P18).

Every fixture is synthetic (principle 12).
"""

import json
import os

import pytest

from keepsake import devices, net
from keepsake.advisor import ai, compat, current, deckverified, recommend, stack
from test_advisor import GO, GO2, NOW, make_advisor, report, snapshot, write


def profiles():
    found = devices.load_profiles()
    return found, devices.resolve(found, GO)[0], devices.resolve(found, GO2)[0]


# Launch options and Proton


def test_launch_options_are_explained_merged_and_flagged():
    section = compat.launch_section(
        "PROTON_USE_WINED3D=1 FSR4_UPGRADE=1 ~/lsfg %command% -novid; rm x", "DXVK_HUD=1 %command% -windowed", {}, False
    )
    assert "FSR4" not in section["recommended"] and any("FSR 4" in f for f in section["flags"])
    assert any("shell operators" in f for f in section["flags"])
    assert any("~/lsfg needs lsfg-vk" in f for f in section["flags"])
    assert section["merged"].startswith("DXVK_HUD=1 PROTON_USE_WINED3D=1 ~/lsfg %command% -windowed")
    assert section["where"].startswith("Steam, the game's Properties")
    assert compat.launch_section("", "anything", {}, False) is None
    same = compat.launch_section("DXVK_HUD=1 %command%", "DXVK_HUD=1 %command%", {}, True)
    assert same["sameAsCurrent"] and "Shortcut" in same["where"]


def test_installed_ge_proton_is_found_newest_first(tmp_path):
    root = tmp_path / "steam"
    for name in ("GE-Proton9-27", "GE-Proton10-3", "GE-Proton10-10", "Proton-tkg", "GE-Proton8-1"):
        os.makedirs(root / "compatibilitytools.d" / name)
    write(str(root / "compatibilitytools.d" / "GE-Proton11-1"), "a file, not a folder")
    assert compat.installed_ge_proton([str(root), str(tmp_path / "missing")]) == [
        "GE-Proton10-10",
        "GE-Proton10-3",
        "GE-Proton9-27",
        "GE-Proton8-1",
    ]


def test_proton_follows_the_signal_order():
    ge_report = deckverified.normalise(
        {
            **report(),
            "data": {
                **report()["data"],
                "steam_play_compatibility_tool_used": "GE",
                "compatibility_tool_version": "10-3",
            },
        }
    )
    from_report = compat.proton_section([ge_report], "", True, ["GE-Proton10-3"])
    assert from_report["signal"] == "report" and from_report["recommended"] == "GE-Proton10-3"
    assert from_report["installNote"] is None  # already installed
    assert "Replication" in from_report["peer"]  # the peer signal comes first once Replication exists
    installed = compat.proton_section([], "", True, ["GE-Proton10-10", "GE-Proton9-1"])
    assert installed["signal"] == "installed" and installed["recommended"] == "GE-Proton10-10"
    assert compat.proton_section([], "", False, ["GE-Proton10-10"]) is None  # a Steam game: Steam's choice stands
    matching = compat.proton_section([], "GE-Proton10-10", True, ["GE-Proton10-10"])
    assert matching["matches"] and matching["current"] == "GE-Proton10-10"
    missing = compat.proton_section([ge_report], "", True, [])
    assert missing["installNote"].startswith("GE-Proton is not built into Steam")


# Current values (read-only)


def test_current_values_from_the_selected_tools(tmp_path):
    decky = tmp_path / "homebrew"
    write(
        str(decky / "settings/SimpleDeckyTDP/settings.json"),
        json.dumps({"enableTdpProfiles": True, "tdpProfiles": {"1999999101": {"tdp": 12}, "default": {"tdp": 15}}}),
    )
    write(
        str(tmp_path / "home/.config/lsfg-vk/conf.toml"),
        'version = 2\n[[profile]]\nname = "synthetic"\nactive_in = ["1999999101"]\nmultiplier = 2\nflow_scale = 0.75\n',
    )
    detected = {"tools": [{"id": "simpledeckytdp", "folder": "SimpleDeckyTDP"}, {"id": "lsfg-vk", "folder": "lsfg"}]}
    selected = {"power": "simpledeckytdp", "framegen": "lsfg-vk"}
    found = current.read(selected, detected, str(decky), str(tmp_path / "home"), 1999999101)
    assert found["power"] == {"tdp_w": 12, "scope": "this game's profile", "note": None, "tool": "simpledeckytdp"}
    assert found["framegen"]["multiplier"] == 2 and found["framegen"]["flow_scale"] == 0.75
    assert (
        current.read(selected, detected, str(decky), str(tmp_path / "home"), 1999999102)["power"]["scope"]
        == "default profile"
    )
    write(str(decky / "settings/SimpleDeckyTDP/settings.json"), "{not json")
    assert current.read(selected, detected, str(decky), str(tmp_path / "home"), 1999999101)["power"] is None
    assert current.read(selected, detected, str(decky), str(tmp_path / "home"), None) == {
        "power": None,
        "framegen": None,
    }


# Frame generation and upscaling


def test_frame_generation_only_from_a_base_of_40_fps():
    found, _go, go2 = profiles()
    tools = stack.load_tools()
    selected = {"power": "steam-native", "framegen": "lsfg-vk"}
    light = recommend.build([], found, tools, go2, selected, "light", False, NOW)[-1]
    heavy = recommend.build([], found, tools, go2, selected, "heavy", False, NOW)[-1]
    assert "works from this base of 60 fps" in light["lines"]["frame_gen"][0]
    assert light["lines"]["frame_gen"][0].startswith("Use the game's own frame generation")  # in-game first
    assert "not advised: a base of 30 fps is below the 40 fps" in heavy["lines"]["frame_gen"][0]
    without = recommend.build([], found, tools, go2, {"framegen": "none"}, "light", False, NOW)[-1]
    assert without["lines"]["frame_gen"] == []  # no lsfg-vk, no frame generation advice
    low_base = deckverified.normalise(report(fps="30"))
    rec = recommend.build([low_base], found, tools, go2, selected, "medium", False, NOW)[0]
    assert any("base of 30 fps shows visible artefacts" in f for f in rec["flags"])


def test_upscaling_puts_the_games_own_upscaler_first():
    found, go, _go2 = profiles()
    tools = stack.load_tools()
    rec = deckverified.normalise(
        {**report(), "data": {**report()["data"], "game_graphics_settings": "- Upscaling: FSR 3 Quality\n"}}
    )
    built = recommend.build([rec], found, tools, go, {}, "medium", False, NOW)
    scaling = built[0]["lines"]["scaling"]
    assert scaling.index("In game, use FSR 3 (FSR 3 Quality).") < scaling.index(
        "Set Scaling Filter to FSR in Steam, Performance."
    )
    general = built[-1]["lines"]["scaling"]  # 1280x800 on a 2560x1600 panel: try the game's upscaler first
    assert general[0] == "Set the game resolution to 1280x800." and general[1].startswith(
        "If the game has its own upscaler"
    )
    assert general[2] == "Set Scaling Filter to Integer in Steam, Performance."


# AI (P18)


def test_ai_payload_holds_only_what_p18_allows(tmp_path):
    _found, _go, go2 = profiles()
    secret_report = report(device="Lenovo Legion Go 2 of Some Person")
    secret_report["data"]["summary"] = "Played on /home/someone/Games with my save from https://example.com/x"
    rec = deckverified.normalise(secret_report)
    rec["device_match"] = "exact"
    rec["compat"]["launch_options"] = "DXVK_HUD=1 %command%"
    body = ai.payload(
        "Example Quest",
        go2,
        {"power": "simpledeckytdp", "framegen": "none"},
        {"simpledeckytdp": "SimpleDeckyTDP"},
        [rec],
    )
    text = json.dumps(body)
    assert set(body) == {"game", "hardware", "tools", "settings_discussed"}
    assert body["game"] == {"title": "Example Quest"}  # the title only: no app ID (c0-report Q5)
    assert set(body["hardware"]) == set(ai.HARDWARE_FIELDS) and "id" not in body["hardware"]
    assert body["tools"] == {"framegen": None, "power": "SimpleDeckyTDP"}
    for forbidden in (
        "1999999101",
        "/home",
        "someone",
        "Some Person",
        "example.com",
        "github.com",
        "2026-10-01",
        "Played on",
    ):
        assert forbidden not in text, forbidden
    assert body["settings_discussed"][0]["from"] == "your device"
    assert body["settings_discussed"][0]["launch_options"] == "DXVK_HUD=1 %command%"  # a setting being discussed


class FakeProvider:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, method, url, headers=None, body=None, timeout=None, allowed=None, suffixes=None):
        net.check_url(url, allowed, suffixes or ())
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "body": json.loads(body) if body else None,
                "allowed": allowed,
            }
        )
        if url.endswith("/v1/models?limit=1000"):
            return net.HttpResponse(
                200, {}, json.dumps({"data": [{"id": "synthetic-model", "display_name": "Synthetic"}]}).encode()
            )
        return net.HttpResponse(
            200, {}, json.dumps({"content": [{"type": "text", "text": self.reply}], "stop_reason": "end_turn"}).encode()
        )


REPLY = json.dumps(
    {
        "power": {"tdp_w": 99, "gpu_clock_mhz": None},
        "display": {"refresh_hz": None, "fps_cap": 45, "vrr": True},
        "scaling": {"steam_filter": "Linear", "game_resolution": "1920x1200"},
        "upscaler": {"name": "FSR 4", "mode": "Quality"},
        "frame_gen": {"tool": None, "mode": None},
        "in_game": {"preset": "Medium", "settings": [{"name": "Shadows", "value": "Low"}, {"name": "x", "value": 3}]},
        "compat": {"proton": "GE-Proton10-3", "launch_options": "DXVK_ASYNC=1 %command%"},
        "notes": "Synthetic advice.",
    }
)


def test_ai_advice_from_a_button_press_with_checks(tmp_path):
    advisor, _calls = make_advisor(tmp_path)
    provider = FakeProvider(REPLY)
    keys = {"anthropic": "sk-synthetic-0123456789abcdef"}
    advisor._ai_key = lambda pid: keys.get(pid, "")
    advisor.ai_providers = {pid: cls(provider) for pid, cls in ai.PROVIDERS.items()}
    advisor.set_game(1999999101)
    assert advisor.generate_ai()["error"] == "Choose an AI provider in Advisor settings first."  # off by default
    advisor.save_settings({"aiProvider": "anthropic"})
    assert advisor.generate_ai()["error"] == "Load the model list and pick a model first."
    assert advisor.list_models("anthropic") == [{"id": "synthetic-model", "label": "Synthetic"}]
    advisor.save_settings({"aiModel": "synthetic-model", "aiDailyCap": 1})
    result = advisor.generate_ai()
    sent = provider.calls[-1]
    assert sent["url"] == "https://api.anthropic.com/v1/messages" and sent["headers"]["x-api-key"] == keys["anthropic"]
    assert {frozenset(c["allowed"]) for c in provider.calls} == {frozenset({"api.anthropic.com"})}  # one host only
    user_text = sent["body"]["messages"][0]["content"]
    assert "1999999101" not in user_text and '"title": "Example Quest"' in user_text
    rec = result["rec"]
    assert result["label"] == "AI generated, unverified" and result["error"] is None
    assert rec["power"]["tdp_w"] is None and rec["upscaler"] == {"name": None, "mode": None}  # 99 W and FSR 4 dropped
    assert any("99 W is outside" in d for d in result["discarded"]) and any(
        "not a name and value" in d for d in result["discarded"]
    )
    assert rec["lines"]["display"][0] == "Set Framerate Limit to 45 in Steam, Performance."
    assert rec["launch"]["recommended"] == "DXVK_ASYNC=1 %command%" and rec["confidence"] == "low"
    assert advisor.view()["ai"]["result"]["rec"] is not None and advisor.view()["ai"]["usedToday"] == 1
    assert "limit of 1" in advisor.generate_ai()["error"]  # the daily cap holds
    advisor.save_settings({"aiProvider": "openai"})
    assert advisor.settings()["aiModel"] == ""  # a new provider needs its own model
    assert advisor.generate_ai()["error"] == "Load the model list and pick a model first."


def test_ai_errors_never_leak_the_key_and_hosts_are_fixed():
    class Refused:
        def __call__(self, method, url, headers=None, body=None, **kw):
            return net.HttpResponse(401, {}, b"")

    with pytest.raises(ai.AiError) as caught:
        ai.Anthropic(Refused()).generate("sk-synthetic-secret-0000", "m", "hello")
    assert "sk-synthetic" not in caught.value.hint and "rejected the API key" in caught.value.hint
    assert {p.host for p in (ai.Anthropic, ai.OpenAI, ai.Gemini)} == {
        "api.anthropic.com",
        "api.openai.com",
        "generativelanguage.googleapis.com",
    }
    with pytest.raises(ai.AiError):
        ai.Gemini(FakeProvider("{}")).generate("k", "../../evil", "hello")  # model names cannot reach other paths
    with pytest.raises(ai.AiError):
        ai.parse_reply("not json at all")
    assert ai.parse_reply('```json\n{"a": 1}\n```') == {"a": 1}


def test_ai_keys_are_backend_secrets(tmp_path):
    from keepsake.backends import BackendConfigError, CredentialStore

    store = CredentialStore(str(tmp_path))
    with pytest.raises(BackendConfigError):
        store.save("openai", {"apiKey": "short"})
    assert store.save("openai", {"apiKey": "sk-synthetic-0123456789"}) == {
        "apiKey": "",
        "apiKeySet": True,
        "configured": True,
    }


def test_advisor_ii_still_writes_nothing_else(tmp_path):
    advisor, _calls = make_advisor(tmp_path)
    advisor._ai_key = lambda pid: "sk-synthetic-0123456789abcdef"
    advisor.ai_providers = {pid: cls(FakeProvider(REPLY)) for pid, cls in ai.PROVIDERS.items()}
    own = [str(tmp_path / "settings" / "advisor.json"), str(tmp_path / "runtime" / "advisor-cache")]
    write(str(tmp_path / "home/.config/lsfg-vk/conf.toml"), "version = 2\n")
    before = snapshot(str(tmp_path), own)
    advisor.save_settings({"aiProvider": "anthropic", "aiModel": "synthetic-model"})
    advisor.set_game(1999999101)
    advisor.generate_ai()
    view = advisor.view()
    assert snapshot(str(tmp_path), own) == before  # P16 holds with Proton, current values and AI
    assert view["proton"] is None or view["proton"]["signal"] in ("report", "installed")


def test_current_values_respect_each_tools_own_switches(tmp_path):
    decky = tmp_path / "homebrew"
    write(
        str(decky / "settings/SimpleDeckyTDP/settings.json"),
        json.dumps({"enableTdpProfiles": False, "tdpProfiles": {"1999999101": {"tdp": 12}, "default": {"tdp": 15}}}),
    )
    write(str(tmp_path / "home/.config/lsfg-vk/conf.toml"), 'version = 1\n[[profile]]\nactive_in = ["1999999101"]\n')
    detected = {"tools": [{"id": "simpledeckytdp", "folder": "SimpleDeckyTDP"}, {"id": "lsfg-vk", "folder": "lsfg"}]}
    found = current.read(
        {"power": "simpledeckytdp", "framegen": "lsfg-vk"}, detected, str(decky), str(tmp_path / "home"), 1999999101
    )
    assert found["power"]["tdp_w"] == 15 and "Per-game profiles are off" in found["power"]["note"]
    assert found["framegen"] is None  # an older lsfg-vk config format is not guessed at
