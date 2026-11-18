"""Retention (build prompt section 9).

Retention prunes blobs only; metadata stays for ancestry checks, and a
write-once ``pruned/<snapId>`` marker records each prune. It is the only code
that deletes cloud data (principle 2).

Never pruned: pinned snapshots, every head, every device's base, the newest
snapshot that passed the gates, anything younger than 7 days, and (a
conservative choice, ADR-0007) every ``manual``, ``merge`` and ``import``
snapshot. Otherwise the policy keeps the last 10 automatic snapshots, one
per day for 30 days and one per month for 12 months.

Timestamps choose what to keep, never which save wins, so principle 4 holds.
"""

from __future__ import annotations

import calendar
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .snapshot import AUTOMATIC_KINDS

MIN_AGE_SECONDS = 7 * 24 * 3600
KEEP_LAST_AUTOMATIC = 10
DAILY_DAYS = 30
MONTHLY_MONTHS = 12
ALWAYS_KEPT_KINDS = ("manual", "merge", "import")


def created_epoch(meta: Mapping[str, Any]) -> float:
    try:
        return float(calendar.timegm(time.strptime(str(meta["created"]), "%Y-%m-%dT%H:%M:%SZ")))
    except (KeyError, ValueError):
        return 0.0


def heads(metas: Iterable[Mapping[str, Any]]) -> set[str]:
    """Snapshots no other snapshot names as a parent.

    ``import`` snapshots (old backups brought in from Ludusavi, ADR-0021) and
    ``provisional`` snapshots (taken on suspend mid-session, ADR-0022) are
    history to restore from by hand, never heads, so they never raise a
    conflict or replace anyone's current save without a prompt.
    """
    items = list(metas)
    # A suspend snapshot names the current head as its parent but must not hide it.
    parents = {p for m in items if m.get("kind") not in NEVER_HEADS for p in m.get("parents", [])}
    return {m["snapId"] for m in items if m["snapId"] not in parents and m.get("kind") not in NEVER_HEADS}


NEVER_HEADS = ("import", "provisional")


def active_pins(pins: Iterable[Mapping[str, Any]], now: float) -> set[str]:
    out: set[str] = set()
    for pin in pins:
        until = pin.get("until")
        if until is None or (isinstance(until, (int, float)) and until > now):
            out.add(str(pin["snapId"]))
    return out


def plan(
    metas: Sequence[Mapping[str, Any]],
    pinned: set[str],
    bases: set[str],
    already_pruned: set[str],
    now: float,
) -> dict[str, Any]:
    """Return ``{"keep": {snapId: reason}, "prune": [snapId, ...]}``."""
    keep: dict[str, str] = {}

    def protect(snap_id: str, reason: str) -> None:
        keep.setdefault(snap_id, reason)

    by_id = {m["snapId"]: m for m in metas}
    for snap_id in heads(metas):
        protect(snap_id, "head")
    for snap_id in pinned & set(by_id):
        protect(snap_id, "pinned")
    for snap_id in bases & set(by_id):
        protect(snap_id, "device base")
    epoch_of = {m["snapId"]: created_epoch(m) for m in metas}  # parse each time once (performance budget)
    ordered = sorted(metas, key=lambda m: (epoch_of[m["snapId"]], m["snapId"]), reverse=True)
    passed = [m for m in ordered if m.get("kind") != "provisional" and "quarantined" not in m.get("flags", [])]
    if passed:
        protect(passed[0]["snapId"], "newest that passed the gates")
    for meta in ordered:
        if now - epoch_of[meta["snapId"]] < MIN_AGE_SECONDS:
            protect(meta["snapId"], "younger than 7 days")
        if meta.get("kind") in ALWAYS_KEPT_KINDS:
            protect(meta["snapId"], f"{meta.get('kind')} snapshots are kept")

    automatic = [m for m in ordered if m.get("kind") in AUTOMATIC_KINDS]
    for meta in automatic[:KEEP_LAST_AUTOMATIC]:
        protect(meta["snapId"], "one of the last 10")
    days_seen: set[str] = set()
    months_seen: set[str] = set()
    for meta in automatic:
        epoch = epoch_of[meta["snapId"]]
        age_days = (now - epoch) / 86400
        day = time.strftime("%Y-%m-%d", time.gmtime(epoch))
        month = day[:7]
        if age_days <= DAILY_DAYS and day not in days_seen:
            days_seen.add(day)
            protect(meta["snapId"], "daily")
        if age_days <= MONTHLY_MONTHS * 31 and month not in months_seen:
            months_seen.add(month)
            protect(meta["snapId"], "monthly")

    prune = [m["snapId"] for m in ordered if m["snapId"] not in keep and m["snapId"] not in already_pruned]
    return {"keep": keep, "prune": sorted(prune)}
