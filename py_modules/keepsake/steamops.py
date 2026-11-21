"""Steam Operations Executor queue (v2 spec 7.2, P15, ADR-0015).

Steam-side changes (shortcuts, launch options, compatibility tools, artwork) can
only be made through ``SteamClient`` in the frontend. Modules enqueue an
operation here after an explicit user action; the frontend claims it when
Gaming Mode is running, stores the original values, applies the change, reads
every field back and reports. Operations wait while no frontend is running (for
example in Desktop Mode) and every UI shows them as pending.

Stored in the ``core_steam_ops`` table of the state database.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

from .statedb import StateDB

KINDS = (
    "probe",
    "add-shortcut",  # payload: name, exe, startDir, launchOptions; the result carries the new appid
    "set-launch-options",
    "set-shortcut-name",
    "set-shortcut-exe",
    "set-shortcut-start-dir",
    "set-compat-tool",
    "remove-shortcut",  # payload: appid; only for a shortcut the module itself created
    "set-artwork",  # payload: appid, assetType (0 to 3), imageType (png or jpg), file (a staged image's name)
    "set-hidden",  # payload: appid, hidden; only Steam's copies of other devices' shortcuts (ADR-0064)
)
_STAGED_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
STATES = ("pending", "claimed", "done", "failed")
CLAIM_TIMEOUT = 120.0  # a claim not completed in this time is offered again (the frontend may have reloaded)
MIGRATIONS = [
    """
    CREATE TABLE core_steam_ops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        module TEXT NOT NULL,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL,
        state TEXT NOT NULL,
        result TEXT,
        created REAL NOT NULL,
        updated REAL NOT NULL
    );
    CREATE INDEX core_steam_ops_state ON core_steam_ops (state, id)
    """,
]


class SteamOpsError(ValueError):
    pass


class SteamOps:
    def __init__(self, db: StateDB, clock: Callable[[], float] = time.time) -> None:
        self.db = db
        self.clock = clock
        db.migrate("core", MIGRATIONS)

    def enqueue(self, module: str, kind: str, payload: dict[str, Any]) -> int:
        if kind not in KINDS:
            raise SteamOpsError(f"unknown Steam operation {kind}")
        if kind == "add-shortcut":
            if not all(isinstance(payload.get(k), str) for k in ("name", "exe", "startDir", "launchOptions")):
                raise SteamOpsError("a new shortcut needs a name, exe, start folder and launch options")
        elif kind != "probe" and not isinstance(payload.get("appid"), int):
            raise SteamOpsError("Steam operations need the app ID")
        if kind == "set-artwork" and (
            payload.get("assetType") not in (0, 1, 2, 3)
            or payload.get("imageType") not in ("png", "jpg")
            or not _STAGED_NAME.match(str(payload.get("file", "")))  # no "/" and no leading dot, so no ".."
        ):
            raise SteamOpsError("artwork needs an asset type, a PNG or JPEG and a staged file name")
        if kind == "set-hidden" and not isinstance(payload.get("hidden"), bool):
            raise SteamOpsError("hiding needs hidden true or false")
        now = self.clock()
        self.db.execute(
            "INSERT INTO core_steam_ops (module, kind, payload, state, created, updated) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (module, kind, json.dumps(payload, sort_keys=True), now, now),
        )
        return int(self.db.execute("SELECT max(id) FROM core_steam_ops")[0][0])

    def claim(self) -> dict[str, Any] | None:
        """The oldest pending operation (or one whose claim timed out), marked claimed."""
        stale = self.clock() - CLAIM_TIMEOUT
        rows = self.db.execute(
            "SELECT id, module, kind, payload FROM core_steam_ops "
            "WHERE state = 'pending' OR (state = 'claimed' AND updated < ?) ORDER BY id LIMIT 1",
            (stale,),
        )
        if not rows:
            return None
        op_id, module, kind, payload = rows[0]
        self.db.execute("UPDATE core_steam_ops SET state = 'claimed', updated = ? WHERE id = ?", (self.clock(), op_id))
        return {"id": op_id, "module": module, "kind": kind, "payload": json.loads(payload)}

    def finish(self, op_id: int, ok: bool, result: dict[str, Any]) -> None:
        rows = self.db.execute("SELECT state FROM core_steam_ops WHERE id = ?", (int(op_id),))
        if not rows or rows[0][0] != "claimed":
            raise SteamOpsError("that operation is not waiting for a result")
        self.db.execute(
            "UPDATE core_steam_ops SET state = ?, result = ?, updated = ? WHERE id = ?",
            ("done" if ok else "failed", json.dumps(result, sort_keys=True)[:20000], self.clock(), int(op_id)),
        )

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, module, kind, payload, state, result, created, updated "
            "FROM core_steam_ops ORDER BY id DESC LIMIT ?",
            (int(limit),),
        )
        return [
            {
                "id": r[0],
                "module": r[1],
                "kind": r[2],
                "payload": json.loads(r[3]),
                "state": r[4],
                "result": json.loads(r[5]) if r[5] else None,
                "created": r[6],
                "updated": r[7],
            }
            for r in rows
        ]

    def get(self, op_id: int) -> dict[str, Any] | None:
        rows = self.db.execute(
            "SELECT id, module, kind, state, payload FROM core_steam_ops WHERE id = ?", (int(op_id),)
        )
        if not rows:
            return None
        r = rows[0]
        return {"id": r[0], "module": r[1], "kind": r[2], "state": r[3], "payload": json.loads(r[4])}

    def pending_count(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM core_steam_ops WHERE state IN ('pending', 'claimed')")[0][0])
