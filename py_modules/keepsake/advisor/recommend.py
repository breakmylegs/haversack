"""Device matching, ranking, validation, translation and fallback rules (v2 spec 8.1, ADR-0028).

Ported from Tuning Advisor (ADR-0013). Values reported on another device are
shown as reported, labelled with that device, and never scaled. Validation
clamps or drops what this device cannot do and records each change as a flag.
Keepsake adds device-aware render resolution and filter advice to the fallback,
so a 2560x1600 panel without VRR (Legion Go) and a 1920x1200 VRR panel (Legion
Go 2) get different, correct advice (spec 8.1).
"""

from __future__ import annotations

import copy
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from .deckverified import parse_date
from .stack import Tools

MATCH_ORDER = ("exact", "variant", "family", "same_apu", "other_handheld", "steam_deck", "generic")
MATCH_LABELS = {
    "exact": "your device",
    "variant": "another variant of your device",
    "family": "the same device family",
    "same_apu": "a device with the same chip",
    "other_handheld": "another handheld",
    "steam_deck": "a Steam Deck",
    "generic": "general guidance",
}
RECENT = timedelta(days=365)
FPS_TARGETS = {"light": 60, "medium": 45, "heavy": 30}
WORKLOADS = tuple(FPS_TARGETS)
FRAMEGEN_MIN_BASE = 40  # research 6.4: lsfg-vk only from about 40 fps, to avoid visible artefacts
FSR4_RE = re.compile(r"\b(?:fsr|fidelityfx super resolution)\s*4\b", re.I)


# Device matching


def device_for_report(profiles: list[dict[str, Any]], reported: str) -> dict[str, Any] | None:
    for entry in profiles:
        for pattern in entry.get("report_aliases") or []:
            try:
                if re.match(pattern, reported, re.I):
                    return entry
            except re.error:
                continue
    return None


def chip(name: Any) -> str:
    """Chips compare by name: "AMD Ryzen AI Z2 Extreme" is "AMD Ryzen Z2 Extreme"."""
    return " ".join(w for w in str(name or "").casefold().split() if w not in ("ai", "amd"))


def device_match(profiles: list[dict[str, Any]], reported: str, mine: dict[str, Any], apu_reported: str = "") -> str:
    theirs = device_for_report(profiles, reported)
    if theirs is None:
        if apu_reported and chip(apu_reported) == chip(mine.get("apu")):
            return "same_apu"
        steam_deck = "steam deck" in reported.casefold() and mine.get("family") != "steam-deck"
        return "steam_deck" if steam_deck else "other_handheld"
    if theirs["id"] == mine.get("id"):
        return "exact"
    if theirs.get("model") == mine.get("model") and theirs.get("vendor") == mine.get("vendor"):
        return "variant"
    if theirs.get("family") == mine.get("family") and mine.get("family") not in (None, "generic"):
        return "family"
    if theirs.get("apu") and chip(theirs.get("apu")) == chip(mine.get("apu")):
        return "same_apu"
    if theirs.get("family") == "steam-deck":
        return "steam_deck"
    return "other_handheld"


def confidence(rec: dict[str, Any], now: datetime, low_confidence_game: bool) -> str:
    if low_confidence_game:
        return "low"
    match = rec["device_match"]
    date = parse_date(rec.get("report_date", ""))
    recent = bool(date and now - date <= RECENT)
    if match in ("exact", "variant") and recent:
        return "high"
    if match in ("exact", "variant", "family", "same_apu"):
        return "medium"
    return "low"


# Ranking


def rank(recs: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    def key(rec: dict[str, Any]) -> tuple[int, int, int, float]:
        date = parse_date(rec.get("report_date", "")) or datetime(1970, 1, 1, tzinfo=UTC)
        order = MATCH_ORDER.index(rec["device_match"]) if rec["device_match"] in MATCH_ORDER else len(MATCH_ORDER)
        return (order, 0 if now - date <= RECENT else 1, -int(rec.get("votes") or 0), -date.timestamp())

    return sorted(recs, key=key)


# Validation


def nearest_divisor(target: int, refresh: int) -> int:
    divisors = [refresh // n for n in range(1, refresh + 1) if refresh % n == 0 and refresh // n >= 20]
    below = [d for d in divisors if d <= target]
    return max(below) if below else min(divisors)


def validate(rec: dict[str, Any], device: dict[str, Any], selected: dict[str, str]) -> dict[str, Any]:
    out = copy.deepcopy(rec)
    flags: list[str] = []
    tdp = out["power"].get("tdp_w")
    rng = device.get("tdp_w") or {}
    if tdp is not None and rng:
        lo, hi = rng.get("min"), rng.get("max")
        if lo is not None and tdp < lo:
            flags.append(f"TDP {tdp} W is below this device's {lo} W minimum. Raised to {lo} W.")
            out["power"]["tdp_w"] = lo
        elif hi is not None and tdp > hi:
            flags.append(f"TDP {tdp} W is above this device's {hi} W maximum. Lowered to {hi} W.")
            out["power"]["tdp_w"] = hi

    display = device.get("display") or {}
    max_hz = display.get("refresh_hz_max")
    refresh = out["display"].get("refresh_hz")
    if refresh and max_hz and refresh > max_hz:
        flags.append(f"Refresh {refresh} Hz is above this screen's {max_hz} Hz. Dropped.")
        out["display"]["refresh_hz"] = None
        refresh = None

    cap = out["display"].get("fps_cap")
    if cap and max_hz:
        panel_hz = refresh or max_hz
        if cap > max_hz:
            flags.append(f"FPS cap {cap} is above this screen's {max_hz} Hz. Dropped.")
            out["display"]["fps_cap"] = None
        elif display.get("vrr"):
            low, high = display.get("vrr_range_hz") or [30, max_hz]
            if not low <= cap <= high:
                flags.append(f"FPS cap {cap} is outside this screen's VRR range ({low} to {high} Hz).")
        elif panel_hz % cap != 0:
            better = nearest_divisor(cap, panel_hz)
            flags.append(
                f"FPS cap {cap} does not divide {panel_hz} Hz evenly, so frame pacing may stutter. Try {better}."
            )
    if out["display"].get("vrr") and not display.get("vrr") and max_hz:
        flags.append("The report uses VRR. This screen has no VRR.")
        out["display"]["vrr"] = False

    upscaler = out.get("upscaler") or {}
    if upscaler.get("name") and FSR4_RE.search(f"{upscaler.get('name')} {upscaler.get('mode') or ''}"):
        flags.append("FSR 4 is not recommended. It is not officially available on handheld chips under Proton.")
        out["upscaler"] = {"name": None, "mode": None}

    settings = (out.get("in_game") or {}).get("settings") or []
    kept = [st for st in settings if not FSR4_RE.search(f"{st.get('name', '')} {st.get('value', '')}")]
    if len(kept) != len(settings):
        out["in_game"]["settings"] = kept
        if not any("FSR 4" in f for f in flags):
            flags.append(
                "FSR 4 settings from the report are hidden. "
                "FSR 4 is not officially available on handheld chips under Proton."
            )

    tool = (out.get("frame_gen") or {}).get("tool")
    if tool and selected.get("framegen") != tool:
        out["frame_gen"]["requires"] = tool
        flags.append(f"Uses frame generation that needs {tool}, which is not in your selected tools.")
    base = out["display"].get("fps_cap")
    if tool == "lsfg-vk" and base and base < FRAMEGEN_MIN_BASE:
        flags.append(
            f"Frame generation from a base of {base} fps shows visible artefacts. "
            f"lsfg-vk needs about {FRAMEGEN_MIN_BASE} fps or more to look right."
        )

    out["flags"] = flags
    return out


# Translation into the selected tools' words


def nearest_preset(presets: list[dict[str, Any]], watts: int) -> dict[str, Any]:
    return min(presets, key=lambda p: (abs(p["spl"] - watts), p["spl"]))


def translate(rec: dict[str, Any], tools: Tools, device: dict[str, Any], selected: dict[str, str]) -> dict[str, Any]:
    lines: dict[str, list[str]] = {"power": [], "display": [], "scaling": [], "frame_gen": [], "in_game": []}
    watts = rec["power"].get("tdp_w")
    power_id = selected.get("power", "none")
    tool = tools.tool(power_id) if power_id != "none" else None
    if watts is not None:
        if tool:
            phrase = (tool.get("vocabulary") or {}).get("power", "Set the TDP to {w} W in " + tool["name"] + ".")
            if "{preset}" in phrase:
                presets_by_device = tool.get("presets") or {}
                presets = presets_by_device.get(device.get("id")) or presets_by_device.get("default") or []
                if presets:
                    preset = nearest_preset(presets, watts)
                    phrase = phrase.replace("{preset}", preset["name"]).replace("{spl}", str(preset["spl"]))
                else:
                    phrase = "Set SPL (Sustained) to {w} W in " + tool["name"] + "."
            lines["power"].append(phrase.replace("{w}", str(watts)))
        else:
            lines["power"].append(f"Set the TDP to {watts} W. No power tool is selected.")
    if rec["power"].get("gpu_clock_mhz"):
        lines["power"].append(f"Fix the GPU clock at {rec['power']['gpu_clock_mhz']} MHz in Steam, Performance.")

    display = rec["display"]
    if display.get("refresh_hz"):
        lines["display"].append(f"Set Refresh Rate to {display['refresh_hz']} Hz in Steam, Performance.")
    if display.get("fps_cap"):
        lines["display"].append(f"Set Framerate Limit to {display['fps_cap']} in Steam, Performance.")
    if display.get("vrr") is True:
        lines["display"].append("Turn on Variable Refresh Rate in Steam, Performance.")
    elif display.get("vrr") is False and (device.get("display") or {}).get("vrr"):
        lines["display"].append("Leave Variable Refresh Rate off.")

    # Upscaling order (spec 8.1): the game's own upscaler first, then Steam's scaling filter.
    scaling = rec["scaling"]
    if scaling.get("game_resolution"):
        lines["scaling"].append(f"Set the game resolution to {scaling['game_resolution']}.")
    upscaler = rec.get("upscaler") or {}
    if upscaler.get("name"):
        mode = f" ({upscaler['mode']})." if upscaler.get("mode") else "."
        lines["scaling"].append(f"In game, use {upscaler['name']}{mode}")
    elif rec.get("source") == "fallback" and _below_native(scaling.get("game_resolution"), device):
        lines["scaling"].append(
            "If the game has its own upscaler (FSR 2 or 3, XeSS or TSR), use it first at your screen's resolution. "
            "Otherwise use Steam's filter:"
        )
    if scaling.get("steam_filter"):
        lines["scaling"].append(f"Set Scaling Filter to {scaling['steam_filter']} in Steam, Performance.")

    fg = rec.get("frame_gen") or {}
    if rec.get("source") == "fallback" and selected.get("framegen") == "lsfg-vk":
        base = rec["display"].get("fps_cap")
        if base and base >= FRAMEGEN_MIN_BASE:
            lines["frame_gen"].append(
                f"Use the game's own frame generation if it has one. Otherwise lsfg-vk at 2x works from this base of "
                f"{base} fps."
            )
        elif base:
            lines["frame_gen"].append(
                f"Frame generation is not advised: a base of {base} fps is below the {FRAMEGEN_MIN_BASE} fps "
                "lsfg-vk needs to avoid visible artefacts."
            )
    if fg.get("tool"):
        fg_tool = tools.tool(fg["tool"])
        phrase = (fg_tool or {}).get("vocabulary", {}).get("framegen") if fg_tool else None
        lines["frame_gen"].append(phrase or f"Uses frame generation with {fg['tool']}.")
        if fg.get("requires"):
            lines["frame_gen"].append(f"Requires {(fg_tool or {}).get('name', fg['tool'])}.")

    in_game = rec.get("in_game") or {}
    if in_game.get("preset"):
        lines["in_game"].append(f"Graphics preset: {in_game['preset']}.")
    lines["battery"] = [] if device.get("mains_only") else battery_lines(rec, device)
    if device.get("mains_only") and device.get("generic"):
        # A mains-powered machine with no profile: its power limits are unknown, so no TDP is suggested (ADR-0049).
        lines["power"] = [MAINS_POWER_LINE]
    out = copy.deepcopy(rec)
    out["lines"] = lines
    out["matchLabel"] = MATCH_LABELS.get(rec["device_match"], rec["device_match"])
    return out


# Battery

MAINS_POWER_LINE = "This device runs on mains power and has no profile here, so no TDP is suggested."
NEAR_MATCHES = ("exact", "variant", "family")


def duration(minutes: float) -> str:
    hours, mins = divmod(round(minutes), 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def battery_lines(rec: dict[str, Any], device: dict[str, Any]) -> list[str]:
    """An estimate from the report's measured draw and this battery; no model links TDP to whole-device draw."""
    battery = rec.get("battery") or {}
    draw = battery.get("draw_w")
    if not isinstance(draw, (int, float)) or isinstance(draw, bool) or draw <= 0:
        return []
    where = rec.get("device_reported") or "the reporting device"
    wh = device.get("battery_wh")
    if device.get("generic") or not isinstance(wh, (int, float)) or isinstance(wh, bool) or wh <= 0:
        reported = battery.get("minutes")
        line = f"Reported battery draw {draw:g} W on {where}"
        return [line + (f", about {duration(reported)} on its battery." if reported else ".")]
    estimate = duration(wh * 60 / draw)
    if rec.get("device_match") in NEAR_MATCHES:
        return [f"Reported battery draw {draw:g} W. On your {wh:g} Wh battery that is about {estimate}."]
    return [
        f"Reported battery draw {draw:g} W on {where}. At the same draw, your {wh:g} Wh battery lasts "
        f"about {estimate}. Your screen and chip differ, so treat this as a rough guide."
    ]


# Fallback


def _below_native(resolution: Any, device: dict[str, Any]) -> bool:
    display = device.get("display") or {}
    try:
        width = int(str(resolution).split("x")[0])
    except (ValueError, IndexError):
        return False
    return bool(display.get("width")) and width < int(display["width"])


def render_advice(device: dict[str, Any], workload: str) -> tuple[str | None, str]:
    """Render resolution and gamescope filter for this panel (Keepsake addition, spec 8.1).

    A 2560x1600 panel takes exactly half resolution, 1280x800, with integer
    scaling for medium and heavy games, which stays sharp. A 1920x1200 or 1080
    panel stays native until heavy, then 1280x800 or 1280x720 with FSR. A
    1280x800 panel is always native.
    """
    display = device.get("display") or {}
    width, height = display.get("width"), display.get("height")
    if not width or not height:
        return None, "FSR" if workload == "heavy" else "Linear"
    if width >= 2560:
        if workload == "light":
            return f"{width}x{height}", "Linear"
        return f"{width // 2}x{height // 2}", "Integer"
    if width >= 1920:
        if workload == "heavy":
            return ("1280x800" if height >= 1200 else "1280x720"), "FSR"
        return f"{width}x{height}", "Linear"
    return f"{width}x{height}", "FSR" if workload == "heavy" else "Linear"


def fallback(device: dict[str, Any], workload: str) -> dict[str, Any]:
    workload = workload if workload in FPS_TARGETS else "medium"
    bands = device.get("tdp_bands_w") or {}
    display = device.get("display") or {}
    max_hz = display.get("refresh_hz_max") or 60
    target = FPS_TARGETS[workload]
    if display.get("vrr"):
        low, high = display.get("vrr_range_hz") or [30, max_hz]
        cap = max(low, min(target, high))
    else:
        cap = nearest_divisor(target, max_hz)
    resolution, steam_filter = render_advice(device, workload)
    notes = "General guidance for this device, not game-specific."
    if display.get("vrr"):
        notes += f" With VRR the screen follows the game, so any cap from {cap} up stays smooth."
    elif display.get("refresh_hz_max"):
        notes += f" Without VRR, a cap that divides {max_hz} Hz evenly keeps frame pacing smooth."
    if bands.get("derived"):
        notes += " TDP bands are derived from the device's TDP range."
    return {
        "source": "fallback",
        "source_url": "",
        "report_date": "",
        "votes": 0,
        "device_reported": "",
        "device_match": "generic",
        "confidence": "low",
        "workload": workload,
        "power": {"tdp_w": bands.get(workload), "gpu_clock_mhz": None},
        "display": {"refresh_hz": None, "fps_cap": cap, "vrr": True if display.get("vrr") else None},
        "scaling": {"steam_filter": steam_filter, "scaling_mode": None, "game_resolution": resolution},
        "upscaler": {"name": None, "mode": None},
        "frame_gen": {"tool": None, "mode": None},
        "in_game": {"preset": None, "settings": []},
        "compat": {"proton": None, "tool": None, "tool_version": None, "launch_options": None},
        "notes": notes,
    }


def build(
    reports: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    tools: Tools,
    device: dict[str, Any],
    selected: dict[str, str],
    workload: str,
    low_confidence_game: bool,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Source reports first, ranked, then the fallback last."""
    now = now or datetime.now(UTC)
    recs = []
    for rec in reports:
        rec = dict(rec)
        rec["device_match"] = device_match(
            profiles, rec.get("device_reported", ""), device, rec.get("apu_reported", "")
        )
        rec["confidence"] = confidence(rec, now, low_confidence_game)
        recs.append(rec)
    ranked = rank(recs, now)
    ranked.append(fallback(device, workload))
    return [translate(validate(r, device, selected), tools, device, selected) for r in ranked]
