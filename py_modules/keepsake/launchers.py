"""Games from other launchers, and emulator saves (ADR-0051, R4).

Read-only discovery of:

- **Heroic** (GOG and Epic): ``gog_store/installed.json`` with titles from
  ``store_cache/gog_library.json`` (or the older ``gog_store/library.json``); Legendary's
  ``installed.json``; the Wine prefix from ``GamesConfig/<appName>.json`` (``winePrefix``,
  ``wineVersion.type``). Native and Flatpak installs.
- **Lutris**: ``games/*.yml`` (``name``, ``game.prefix``, ``game.exe``, ``game.working_dir``),
  with ``pga.db`` used for the name when ``sqlite3`` is there.
- **Bottles**: each bottle's ``bottle.yml`` ``External_Programs`` (``name``, ``path``); the
  bottle folder is the Wine prefix. Native and Flatpak installs.
- **Emulators** (``data/emulators.json``): save folders of the Flatpak and AppImage builds
  EmuDeck installs, as one entry per emulator with a fixed game key on every device.

Formats follow Ludusavi's readers (MIT) and each launcher's files; nothing is written.
Every path stays on this device; snapshots only see logical roots (P10).
"""

from __future__ import annotations

import glob
import json
import os
import re
from collections.abc import Iterable, Mapping
from typing import Any

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "emulators.json")
HEROIC_DIRS = (".config/heroic", ".var/app/com.heroicgameslauncher.hgl/config/heroic")
LEGENDARY_DIRS = (
    ".config/legendary",
    ".config/heroic/legendaryConfig/legendary",
    ".var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary",
)
LUTRIS_CONFIG_DIRS = (".config/lutris/games", ".local/share/lutris/games")
LUTRIS_DB = ".local/share/lutris/pga.db"
BOTTLES_DIRS = (".local/share/bottles/bottles", ".var/app/com.usebottles.bottles/data/bottles/bottles")
LAUNCHER_KINDS = ("heroic", "lutris", "bottles")
EMULATOR_KIND = "emulator"
_KEY_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _under(home: str, rel: str) -> str:
    """``rel`` (written with ``/``) inside ``home``, with this system's separators."""
    return os.path.join(home, *rel.split("/"))


def _entry(key: str, kind: str, name: str, **extra: Any) -> dict[str, Any]:
    """A game in the shape discovery uses (``discovery.GameEntry``), plus the launcher's own fields."""
    return {
        "key": key,
        "kind": kind,
        "appid": 0,
        "name": name,
        "user_id": None,
        "is_default_user": True,
        "prefix": None,
        "prefix_library_index": None,
        "base_dir": None,
        "exe_inside_prefix": False,
        "last_played": 0,
        "notes": [],
        "steam_root": None,
        "default_user": None,
        "exe_name": None,
        "exe": None,
        "start_dir": None,
        "launch_options": "",
        "compat_tool": None,
        "artwork": [],
        "icon": "",
        "os": "linux",
        **extra,
    }


def _json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def wine_user(prefix: str) -> str | None:
    """The Windows user folder inside a Wine prefix: ``steamuser`` under Proton, the Linux user under Wine."""
    users = os.path.join(prefix, "drive_c", "users")
    try:
        names = sorted(n for n in os.listdir(users) if n.lower() != "public" and os.path.isdir(os.path.join(users, n)))
    except OSError:
        return None
    if "steamuser" in names:
        return "steamuser"
    return names[0] if len(names) == 1 else None  # several users: uncertain, so none (fail closed)


def _wine_fields(prefix: str | None) -> dict[str, Any]:
    """``prefix`` for a Proton prefix (holding ``pfx``), ``wine_prefix`` for a plain one (holding ``drive_c``)."""
    if not prefix:
        return {}
    if os.path.isdir(os.path.join(prefix, "pfx", "drive_c")):
        return {"prefix": prefix}
    if os.path.isdir(os.path.join(prefix, "drive_c")):
        return {"wine_prefix": prefix, "wine_user": wine_user(prefix)}
    return {}


# Heroic


def heroic_games(home: str) -> list[dict[str, Any]]:
    games: dict[str, dict[str, Any]] = {}
    for rel in HEROIC_DIRS:
        root = _under(home, rel)
        if not os.path.isdir(root):
            continue
        configs: dict[str, Any] = {}

        def prefix_for(app: str, root: str = root, configs: dict[str, Any] = configs) -> str | None:
            if app not in configs:
                data = _json(os.path.join(root, "GamesConfig", f"{app}.json"))
                configs[app] = data.get(app) if isinstance(data, dict) else None
            config = configs[app]
            if not isinstance(config, dict):
                return None
            kind = str((config.get("wineVersion") or {}).get("type", ""))
            prefix = config.get("winePrefix")
            return str(prefix) if kind in ("wine", "proton") and isinstance(prefix, str) and prefix else None

        titles: dict[str, str] = {}
        for library in ("store_cache/gog_library.json", "gog_store/library.json"):
            data = _json(os.path.join(root, library))
            if isinstance(data, dict) and isinstance(data.get("games"), list):
                for item in data["games"]:
                    if isinstance(item, dict) and item.get("title"):
                        app = str(item.get("app_name") or item.get("appName") or "")
                        titles.setdefault(app, str(item["title"]))
                break
        installed = _json(os.path.join(root, "gog_store", "installed.json"))
        for item in (installed or {}).get("installed", []) if isinstance(installed, dict) else []:
            if not isinstance(item, dict) or str(item.get("platform", "")).lower() != "windows":
                continue
            app = str(item.get("appName") or "")
            if app and app in titles:
                games.setdefault(f"heroic:gog:{app}", _heroic_entry("gog", app, titles[app], item, prefix_for(app)))
        for legendary in LEGENDARY_DIRS:
            data = _json(os.path.join(_under(home, legendary), "installed.json"))
            if not isinstance(data, dict):
                continue
            for app, item in data.items():
                if isinstance(item, dict) and item.get("title") and str(item.get("platform", "")).lower() == "windows":
                    key = f"heroic:epic:{app}"
                    games.setdefault(
                        key, _heroic_entry("epic", str(app), str(item["title"]), item, prefix_for(str(app)))
                    )
    return list(games.values())


def _heroic_entry(store: str, app: str, title: str, item: Mapping[str, Any], prefix: str | None) -> dict[str, Any]:
    entry = _entry(f"heroic:{store}:{app}", "heroic", title, launcher_store=store, **_wine_fields(prefix))
    install = item.get("install_path")
    if isinstance(install, str) and install:
        entry["base_dir"] = install
    entry["notes"] = [
        f"Heroic can also sync this game's saves with {'GOG' if store == 'gog' else 'Epic'}; use one or the other"
    ]
    return entry


# Lutris (and a small YAML reader for the simple files Lutris and Bottles write)


def simple_yaml(text: str) -> dict[str, Any]:
    """Nested mappings of plain scalars, enough for Lutris game files and Bottles' ``bottle.yml``.

    Lists, anchors and multi-line values are skipped rather than guessed (fail closed).
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith(("#", "- ")) or raw.strip() == "-":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().strip("'\""), value.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            break
        parent = stack[-1][1]
        if value in ("", "|", ">"):
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            parent[key] = value
    return root


def lutris_games(home: str, names_from_db: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    names = dict(names_from_db) if names_from_db is not None else lutris_db_names(_under(home, LUTRIS_DB))
    games: dict[str, dict[str, Any]] = {}
    for rel in LUTRIS_CONFIG_DIRS:
        for path in sorted(glob.glob(os.path.join(_under(home, rel), "*.y*ml"))):
            try:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    spec = simple_yaml(handle.read(256 * 1024))
            except OSError:
                continue
            ident = os.path.splitext(os.path.basename(path))[0]
            raw = spec.get("game")
            game: dict[str, Any] = raw if isinstance(raw, dict) else {}
            prefix = game.get("prefix")
            name = names.get(ident) or spec.get("name") or ""
            if not prefix or not name:
                continue  # only Wine games with a known name
            entry = _entry(f"lutris:{_KEY_SAFE.sub('_', ident)}", "lutris", str(name), **_wine_fields(str(prefix)))
            base = game.get("working_dir") or (os.path.dirname(str(game["exe"])) if game.get("exe") else None)
            if base and os.path.isabs(str(base)):
                entry["base_dir"] = str(base)
            games.setdefault(entry["key"], entry)
    return list(games.values())


def lutris_db_names(db_path: str) -> dict[str, str]:
    """``configpath -> name`` from Lutris' database, read-only; empty when ``sqlite3`` or the file is missing."""
    if not os.path.isfile(db_path):
        return {}
    try:
        import sqlite3  # may be missing from Decky's frozen Python (ADR-0030)
    except ImportError:
        return {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            rows = db.execute("SELECT name, configpath FROM games WHERE configpath IS NOT NULL").fetchall()
    except sqlite3.Error:
        return {}
    return {str(path): str(name) for name, path in rows if name and path}


# Bottles


def bottles_programs(home: str) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for rel in BOTTLES_DIRS:
        for bottle_yml in sorted(glob.glob(os.path.join(_under(home, rel), "*", "bottle.yml"))):
            bottle = os.path.dirname(bottle_yml)
            try:
                with open(bottle_yml, encoding="utf-8", errors="replace") as handle:
                    spec = simple_yaml(handle.read(512 * 1024))
            except OSError:
                continue
            programs = spec.get("External_Programs")
            if not isinstance(programs, dict):
                continue
            for ident, program in sorted(programs.items()):
                if not isinstance(program, dict) or not program.get("name"):
                    continue
                key = f"bottles:{_KEY_SAFE.sub('_', os.path.basename(bottle))}:{_KEY_SAFE.sub('_', str(ident))}"
                games.append(_entry(key, "bottles", str(program["name"]), **_wine_fields(bottle)))
    return games


# Emulators


def load_emulators(path: str = DATA_FILE) -> list[dict[str, Any]]:
    data = _json(path)
    return list(data.get("emulators", [])) if isinstance(data, dict) else []


def emulator_entries(home: str, profiles: Iterable[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """One entry per emulator whose save folder exists here. Its game key is the same on every device."""
    out = []
    for profile in profiles if profiles is not None else load_emulators():
        paths = [p for p in profile.get("saves", []) if os.path.isdir(_under(home, p["rel"]))]
        if not paths:
            continue
        out.append(
            _entry(
                f"emulator:{profile['id']}",
                EMULATOR_KIND,
                f"Emulator saves: {profile['name']}",
                emulator=profile["id"],
                emulator_paths=[{"root": p["root"], "rel": p["rel"]} for p in paths],
                states_paths=[{"root": p["root"], "rel": p["rel"]} for p in profile.get("states", [])],
                flatpak_id=profile.get("flatpak"),
                process_names=list(profile.get("process_names", [])),
            )
        )
    return out


def emulator_game_key(entry: Mapping[str, Any]) -> str:
    return f"emulator-{entry['emulator']}"


def discover_all(home: str) -> list[dict[str, Any]]:
    """Every launcher game and emulator on this Linux device. A failing launcher never hides the others."""
    found: list[dict[str, Any]] = []
    for reader in (heroic_games, lutris_games, bottles_programs, emulator_entries):
        try:
            found.extend(reader(home))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found
