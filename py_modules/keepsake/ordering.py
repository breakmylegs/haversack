"""Order the Games list by what needs the user's attention (Peter's device run, 16 November 2026).

First, games whose match waits for approval. Then a prefix mismatch (sync is
blocked), an unresolved conflict and a quarantined snapshot. Then everything
else, by name: case-insensitive and numeric-aware, so "Game 2" comes before
"Game 10". Each entry gains ``attention``, the reason it is near the top, or None.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

ATTENTION = ("confirm-match", "prefix-mismatch", "conflict", "quarantined")
_DIGITS = re.compile(r"(\d+)")


def attention(match: dict[str, Any], mismatched: set[str]) -> str | None:
    if match.get("proposal"):
        return "confirm-match"
    if match.get("key") in mismatched:
        return "prefix-mismatch"
    if match.get("sync") == "conflict":
        return "conflict"
    if match.get("sync") == "quarantined":
        return "quarantined"
    return None


def name_key(name: Any) -> tuple[tuple[int, Any], ...]:
    """Case-insensitive, numeric-aware: runs of digits compare as numbers."""
    parts = _DIGITS.split(str(name or "").casefold())
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts if p)


def order(matches: Iterable[dict[str, Any]], mismatched: Iterable[str] = ()) -> list[dict[str, Any]]:
    blocked = set(mismatched)
    out = []
    for match in matches:
        reason = attention(match, blocked)
        out.append({**match, "attention": reason})
    rank = {reason: i for i, reason in enumerate(ATTENTION)}
    return sorted(
        out, key=lambda m: (rank.get(m["attention"], len(ATTENTION)), name_key(m.get("name")), m.get("key", ""))
    )
