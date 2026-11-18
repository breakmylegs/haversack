"""The Activity list: what Keepsake did, in plain words (ADR-0048).

Built from the structured log (``keepsake.jsonl``), newest first. Only events a person
cares about are listed; everything else stays in Logs. Game keys are shown as the
game's name where this device knows it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

PULL_TEXT = {
    "restored": "Brought in the newer save from another device for {game}.",
    "pull": "Brought in the newer save from another device for {game}.",
    "adopt": "Linked {game} with your other devices: the saves were already the same.",
    "up-to-date": "Checked {game} before play: already up to date.",
    "conflict": "{game} changed on two devices: your choice is needed.",
    "offline": "Could not reach the cloud before playing {game}; played with the save on this device.",
}
PUSH_TEXT = {
    "published": "Saved {game} to the cloud.",
    "published-fork": "Saved {game} to the cloud, but another device saved too: your choice is needed.",
    "offline": "Could not reach the cloud to save {game}; it will be saved next time.",
    "pending": "Could not reach the cloud to save {game}; it will be saved next time.",
    "quarantined": "Held back a save of {game} that looked broken; it is waiting for you to check it.",
    "conflict": "{game} changed on two devices: your choice is needed.",
}
RESOLVE_TEXT = {
    "use-local": "Kept this device's save of {game}. The other one is pinned in History.",
    "use-cloud": "Used the save from another device for {game}. This device's one is pinned in History.",
    "decide-later": "Left the conflict in {game} for later.",
}


def _game(fields: Mapping[str, Any], name_of: Callable[[str], str]) -> str:
    key = str(fields.get("gameKey") or fields.get("key") or "")
    return name_of(key) if key else "a game"


def describe(record: Mapping[str, Any], name_of: Callable[[str], str]) -> str | None:
    """One sentence for a log record, or None when it is not activity a person needs to see."""
    event = str(record.get("event", ""))
    fields = record.get("fields") or {}
    if not isinstance(fields, Mapping):
        fields = {}
    game = _game(fields, name_of)
    if event == "sync.pull":
        template = PULL_TEXT.get(str(fields.get("action")))
    elif event == "sync.push":
        template = PUSH_TEXT.get(str(fields.get("status")))
    elif event == "sync.resolve":
        template = RESOLVE_TEXT.get(str(fields.get("choice")))
    elif event == "snapshot.checkpoint":
        template = "Saved a checkpoint of {game}." if fields.get("status") == "published" else None
    elif event == "snapshot.take":
        template = "Took a snapshot of {game}." if fields.get("status") == "published" else None
    elif event == "snapshot.restore":
        status = fields.get("status")
        template = {
            "restored": "Restored an older save of {game}. The one it replaced can be brought back.",
            "restored-partly": "Restored some files of {game} from an older save; the replaced ones can come back.",
        }.get(str(status))
    elif event == "snapshot.undo":
        template = "Undid the last restore of {game}."
    elif event == "snapshot.release":
        template = "Released a held-back save of {game} to the cloud."
    elif event == "auth.signed_in":
        template = "Signed in to the cloud."
    elif event == "auth.signed_out":
        template = "Signed out of the cloud."
    elif event == "import.ludusavi_all":
        template = "Finished importing Ludusavi backups."
    elif event in ("update.applied", "update.pc_installed"):
        template = "Updated Keepsake."
    else:
        template = None
    return template.format(game=game) if template else None


def build(
    records: Iterable[Mapping[str, Any]], name_of: Callable[[str], str], limit: int = 100
) -> list[dict[str, Any]]:
    """Activity entries, newest first: ``time``, ``text`` and ``level`` (info or warn)."""
    out: list[dict[str, Any]] = []
    for record in reversed(list(records)):
        text = describe(record, name_of)
        if text is None:
            continue
        level = "warn" if str(record.get("level")) in ("warning", "error") or "your choice" in text else "info"
        out.append({"time": record.get("ts"), "text": text, "level": level})
        if len(out) >= limit:
            break
    return out
