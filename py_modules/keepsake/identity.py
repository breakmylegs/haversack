"""Cross-device game matching (ADR-0011).

The same game can be installed into differently numbered compatdata prefixes
and named differently on each device. Its cross-device identity is the game
key; this module finds the right key for a game when its title alone does not.

Signals, each scored separately:

* **exe**: the shortcut's executable name equals a manifest ``launch``
  executable or the exe another device recorded. Generic names such as
  ``game.exe`` count for little.
* **folder**: a folder on the way to the game (inside the prefix's
  ``drive_c``, or the last folders outside it) equals a manifest
  ``installDir`` or a folder another device recorded.
* **name**: the normalised shortcut name equals the title or another device's
  shortcut name (or shares most of its words).
* **saves**: the save folders another device syncs for that game (for
  example ``winLocalAppData/ExampleQuest/Saves``) exist inside this game's
  prefix. This is the strongest signal and works for games the manifest does
  not know.

A match is applied automatically only when it is strong, backed by two
independent signals and clearly ahead of the next candidate (fail closed);
otherwise candidates are offered as suggestions.
"""

from __future__ import annotations

import json
import os
import posixpath
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .manifest import game_key, normalise_title
from .store import AlreadyExistsError, NotFoundError, Store, StoreError

IDENTITY_SCHEMA = 1
GENERIC_EXES = frozenset(
    {
        "game.exe", "launcher.exe", "start.exe", "setup.exe", "play.exe", "run.exe", "main.exe", "app.exe",
        "client.exe", "bootstrap.exe", "launch.exe", "unitycrashhandler64.exe", "unitycrashhandler32.exe",
        "crashreporter.exe", "crashpad_handler.exe", "uninstall.exe", "unins000.exe",
    }
)  # fmt: skip
GENERIC_FOLDERS = frozenset(
    {
        "games", "game", "program files", "program files (x86)", "gog games", "gog galaxy", "bin", "binaries",
        "win64", "win32", "x64", "x86", "common", "steamapps", "drive_c", "users", "public", "appdata",
        "launcher", "data", "release", "shipping", "pfx", "steamuser", "documents", "my games", "saved games",
    }
)  # fmt: skip
WEIGHTS = {
    "exe": 3.0,
    "folder": 3.0,
    "name": 3.0,
    "name-partial": 1.0,
    "saves": 4.0,
    "saves-partial": 2.0,
    "exe-generic": 0.5,
}
AUTO_MIN_SCORE = 6.0
AUTO_MIN_SIGNALS = 2
AUTO_MIN_LEAD = 3.0
STRONG = frozenset({"exe", "folder", "name", "saves"})


def _norm_folder(name: str) -> str:
    return " ".join(name.lower().replace("_", " ").replace(".", " ").split())


def local_hints(game: Mapping[str, Any]) -> dict[str, Any]:
    """What this device knows about a game's installation, without absolute paths or IDs."""
    exe = game.get("exe_name") or None
    folders: list[str] = []
    base = str(game.get("base_dir") or "").replace("\\", "/")
    parts = [p for p in base.split("/") if p]
    if "drive_c" in [p.lower() for p in parts]:
        index = [p.lower() for p in parts].index("drive_c")
        parts = parts[index + 1 :]
    else:
        parts = parts[-2:]
    for part in parts:
        normalised = _norm_folder(part)
        if normalised and normalised not in GENERIC_FOLDERS and normalised not in folders:
            folders.append(normalised)
    return {
        "exe": str(exe).lower() if exe else None,
        "folders": folders,
        "name": normalise_title(str(game.get("name", ""))),
    }


def save_dirs(files_by_root: Mapping[str, Iterable[str]], depth: int = 2) -> list[str]:
    """``root/folder/folder`` for the folders holding a game's save files (relative, so safe for the cloud)."""
    out: set[str] = set()
    for root, rels in files_by_root.items():
        for rel in rels:
            folders = rel.split("/")[:-1]
            if folders:
                out.add(posixpath.join(root, *folders[:depth]))
    return sorted(out)


def identity_record(
    game_key_value: str,
    device_id: str,
    title: str | None,
    hints: Mapping[str, Any],
    dirs: list[str],
    now: float | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": IDENTITY_SCHEMA,
        "gameKey": game_key_value,
        "deviceId": device_id,
        "title": title,
        "exe": hints.get("exe"),
        "folders": list(hints.get("folders", []))[:8],
        "name": hints.get("name", "")[:200],
        "saveDirs": dirs[:40],
        "created": now if now is not None else time.time(),
    }


def identity_key(game_key_value: str, device_id: str) -> str:
    return f"games/{game_key_value}/identity/{device_id}.json"


def publish_identity(store: Store, record: Mapping[str, Any]) -> bool:
    """Write this device's identity record once. Returns True when it is in the cloud."""
    try:
        store.put_new(
            identity_key(record["gameKey"], record["deviceId"]), json.dumps(dict(record), sort_keys=True).encode()
        )
    except AlreadyExistsError:
        return True
    except StoreError:
        return False
    return True


def cloud_identities(store: Store) -> list[dict[str, Any]]:
    """Every device's identity records. Unreadable or malformed ones are skipped."""
    out: list[dict[str, Any]] = []
    for info in store.list("games/"):
        parts = info.key.split("/")
        if len(parts) != 4 or parts[2] != "identity" or not parts[3].endswith(".json"):
            continue
        try:
            record = json.loads(store.get(info.key).decode("utf-8"))
        except (ValueError, NotFoundError, StoreError):
            continue
        if isinstance(record, dict) and record.get("gameKey") == parts[1]:
            out.append(record)
    return out


# Scoring

Probe = Callable[[str], bool]  # does "root/folder/folder" exist for this game on this device?


def _add(candidates: dict[str, dict[str, Any]], key: str, title: str | None, signal: str, source: str) -> None:
    entry = candidates.setdefault(key, {"gameKey": key, "title": title, "signals": {}, "sources": set()})
    if title and not entry["title"]:
        entry["title"] = title
    entry["signals"][signal] = max(entry["signals"].get(signal, 0.0), WEIGHTS[signal])
    entry["sources"].add(source)


def _name_signal(a: str, b: str) -> str | None:
    if not a or not b:
        return None
    if a == b:
        return "name"
    wa, wb = set(a.split()), set(b.split())
    if wa and wb and len(wa & wb) / len(wa | wb) >= 0.5:
        return "name-partial"
    return None


def candidates(
    hints: Mapping[str, Any],
    index: Mapping[str, Any] | None,
    identities: Iterable[Mapping[str, Any]],
    probe: Probe | None,
    exclude_device: str | None = None,
) -> list[dict[str, Any]]:
    """Ranked candidate game keys with their score and the signals behind it."""
    found: dict[str, dict[str, Any]] = {}
    exe = hints.get("exe")
    folders = set(hints.get("folders", []))
    name = str(hints.get("name", ""))

    if index:
        for title, record in index.get("games", {}).items():
            key = game_key(title)
            if exe and exe in record.get("x", []):
                _add(found, key, title, "exe-generic" if exe in GENERIC_EXES else "exe", "manifest")
            if folders & {_norm_folder(d) for d in record.get("i", [])} - GENERIC_FOLDERS:
                _add(found, key, title, "folder", "manifest")
            signal = _name_signal(name, normalise_title(title))
            if signal:
                _add(found, key, title, signal, "manifest")

    for record in identities:
        if exclude_device and record.get("deviceId") == exclude_device:
            continue
        key = str(record.get("gameKey"))
        title = record.get("title") if isinstance(record.get("title"), str) else None
        other_exe = record.get("exe")
        if exe and other_exe and exe == other_exe:
            _add(found, key, title, "exe-generic" if exe in GENERIC_EXES else "exe", "other device")
        if folders & set(record.get("folders", [])):
            _add(found, key, title, "folder", "other device")
        signal = _name_signal(name, str(record.get("name", "")))
        if signal:
            _add(found, key, title, signal, "other device")
        dirs = [d for d in record.get("saveDirs", []) if isinstance(d, str)]
        if probe and dirs:
            present = sum(1 for d in dirs if probe(d))
            if present and present * 2 >= len(dirs):
                _add(found, key, title, "saves", "other device")
            elif present:
                _add(found, key, title, "saves-partial", "other device")

    ranked = []
    for entry in found.values():
        signals = entry["signals"]
        ranked.append({
            "gameKey": entry["gameKey"],
            "title": entry["title"],
            "score": round(sum(signals.values()), 2),
            "signals": sorted(signals),
            "strongSignals": len(STRONG & set(signals)),
            "sources": sorted(entry["sources"]),
        })  # fmt: skip
    ranked.sort(key=lambda c: (-c["score"], c["gameKey"]))
    return ranked


def automatic_choice(ranked: list[dict[str, Any]], taken: set[str]) -> dict[str, Any] | None:
    """The candidate to apply without asking, or None (then the list is only suggested)."""
    if not ranked:
        return None
    best = ranked[0]
    runner_up = ranked[1]["score"] if len(ranked) > 1 else 0.0
    if (
        best["score"] >= AUTO_MIN_SCORE
        and best["strongSignals"] >= AUTO_MIN_SIGNALS
        and best["score"] - runner_up >= AUTO_MIN_LEAD
        and best["gameKey"] not in taken
    ):
        return best
    return None


PROPOSE_MIN_SCORE = 3.0


def proposal(ranked: list[dict[str, Any]], taken: set[str], rejected: set[str]) -> dict[str, Any] | None:
    """A likely but uncertain match for the user to approve, with the alternatives (Peter, 15 November 2026).

    Used when :func:`automatic_choice` declines. Candidates the user said
    "not this game" to, or keys used by another game here, are skipped.
    """
    usable = [c for c in ranked if c["gameKey"] not in rejected and c["gameKey"] not in taken]
    if not usable or usable[0]["score"] < PROPOSE_MIN_SCORE:
        return None
    return {"candidate": usable[0], "alternatives": usable[1:5]}


def probe_for(
    roots: Mapping[str, str | None], insensitive: Callable[[str], bool], expand: Callable[[str, str, bool], list[str]]
) -> Probe:
    """A probe that checks ``root/folder/folder`` inside this game's own logical roots only."""

    def probe(entry: str) -> bool:
        root_name, _, rel = entry.partition("/")
        root = roots.get(root_name)
        if not root or not rel or not os.path.isdir(root):
            return False
        return bool(expand(root, rel, insensitive(root_name)))

    return probe
