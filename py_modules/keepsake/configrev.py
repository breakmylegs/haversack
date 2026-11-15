"""Game config revisions: per-game settings shared between devices (build prompt section 9).

Each change to a game's shared settings (aliases, include config files, custom
paths, exclusions) is published as a write-once object
``games/<gameKey>/config/<seq>-<deviceId>.json``, where ``seq`` counts this
device's revisions for the game. The newest revision applies on every device,
so custom paths set on one device reach the other. Principle 4 covers save
data only, so timestamps may order config revisions (build prompt section 9).

Two revisions from different devices based on the same earlier revision are
concurrent edits: the newest still applies and the game page shows a warning.

Revisions hold only canonical values (``{root, rel}`` custom paths, glob
exclusions, aliases), never device paths (principle 10). Matching choices and
the game key stay per device, because shortcut names differ.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from .gameconfig import DEFAULT, GameConfigError, validate
from .store import AlreadyExistsError, NotFoundError, Store, StoreError

SCHEMA_VERSION = 1
SHARED_FIELDS = ("aliases", "includeConfig", "customPaths", "exclusions")
MAX_REVISIONS = 200
PUBLISH_ATTEMPTS = 5
_NAME = re.compile(r"^(\d{6})-([0-9A-Za-z-]{1,64})\.json$")


def shared_part(config: Mapping[str, Any]) -> dict[str, Any]:
    return {field: config.get(field, DEFAULT[field]) for field in SHARED_FIELDS}


def prefix(game_key: str) -> str:
    return f"games/{game_key}/config/"


def object_key(game_key: str, seq: int, device_id: str) -> str:
    return f"{prefix(game_key)}{seq:06d}-{device_id}.json"


def parse_name(name: str) -> tuple[int, str] | None:
    match = _NAME.match(name)
    return (int(match.group(1)), match.group(2)) if match else None


def _validate_revision(data: Any, game_key: str, name: str) -> dict[str, Any] | None:
    parsed = parse_name(name)
    if parsed is None or not isinstance(data, dict):
        return None
    if data.get("schemaVersion") != SCHEMA_VERSION or data.get("gameKey") != game_key:
        return None
    if data.get("deviceId") != parsed[1] or data.get("seq") != parsed[0]:
        return None
    config = data.get("config")
    if not isinstance(config, dict) or set(config) - set(SHARED_FIELDS):
        return None
    try:
        clean = shared_part(validate({**DEFAULT, **config}))
    except GameConfigError:
        return None
    created = data.get("createdTs")
    if not isinstance(created, (int, float)) or isinstance(created, bool):
        return None
    based_on = data.get("basedOn")
    if based_on is not None and (not isinstance(based_on, str) or parse_name(based_on) is None):
        return None
    return {
        "name": name,
        "seq": parsed[0],
        "deviceId": parsed[1],
        "deviceName": str(data.get("deviceName") or "")[:40],
        "createdTs": float(created),
        "basedOn": based_on,
        "config": clean,
    }


def list_revisions(store: Store, game_key: str) -> list[dict[str, Any]]:
    """Valid revisions for a game. Invalid or newer-schema objects are ignored (fail closed)."""
    out = []
    for info in store.list(prefix(game_key))[-MAX_REVISIONS:]:
        name = info.key.rsplit("/", 1)[-1]
        if parse_name(name) is None:
            continue
        try:
            data = json.loads(store.get(info.key).decode("utf-8"))
        except (NotFoundError, ValueError, UnicodeDecodeError):
            continue
        revision = _validate_revision(data, game_key, name)
        if revision is not None:
            out.append(revision)
    return out


def newest(revisions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not revisions:
        return None
    return max(revisions, key=lambda r: (r["createdTs"], r["deviceId"], r["seq"]))


def concurrent_with(revisions: list[dict[str, Any]], chosen: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Revisions from other devices based on the same revision as ``chosen``."""
    return [
        r
        for r in revisions
        if r["name"] != chosen["name"] and r["basedOn"] == chosen["basedOn"] and r["deviceId"] != chosen["deviceId"]
    ]


def publish(
    store: Store,
    game_key: str,
    device_id: str,
    device_name: str,
    config: Mapping[str, Any],
    based_on: str | None,
    clock: Callable[[], float] = time.time,
) -> str:
    """Write a new revision with this device's next sequence number. Returns its name."""
    shared = shared_part(validate({**DEFAULT, **shared_part(config)}))
    own = [
        parsed[0]
        for info in store.list(prefix(game_key))
        if (parsed := parse_name(info.key.rsplit("/", 1)[-1])) and parsed[1] == device_id
    ]
    seq = max(own, default=0) + 1
    for _ in range(PUBLISH_ATTEMPTS):
        now = clock()
        body = {
            "schemaVersion": SCHEMA_VERSION,
            "gameKey": game_key,
            "deviceId": device_id,
            "deviceName": device_name[:40],
            "seq": seq,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "createdTs": now,
            "basedOn": based_on,
            "config": shared,
        }
        key = object_key(game_key, seq, device_id)
        try:
            store.put_new(key, json.dumps(body, sort_keys=True).encode("utf-8"))
        except AlreadyExistsError:
            seq += 1
            continue
        return key.rsplit("/", 1)[-1]
    raise StoreError("could not find a free config revision number")
