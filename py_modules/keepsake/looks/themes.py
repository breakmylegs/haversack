"""What the theme plugins have installed, read only (R29 stage 1, ADR-0091).

Haversack does not inject themes or sounds itself: CSS Loader and Audio Loader do that well, and two
injectors would fight over the same windows. It finds them and what they hold, so the Looks page can
say what is installed and point to them:

- plugins: ``<homebrew>/plugins/*/plugin.json``, matched by their ``name``;
- CSS Loader themes: ``<homebrew>/themes/<folder>/theme.json`` (``name``, ``author``, ``version``);
- Audio Loader sound packs: ``<homebrew>/sounds/<folder>/pack.json`` (``name``, ``author``, ``music``).

Every file is read with a size limit and every field is cut short, so a broken or hostile theme folder
cannot slow the page down or fill it.
"""

from __future__ import annotations

import json
import os
from typing import Any

PLUGINS = {"CSS Loader": "css", "Audio Loader": "audio", "Animation Changer": "animations"}
MAX_JSON = 256 * 1024
MAX_ITEMS = 300


def _read(path: str) -> dict[str, Any]:
    try:
        if os.path.islink(path) or os.path.getsize(path) > MAX_JSON:
            return {}
        with open(path, encoding="utf-8") as handle:
            found = json.load(handle)
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError, UnicodeDecodeError):
        return {}


def _text(value: Any, limit: int = 80) -> str:
    return str(value)[:limit] if isinstance(value, (str, int, float)) else ""


def installed_plugins(homebrew: str) -> dict[str, bool]:
    """Which of the theme plugins are installed: {"css": bool, "audio": bool, "animations": bool}."""
    found = dict.fromkeys(PLUGINS.values(), False)
    folder = os.path.join(homebrew, "plugins")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return found
    for name in names:
        key = PLUGINS.get(_text(_read(os.path.join(folder, name, "plugin.json")).get("name")))
        if key:
            found[key] = True
    return found


def _packs(folder: str, manifest: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in names:
        path = os.path.join(folder, name)
        if os.path.islink(path) or not os.path.isdir(path):
            continue
        data = _read(os.path.join(path, manifest))
        if not data:
            continue
        item: dict[str, Any] = {"name": _text(data.get("name")) or _text(name), "author": _text(data.get("author"))}
        if manifest == "theme.json":
            item["version"] = _text(data.get("version"), 20)
            item["preset"] = "PRESET" in [str(f) for f in data.get("flags", []) if isinstance(data.get("flags"), list)]
        else:
            item["music"] = bool(data.get("music"))
        out.append(item)
        if len(out) >= MAX_ITEMS:
            break
    return out


def summary(homebrew: str) -> dict[str, Any]:
    """The theme plugins, themes and sound packs on this device."""
    return {
        "plugins": installed_plugins(homebrew),
        "themes": _packs(os.path.join(homebrew, "themes"), "theme.json"),
        "sounds": _packs(os.path.join(homebrew, "sounds"), "pack.json"),
    }
