"""Ludusavi manifest: download, compact index, title matching.

Save location data comes from the Ludusavi Manifest
(https://github.com/mtkennerly/ludusavi-manifest, MIT licence), compiled from
PCGamingWiki. The full YAML (about 18 MB) is streamed to a temporary file,
parsed one entry at a time and reduced to a compact JSON index; the YAML is
then deleted.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any

from .fsutil import atomic_write_json, read_json
from .net import NetError, check_url, fetch_to_file
from .yamlsubset import YamlSubsetError, iter_entries

# The README names the data branch as the current source; master "will stop
# being updated eventually" (assumption A42).
MANIFEST_URL = "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/refs/heads/data/data/manifest.yaml"
INDEX_FILE = "manifest-index.json"
INDEX_SCHEMA = 1
REFRESH_SECONDS = 7 * 24 * 60 * 60
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
ATTRIBUTION = "Save locations from the Ludusavi Manifest (MIT), compiled from PCGamingWiki."

_TAGS = {"save": "s", "config": "c"}


# Titles


_ROMAN = {
    "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
    "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15", "xvi": "16", "xvii": "17", "xviii": "18",
    "xix": "19", "xx": "20",
}  # fmt: skip
_EDITION_SUFFIXES = [
    "game of the year edition",
    "game of the year",
    "goty edition",
    "goty",
    "definitive edition",
    "complete edition",
    "deluxe edition",
    "gold edition",
    "enhanced edition",
    "special edition",
    "ultimate edition",
    "anniversary edition",
    "standard edition",
    "digital deluxe edition",
]
_EDITION_SUFFIXES.sort(key=len, reverse=True)


def normalise_title(title: str) -> str:
    """Normalise a title for matching: case, punctuation, edition suffixes, roman numerals."""
    # Strip trade marks before NFKD, which would turn the trade mark sign into "TM".
    text = re.sub("['\\u2019\\u2122\\u00ae\\u00a9]", "", title)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [_ROMAN.get(t, t) for t in text.split()]
    joined = " ".join(tokens)
    changed = True
    while changed:
        changed = False
        for suffix in _EDITION_SUFFIXES:
            if joined.endswith(" " + suffix):
                joined = joined[: -len(suffix) - 1]
                changed = True
    if joined.startswith("the "):
        joined = joined[4:]
    return joined.strip()


def game_key(title: str) -> str:
    """Cross-device identity: a slug of the manifest title, e.g. ``goat-simulator-3``."""
    text = unicodedata.normalize("NFKD", title)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:100] or "game"


# Index building


def _compact_whens(value: Any) -> list[list[str | None]]:
    out: list[list[str | None]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                os_name = item.get("os")
                store = item.get("store")
                out.append([str(os_name) if os_name is not None else None, str(store) if store is not None else None])
    return out


def _compact_paths(value: Any) -> list[list[Any]]:
    """``{path: {tags, when}}`` to ``[[path, "s"|"c"|"sc", whens], ...]``, keeping only save and config."""
    out: list[list[Any]] = []
    if not isinstance(value, dict):
        return out
    for path, info in value.items():
        info = info if isinstance(info, dict) else {}
        raw_tags = info.get("tags")
        tags: list[Any] = raw_tags if isinstance(raw_tags, list) else []
        code = "".join(sorted({_TAGS[t] for t in tags if t in _TAGS}, key="sc".index))
        if code:
            out.append([str(path), code, _compact_whens(info.get("when"))])
    return out


def build_index(lines: Iterable[str], etag: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    games: dict[str, Any] = {}
    aliases: dict[str, str] = {}
    steam_no_data: list[int] = []
    skipped: list[str] = []
    skipped_count = 0
    total = 0
    for title, entry in iter_entries(lines):
        total += 1
        if isinstance(entry, YamlSubsetError) or not isinstance(entry, dict):
            skipped_count += 1
            if len(skipped) < 50:
                skipped.append(title)
            continue
        alias = entry.get("alias")
        if isinstance(alias, str) and alias:
            aliases[title] = alias
            continue
        files = _compact_paths(entry.get("files"))
        registry = _compact_paths(entry.get("registry"))
        steam = entry.get("steam") if isinstance(entry.get("steam"), dict) else {}
        steam_id = steam.get("id") if isinstance(steam.get("id"), int) else None
        if not files and not registry:
            if steam_id is not None:
                steam_no_data.append(steam_id)
            continue
        ids = entry.get("id") if isinstance(entry.get("id"), dict) else {}
        steam_extra = ids.get("steamExtra") if isinstance(ids, dict) else None
        extra = [i for i in steam_extra if isinstance(i, int)] if isinstance(steam_extra, list) else []
        install = entry.get("installDir") if isinstance(entry.get("installDir"), dict) else {}
        cloud = entry.get("cloud") if isinstance(entry.get("cloud"), dict) else {}
        record: dict[str, Any] = {"f": files}
        if registry:
            record["r"] = registry
        if steam_id is not None:
            record["s"] = steam_id
        if extra:
            record["se"] = extra
        if install:
            record["i"] = [str(k) for k in install]
        if cloud.get("steam") is True:
            record["cs"] = True
        games[title] = record

    steam_map: dict[str, str] = {}
    titles: dict[str, list[str]] = {}
    for title, record in games.items():
        for sid in [record.get("s"), *record.get("se", [])]:
            if isinstance(sid, int):
                steam_map.setdefault(str(sid), title)
        titles.setdefault(normalise_title(title), []).append(title)
    for alias, target in aliases.items():
        if target in games:
            titles.setdefault(normalise_title(alias), []).append(target)
    for names in titles.values():
        names.sort()
    return {
        "schema": INDEX_SCHEMA,
        "source": MANIFEST_URL,
        "etag": etag,
        "fetched": time.time(),
        "parseSeconds": round(time.perf_counter() - started, 2),
        "entries": total,
        "skipped": skipped_count,
        "skippedTitles": skipped,
        "games": games,
        "aliases": aliases,
        "steam": steam_map,
        "steamNoData": sorted(set(steam_no_data)),
        "titles": titles,
    }


def peak_rss_mb() -> float | None:
    try:
        import resource
    except ImportError:
        return None
    getrusage = getattr(resource, "getrusage", None)
    rusage_self = getattr(resource, "RUSAGE_SELF", None)
    if getrusage is None or rusage_self is None:
        return None
    # ru_maxrss is in KiB on Linux.
    return round(float(getrusage(rusage_self).ru_maxrss) / 1024, 1)


# Storage and refresh

Downloader = Callable[..., Any]


class ManifestStore:
    def __init__(self, runtime_dir: str, download: Downloader = fetch_to_file, clock: Callable[[], float] = time.time):
        self.runtime_dir = runtime_dir
        self._path = os.path.join(runtime_dir, INDEX_FILE)
        self._download = download
        self._clock = clock
        self._cache: dict[str, Any] | None = None

    def load(self) -> dict[str, Any] | None:
        if self._cache is None:
            try:
                data = read_json(self._path, default=None)
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict) and data.get("schema") == INDEX_SCHEMA:
                self._cache = data
        return self._cache

    def status(self) -> dict[str, Any]:
        index = self.load()
        if index is None:
            return {"available": False, "attribution": ATTRIBUTION}
        return {
            "available": True,
            "fetched": index.get("fetched"),
            "games": len(index.get("games", {})),
            "entries": index.get("entries"),
            "skipped": index.get("skipped"),
            "parseSeconds": index.get("parseSeconds"),
            "peakRssMb": index.get("peakRssMb"),
            "stale": self._clock() - float(index.get("fetched") or 0) >= REFRESH_SECONDS,
            "attribution": ATTRIBUTION,
        }

    def refresh(self, force: bool = False) -> dict[str, Any]:
        """Download and index the manifest if missing, a week old, or ``force``. Quiet on failure."""
        index = self.load()
        if index is not None and not force and self._clock() - float(index.get("fetched") or 0) < REFRESH_SECONDS:
            return {"ok": True, "changed": False, "reason": "fresh"}
        headers = {"Accept": "text/plain"}
        if index is not None and index.get("etag"):
            headers["If-None-Match"] = str(index["etag"])
        fd, tmp = tempfile.mkstemp(prefix=".manifest-", suffix=".yaml", dir=self.runtime_dir)
        os.close(fd)
        try:
            check_url(MANIFEST_URL)
            response = self._download(MANIFEST_URL, tmp, headers=headers, max_bytes=MAX_MANIFEST_BYTES)
            if response.status == 304 and index is not None:
                index["fetched"] = self._clock()
                atomic_write_json(self._path, index)
                return {"ok": True, "changed": False, "reason": "not-modified"}
            if response.status != 200:
                return {"ok": False, "reason": f"http-{response.status}"}
            with open(tmp, encoding="utf-8", errors="replace") as handle:
                new_index = build_index(handle, etag=response.headers.get("etag"))
            new_index["fetched"] = self._clock()
            new_index["peakRssMb"] = peak_rss_mb()
            if not new_index["games"]:
                # An empty result means the format changed or the download was wrong: keep the old index.
                return {"ok": False, "reason": "empty-index"}
            atomic_write_json(self._path, new_index, mode=0o644)
            self._cache = new_index
            return {
                "ok": True,
                "changed": True,
                "games": len(new_index["games"]),
                "parseSeconds": new_index["parseSeconds"],
                "peakRssMb": new_index["peakRssMb"],
            }
        except NetError as exc:
            return {"ok": False, "reason": "offline", "detail": str(exc)}
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    def import_file(self, path: str, etag: str | None = None) -> dict[str, Any]:
        """Index a local manifest file (tests and offline setup)."""
        with open(path, encoding="utf-8", errors="replace") as handle:
            index = build_index(handle, etag=etag)
        index["fetched"] = self._clock()
        atomic_write_json(self._path, index, mode=0o644)
        self._cache = index
        return index


# Matching


def match_steam(index: dict[str, Any], appid: int) -> str | None:
    title = index.get("steam", {}).get(str(appid))
    return title if isinstance(title, str) else None


def match_title(index: dict[str, Any], name: str, aliases: Iterable[str] = ()) -> list[str]:
    """Titles whose normalised form equals the normalised ``name`` or a user alias."""
    titles = index.get("titles", {})
    found: list[str] = []
    for candidate in [name, *aliases]:
        for title in titles.get(normalise_title(candidate), []):
            if title not in found:
                found.append(title)
    return found


def match_game(index: dict[str, Any] | None, game: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Decide which manifest entry a discovered game uses.

    Order: the user's manual pick, then the Steam ID for Steam apps, then the
    normalised title and aliases. Several title matches are reported as
    ambiguous with candidates rather than guessed.
    """
    if index is None:
        return {"method": "no-manifest", "title": None, "gameKey": None, "candidates": []}
    games = index.get("games", {})
    manual = config.get("matchTitle")
    if isinstance(manual, str) and manual in games:
        return {"method": "manual", "title": manual, "gameKey": game_key(manual), "candidates": []}
    if game.get("kind") == "steam":
        title = match_steam(index, int(game.get("appid", 0)))
        if title:
            return {"method": "steam-id", "title": title, "gameKey": game_key(title), "candidates": []}
        if int(game.get("appid", 0)) in set(index.get("steamNoData", [])):
            return {"method": "no-save-data", "title": None, "gameKey": None, "candidates": []}
    found = match_title(index, str(game.get("name", "")), config.get("aliases", []))
    if len(found) == 1:
        return {"method": "title", "title": found[0], "gameKey": game_key(found[0]), "candidates": []}
    if found:
        return {"method": "ambiguous", "title": None, "gameKey": None, "candidates": found[:10]}
    return {
        "method": "none",
        "title": None,
        "gameKey": None,
        "candidates": search_titles(index, str(game.get("name", "")), 5),
    }


def search_titles(index: dict[str, Any], query: str, limit: int = 20) -> list[str]:
    """Rank manifest titles by shared words with ``query`` (for "Change match")."""
    words = set(normalise_title(query).split())
    if not words:
        return []
    scored: list[tuple[float, str]] = []
    for normalised, names in index.get("titles", {}).items():
        tokens = set(normalised.split())
        common = len(words & tokens)
        if common:
            score = common / len(words | tokens)
            for name in names:
                scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    seen: list[str] = []
    for _, name in scored:
        if name not in seen:
            seen.append(name)
        if len(seen) >= limit:
            break
    return seen
