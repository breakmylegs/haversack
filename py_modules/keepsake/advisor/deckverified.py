"""Deck Verified (DeckSettings) community reports (v2 spec 8.1, ADR-0028).

GET ``https://deckverified.games/deck-verified/api/v1/game_details?appid=<id>``,
or ``?name=<game name>`` for a shortcut with no Steam app ID. 204 means nothing
known; the service allows 120 requests per IP per 2 minutes. Report data is
GPL-3.0: it is shown with a link to each report, cached on the device and
never committed or bulk copied.

Report text is untrusted community input. It is shown, never executed.
Parsing is ported from Tuning Advisor (ADR-0013); the HTTP layer is Keepsake's
``net`` (allowlist, no credentials, size cap).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from .. import net

HOST = "deckverified.games"
URL = f"https://{HOST}/deck-verified/api/v1/game_details"
SOURCE = "deckverified"
SITE = f"https://{HOST}"
ATTRIBUTION = "Community reports from Deck Verified by DeckSettings (report data GPL-3.0)."
MAX_TEXT = 400
MAX_SETTINGS = 12
MAX_BYTES = 4 * 1024 * 1024


class SourceError(Exception):
    """A source could not answer; ``hint`` is shown to the user."""

    def __init__(self, hint: str) -> None:
        super().__init__(hint)
        self.hint = hint


def fetch(appid: int | None, name: str | None, fetcher: Callable[..., net.HttpResponse] = net.fetch) -> dict[str, Any]:
    """Blocking. The raw reply, or an empty one on 204."""
    if appid:
        query = {"appid": str(int(appid))}
    elif name:
        query = {"name": name[:200]}
    else:
        raise ValueError("appid or name is required")
    try:
        response = fetcher(
            f"{URL}?{urlencode(query)}",
            headers={"Accept": "application/json"},
            max_bytes=MAX_BYTES,
            allowed=frozenset({HOST}),
        )
    except net.NetError as exc:
        raise SourceError("Deck Verified could not be reached. Cached reports are shown if there are any.") from exc
    if response.status == 204:
        return {"reports": []}
    if response.status in (403, 429):
        raise SourceError(f"Deck Verified turned the request away (HTTP {response.status}). Try Refresh later.")
    if response.status != 200:
        raise SourceError(f"Deck Verified answered HTTP {response.status}.")
    try:
        data = json.loads(response.body)
    except ValueError as exc:
        raise SourceError("Deck Verified sent an answer Keepsake cannot read.") from exc
    if not isinstance(data, dict):
        raise SourceError("Deck Verified sent an answer Keepsake cannot read.")
    return data


# Normalising


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if math.isfinite(value) else None  # NaN and infinity are not numbers of anything
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _watts(value: Any) -> float | None:
    """Whole-device battery draw; values a handheld cannot draw are dropped."""
    if isinstance(value, bool) or value is None:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    watts = float(match.group(0))
    return watts if 1 <= watts <= 80 else None


def _on(value: Any) -> bool | None:
    text = str(value or "").strip().casefold()
    if text in ("on", "yes", "true", "enabled"):
        return True
    if text in ("off", "no", "false", "disabled"):
        return False
    return None


SETTING_RE = re.compile(r"^\s*(?:[-*+]\s*)?\**\s*([^:*|#][^:*|]{0,60}?)\s*\**\s*:\s*\**\s*(.{1,80}?)\s*\**\s*$")
PRESET_NAMES = ("preset", "quick preset", "graphics preset", "quality preset", "graphics quality", "quality")
UPSCALER_RE = re.compile(
    r"\b(FidelityFX Super Resolution ?[1-4]?(?:\.\d)?|FSR ?[1-4](?:\.\d)?|FSR|DLSS"
    r"|XeSS(?: Super Resolution)?|TAAU|TSR)\b",
    re.I,
)


def upscaler_name(raw: str) -> str:
    text = raw.strip()
    lower = text.casefold().replace(" ", "")
    lower = lower.replace("fidelityfxsuperresolution", "fsr").replace("xesssuperresolution", "xess")
    if lower.startswith("fsr"):
        return ("FSR " + lower[3:]).strip()
    return {"dlss": "DLSS", "xess": "XeSS", "taau": "TAAU", "tsr": "TSR"}.get(lower, text)


def parse_settings(markdown: Any) -> list[dict[str, str]]:
    """``Name: Value`` lines from a report's settings Markdown."""
    out: list[dict[str, str]] = []
    for line in str(markdown or "").splitlines():
        match = SETTING_RE.match(line)
        if not match:
            continue
        name, value = match.group(1).strip(), match.group(2).strip()
        if name and value and not name.startswith("http"):
            out.append({"name": _text(name, 60), "value": _text(value, 80)})
        if len(out) >= MAX_SETTINGS:
            break
    return out


def frame_gen_from_launch(options: str) -> str | None:
    if "~/lsfg" in options or "lsfg" in options.split():
        return "lsfg-vk"
    if "fgmod" in options:
        return "optiscaler"
    return None


def report_device(report: dict[str, Any]) -> str:
    data = report.get("data")
    device = _text(data.get("device"), 80) if isinstance(data, dict) else ""
    if device:
        return device
    labels = report.get("labels")
    for label in labels if isinstance(labels, list) else []:
        name = str(label.get("name") or "") if isinstance(label, dict) else ""
        if name.startswith("DEVICE: "):
            return name[len("DEVICE: ") :]
    return ""


def _url(value: Any) -> str:
    text = str(value or "")
    return text[:300] if text.startswith("https://github.com/") else ""


def normalise(report: dict[str, Any]) -> dict[str, Any]:
    data = report.get("data") or {}
    data = data if isinstance(data, dict) else {}
    reactions = report.get("reactions") or {}
    reactions = reactions if isinstance(reactions, dict) else {}
    graphics = parse_settings(data.get("game_graphics_settings"))
    display_settings = parse_settings(data.get("game_display_settings"))
    settings = graphics + [s for s in display_settings if s not in graphics]
    preset = next((s["value"] for s in settings if s["name"].casefold() in PRESET_NAMES), None)
    upscaler = None
    for s in settings:
        hit = UPSCALER_RE.search(f"{s['name']} {s['value']}")
        if hit:
            upscaler = {"name": upscaler_name(hit.group(1)), "mode": s["value"]}
            break
    launch = _text(data.get("custom_launch_options"), 200)
    fps_cap = _int(data.get("frame_limit"))
    if _on(data.get("disable_frame_limit")) is True:
        fps_cap = None
    tool = _text(data.get("steam_play_compatibility_tool_used"), 60)
    version = _text(data.get("compatibility_tool_version"), 40)
    notes = " ".join(p for p in (_text(data.get("summary")), _text(data.get("additional_notes"))) if p)
    resolution = _text(data.get("game_resolution"), 30)
    return {
        "source": SOURCE,
        "source_url": _url(report.get("html_url")),
        "report_title": _text(report.get("title"), 120),
        "report_date": str(report.get("updated_at") or report.get("created_at") or ""),
        "votes": (_int(reactions.get("reactions_thumbs_up")) or 0)
        - (_int(reactions.get("reactions_thumbs_down")) or 0),
        "device_reported": report_device(report),
        "device_match": "other_handheld",
        "confidence": "low",
        "power": {"tdp_w": _int(data.get("tdp_limit")), "gpu_clock_mhz": _int(data.get("manual_gpu_clock"))},
        "display": {"refresh_hz": None, "fps_cap": fps_cap, "vrr": _on(data.get("enable_vrr"))},
        "scaling": {
            "steam_filter": _text(data.get("scaling_filter"), 30) or None,
            "scaling_mode": _text(data.get("scaling_mode"), 30) or None,
            "game_resolution": None if resolution.casefold() in ("", "default") else resolution,
        },
        "upscaler": upscaler or {"name": None, "mode": None},
        "frame_gen": {"tool": frame_gen_from_launch(launch), "mode": None},
        "in_game": {"preset": preset, "settings": settings},
        "compat": {
            "proton": " ".join(p for p in (tool, version) if p) or None,
            "tool": tool or None,
            "tool_version": version or None,
            "launch_options": launch or None,
        },
        "battery": {
            "draw_w": _watts(data.get("average_battery_power_draw")),
            "minutes": _int(data.get("calculated_battery_life_minutes")),
        },
        "rating": _text(data.get("performance_rating"), 30) or None,
        "target_fps": _text(data.get("target_framerate"), 30) or None,
        "notes": notes,
    }


def parse_date(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
