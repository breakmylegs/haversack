"""Advisor parser fuzzing (v2 slice 25 on slices 14 and 15): untrusted input never crashes or slips through.

Deck Verified reports, the anti-cheat list, AI replies and launch options are
all outside input. Each must return or raise its own error, and the checked
result must stay within what this device can do. Deterministic seeds;
``KEEPSAKE_FUZZ_ITERATIONS`` scales the run.
"""

import json
import os
import random
from datetime import UTC, datetime

from keepsake import devices
from keepsake.advisor import ai, anticheat, compat, deckverified, recommend, stack

ITERATIONS = int(os.environ.get("KEEPSAKE_FUZZ_ITERATIONS", "1500"))
NOW = datetime(2026, 11, 16, tzinfo=UTC)
ATOMS = [
    None,
    True,
    False,
    0,
    -1,
    7,
    10**12,
    3.5,
    float("nan"),
    "",
    "On",
    "Off",
    "45",
    "18 W",
    "Unknown",
    "FSR 4",
    "~/lsfg",
    "https://evil.example",
    "https://github.com/x",
    "%command%",
    "a;b",
    "é" * 300,
]
KEYS = [
    "data",
    "device",
    "frame_limit",
    "enable_vrr",
    "tdp_limit",
    "scaling_filter",
    "game_graphics_settings",
    "custom_launch_options",
    "html_url",
    "reactions",
    "reactions_thumbs_up",
    "labels",
    "name",
    "updated_at",
    "steam_play_compatibility_tool_used",
    "compatibility_tool_version",
    "average_battery_power_draw",
    "x",
]


def random_value(rng, depth=0):
    roll = rng.random()
    if depth < 3 and roll < 0.2:
        return {rng.choice(KEYS): random_value(rng, depth + 1) for _ in range(rng.randint(0, 6))}
    if depth < 3 and roll < 0.3:
        return [random_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return rng.choice(ATOMS)


def go2():
    profiles = devices.load_profiles()
    return profiles, devices.resolve(
        profiles, {"sys_vendor": "LENOVO", "product_name": "83N0", "cpu_model": "Z2 Extreme"}
    )[0]


def test_deck_verified_reports_of_any_shape_normalise_and_validate():
    rng = random.Random(2521)
    profiles, device = go2()
    tools = stack.load_tools()
    low, high = device["tdp_w"]["min"], device["tdp_w"]["max"]
    for _ in range(ITERATIONS // 3):
        raw = {rng.choice(KEYS): random_value(rng) for _ in range(rng.randint(0, 10))}
        raw["data"] = {rng.choice(KEYS): random_value(rng) for _ in range(rng.randint(0, 12))}
        rec = deckverified.normalise(raw)
        assert rec["source_url"] == "" or rec["source_url"].startswith("https://github.com/")
        for built in recommend.build([rec], profiles, tools, device, {}, rng.choice(recommend.WORKLOADS), False, NOW):
            tdp = built["power"]["tdp_w"]
            assert tdp is None or low <= tdp <= high  # whatever a report says, advice stays within the device
            assert not recommend.FSR4_RE.search(json.dumps(built["upscaler"]))


def test_anticheat_lists_of_any_shape():
    rng = random.Random(2522)
    for _ in range(ITERATIONS // 3):
        raw = [
            {k: random_value(rng) for k in rng.sample(["name", "status", "storeIds", "notes", "slug", "anticheats"], 4)}
            for _ in range(rng.randint(0, 5))
        ]
        for game in raw:
            if rng.random() < 0.5:
                game["status"] = rng.choice(list(anticheat.STATUSES))
        try:
            trimmed = anticheat.trim(raw if rng.random() < 0.95 else random_value(rng))
        except anticheat.AntiCheatError:
            continue
        for entry in [*trimmed["by_appid"].values(), *trimmed["by_name"].values()]:
            assert entry["status"] in anticheat.STATUSES
            assert all(n["url"] == "" or n["url"].startswith("https://") for n in entry["notes"])


def test_ai_replies_of_any_shape_are_checked():
    rng = random.Random(2523)
    _profiles, device = go2()
    low, high = device["tdp_w"]["min"], device["tdp_w"]["max"]
    groups = ["power", "display", "scaling", "upscaler", "frame_gen", "in_game", "compat", "notes"]
    fields = ["tdp_w", "gpu_clock_mhz", "fps_cap", "refresh_hz", "vrr", "name", "mode", "preset", "settings", "proton"]
    for _ in range(ITERATIONS):
        data = {
            g: {f: random_value(rng) for f in rng.sample(fields, 4)} if rng.random() < 0.8 else random_value(rng)
            for g in groups
        }
        text = (
            json.dumps(data, default=str)
            if rng.random() < 0.9
            else rng.choice(["", "{", "[1]", "```json\n{}\n```", "x" * 50])
        )
        try:
            parsed = ai.parse_reply(text)
        except ai.AiError:
            continue
        rec, discarded = ai.to_recommendation(parsed, device)
        assert isinstance(discarded, list)
        tdp = rec["power"]["tdp_w"]
        assert tdp is None or (isinstance(tdp, int) and low <= tdp <= high)
        cap = rec["display"]["fps_cap"]
        assert cap is None or (isinstance(cap, int) and 0 < cap <= device["display"]["refresh_hz_max"])
        assert rec["upscaler"]["name"] is None or not recommend.FSR4_RE.search(rec["upscaler"]["name"])
        assert all(not recommend.FSR4_RE.search(f"{s['name']} {s['value']}") for s in rec["in_game"]["settings"])
        assert rec["source"] == "ai" and rec["confidence"] == "low"


def test_launch_options_of_any_shape():
    rng = random.Random(2524)
    parts = [
        "%command%",
        "FSR4_UPGRADE=1",
        "DXVK_HUD=1",
        "~/lsfg",
        "gamemoderun",
        "-novid",
        ";",
        "|",
        "$(x)",
        "'",
        '"',
        "\\",
        "\x00",
        "\x1b",
        " ",
        "PROTON_LOG=1",
        "a" * 40,
    ]
    for _ in range(ITERATIONS):
        recommended = " ".join(rng.choice(parts) for _ in range(rng.randint(0, 10)))
        current = " ".join(rng.choice(parts) for _ in range(rng.randint(0, 6)))
        section = compat.launch_section(
            recommended, current, {"framegen": rng.choice(["none", "lsfg-vk"])}, rng.random() < 0.5
        )
        if section is None:
            continue
        for text in (section["recommended"], section["merged"] or ""):
            assert "FSR4_UPGRADE" not in text and "\x00" not in text and "\x1b" not in text
            assert len(text) <= compat.MAX_LEN * 2
        if any(c in recommended for c in ";|") or "$(" in recommended:
            assert any("shell operators" in f for f in section["flags"])
