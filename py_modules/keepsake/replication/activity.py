"""One list of games moving between devices, for every page (v0.31.0, ADR-0072).

Each entry, sending or receiving, has the same fields: a stage, bytes done of the total, the
speed, the time left, a plain reason when it stopped, and whether it can be stopped or cleared.
The receiving device works its entries out from its own offers and transfers, and sends the
progress fields (never a title or a path) to the sending device, which shows the same bar.
"""

from __future__ import annotations

from typing import Any

# In the order a game goes through them. "paused" and "waiting" interrupt "copying".
STAGES = ("checking-space", "preparing", "copying", "verifying", "adding", "done", "failed", "paused", "waiting")
FINAL = ("done", "failed")
WIRE_FIELDS = ("stage", "done", "total", "bytesPerSecond", "secondsLeft")


def _entry(
    entry_id: str,
    direction: str,
    title: str,
    peer: str,
    stage: str,
    done: int = 0,
    total: int = 0,
    rate: float = 0.0,
    reason: str | None = None,
    update: bool = False,
    seconds_left: int | None = None,
) -> dict[str, Any]:
    done = max(0, min(int(done), int(total))) if total else max(0, int(done))
    if stage == "done" and total:
        done = total
    percent = 100 if stage == "done" else int(done * 100 // total) if total else 0
    if seconds_left is None and stage == "copying" and rate > 0 and total:
        seconds_left = int((total - done) / rate)
    return {
        "id": entry_id,
        "direction": direction,
        "title": title,
        "peer": peer,
        "stage": stage if stage in STAGES else "copying",
        "done": done,
        "total": int(total),
        "percent": percent,
        "bytesPerSecond": int(rate) if stage == "copying" else 0,
        "secondsLeft": seconds_left if stage == "copying" else None,
        "reason": reason,
        "update": update,
        "canStop": stage not in ("done",),
        "canClear": stage in FINAL,
    }


def receiving(offer_id: str, record: dict[str, Any], jobs: dict[str, Any], peer: str) -> dict[str, Any]:
    """An offer this device is taking in. ``jobs`` maps each scope's job ID to its live job, if any."""
    offer = record["offer"]
    shares = offer["shares"]
    scopes = list(record.get("jobs") or shares)
    done_scopes = set(record.get("doneScopes", []))
    done = total = 0
    rate = 0.0
    live = []
    for scope in scopes:
        share_bytes = int(shares.get(scope, {}).get("bytes", 0))
        job = jobs.get(record.get("jobs", {}).get(scope, ""))
        if scope in done_scopes or job is None:
            total += share_bytes
            done += share_bytes if scope in done_scopes else 0
            continue
        live.append(job)
        total += int(job.total or share_bytes)
        done += int(job.received)
        if job.state == "running":
            rate += float(job.rate)
    state = record.get("state")
    reason = record.get("reason")
    if state == "offered":
        stage = "checking-space"
    elif state == "transferring":
        states = {job.state for job in live}
        if "failed" in states:
            stage = "failed"
            reason = next((j.reason for j in live if j.state == "failed"), reason)
        elif states & {"running"}:
            stage = "copying"
        elif "waiting" in states:
            stage, reason = "waiting", next((j.reason for j in live if j.state == "waiting"), reason)
        elif "paused" in states:
            stage, reason = "paused", next((j.reason for j in live if j.state == "paused"), reason)
        elif live and states <= {"verifying", "promoting", "done"}:
            stage = "verifying"
        else:
            stage = "copying"
        if stage == "copying" and any(j.held for j in live):
            stage, reason = "waiting", next((j.reason for j in live if j.held), reason)
    elif state == "registering":
        stage = "adding"
    elif state in ("done", "failed"):
        stage = str(state)
    else:
        stage = "copying"
    return _entry(
        offer_id, "receiving", offer["title"], peer, stage, done, total, rate, reason, bool(offer.get("update"))
    )


REMOTE_STAGES = {
    "offered": "waiting",
    "transferring": "copying",
    "registering": "adding",
    "done": "done",
    "failed": "failed",
    "declined": "failed",
    "removed": "failed",
}


def sending(offer_id: str, record: dict[str, Any], peer: str) -> dict[str, Any]:
    """An offer this device made, as the receiving device last described it."""
    state = str(record.get("remoteState") or "offered")
    stage = str(record.get("remoteStage") or REMOTE_STAGES.get(state, "copying"))
    if state in ("done", "failed", "declined", "removed"):
        stage = REMOTE_STAGES[state]  # a final state wins over an older progress stage
    reason = record.get("remoteReason")
    if state == "offered" and not record.get("remoteStage"):
        reason = f"Waiting for {peer} to start"
    elif state == "declined":
        reason = f"{peer} declined it"
    elif state == "removed":
        reason = f"Stopped and removed on {peer}"
    seconds = record.get("remoteSecondsLeft")
    return _entry(
        offer_id,
        "sending",
        str(record.get("title") or "A game"),
        peer,
        stage,
        int(record.get("remoteDone") or 0),
        int(record.get("remoteTotal") or 0),
        float(record.get("remoteRate") or 0),
        reason,
        bool(record.get("update")),
        int(seconds) if isinstance(seconds, int) else None,
    )


def preparing(entry_id: str, direction: str, title: str, peer: str, state: dict[str, Any]) -> dict[str, Any]:
    """Before an offer exists: checking space and reading the game's files (on either device)."""
    stage = str(state.get("stage") or ("failed" if state.get("state") == "failed" else "preparing"))
    reason = state.get("reason") or (state.get("warning") if stage != "failed" else None)
    return _entry(entry_id, direction, title, peer, stage, reason=reason)


def wire(entry: dict[str, Any]) -> dict[str, Any]:
    """What the receiving device sends about its progress: numbers and a stage only."""
    return {k: entry[k] for k in WIRE_FIELDS}


def clean_progress(message: dict[str, Any]) -> dict[str, Any]:
    """Progress fields from the other device, checked: unknown stages and bad numbers are dropped."""
    out: dict[str, Any] = {}
    stage = message.get("stage")
    if stage in STAGES:
        out["remoteStage"] = stage
    for key, field in (("done", "remoteDone"), ("total", "remoteTotal"), ("bytesPerSecond", "remoteRate")):
        value = message.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**53:
            out[field] = value
    seconds = message.get("secondsLeft")
    if isinstance(seconds, int) and not isinstance(seconds, bool) and 0 <= seconds < 10**7:
        out["remoteSecondsLeft"] = seconds
    elif "secondsLeft" in message:
        out["remoteSecondsLeft"] = None
    return out
