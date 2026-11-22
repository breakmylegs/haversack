"""Take the newest save when two versions differ (R16 step 2, ADR-0080). Opt-in, guarded, reversible.

Principle 4 says hashes decide and timestamps inform. Peter asked for an opt-in exception: when
"When saves differ" is "Take the newest", a fork between this device and one other version is
settled by time instead of by asking. The decision here is pure and refuses whenever time cannot
be trusted:

- only two sides (this device and one other version); several versions still ask;
- both times known;
- neither time in the future by more than a few minutes on this device's clock (a device whose
  clock runs fast would otherwise always win);
- the two times far enough apart that clocks a minute or two out cannot flip the answer.

Whatever is chosen, nothing is lost: the existing resolution keeps the other version pinned in
History and takes a pre-restore snapshot first (principle 3), and Undo restores it.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from .fsutil import atomic_write_json, read_json

FUTURE_SECONDS = 300.0  # a time later than this past "now" means a clock is wrong
CLOSE_SECONDS = 120.0  # closer than this, two devices' clocks could disagree on the order
POLICIES = ("ask", "newest")


def parse_time(value: Any) -> float | None:
    """An ISO 8601 time (as snapshots and last_changed write them) as seconds since the epoch."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.timestamp()


def decide(sides: list[dict[str, Any]], now: float | None = None) -> dict[str, Any]:
    """``{"choice": "use-cloud" | "use-local" | None, "head", "margin", "reason", "device"}``."""
    now = time.time() if now is None else now
    local = [s for s in sides if s.get("side") == "local"]
    cloud = [s for s in sides if s.get("side") == "cloud"]
    out: dict[str, Any] = {"choice": None, "head": None, "margin": None, "device": None}
    if len(local) != 1 or len(cloud) != 1:
        return {**out, "reason": "more than two versions differ, so you choose"}
    mine, theirs = parse_time(local[0].get("created")), parse_time(cloud[0].get("created"))
    out["device"] = cloud[0].get("device")
    if mine is None or theirs is None:
        return {**out, "reason": "one version's time is not known, so you choose"}
    if mine > now + FUTURE_SECONDS or theirs > now + FUTURE_SECONDS:
        return {**out, "reason": "a device's clock looks wrong (a time is in the future), so you choose"}
    margin = abs(mine - theirs)
    out["margin"] = round(margin)
    if margin < CLOSE_SECONDS:
        return {**out, "reason": "the two versions are too close in time to be sure which is newer, so you choose"}
    if theirs > mine:
        return {**out, "choice": "use-cloud", "head": cloud[0].get("snapId"), "reason": "the other version is newer"}
    return {**out, "choice": "use-local", "reason": "this device's version is newer"}


def margin_text(seconds: int | None) -> str:
    if not seconds:
        return ""
    if seconds < 3600:
        return f"{max(1, round(seconds / 60))} min newer"
    if seconds < 86400:
        return f"{round(seconds / 3600)} h newer"
    return f"{round(seconds / 86400)} days newer"


class NewestChoices:
    """The last version taken by itself, per game, so Undo can bring the other back. This device only."""

    def __init__(self, path: str) -> None:
        self.path = path

    def _load(self) -> dict[str, dict[str, Any]]:
        data = read_json(self.path, default={})
        games = data.get("games") if isinstance(data, dict) else None
        return {str(k): v for k, v in games.items() if isinstance(v, dict)} if isinstance(games, dict) else {}

    def get(self, key: str) -> dict[str, Any] | None:
        return self._load().get(key)

    def record(self, key: str, choice: dict[str, Any]) -> None:
        games = self._load()
        games[key] = choice
        atomic_write_json(self.path, {"version": 1, "games": games})

    def clear(self, key: str) -> None:
        games = self._load()
        if games.pop(key, None) is not None:
            atomic_write_json(self.path, {"version": 1, "games": games})
