"""Sync engine: the snapshot DAG and the decision table (build prompt section 9).

Hashes and parent links decide; timestamps are shown but never pick a winner
(principle 4). Whenever local and cloud have both changed, the user resolves a
conflict (principle 1), and whichever side loses is kept as a pinned
snapshot. Restores go through :class:`SnapshotEngine`, which takes a verified
pre-restore snapshot first (principle 3) and refuses while the game runs
(principle 6).

Local state per game (``sync-state.json`` in the runtime folder):
``base`` (the last snapshot this device restored or pushed), ``sessionOpen``,
``conflict``, ``pending`` (a check or push waiting for the cloud),
``basePublished`` and timestamps.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .engine import SnapshotEngine
from .fsutil import atomic_write_json, read_json
from .retention import heads as dag_heads
from .snapshot import NewerSchemaError, SnapshotError, content_hash, scan_entries, verify_blob
from .store import StoreError, StoreUnavailable

STATE_FILE = "sync-state.json"
PIN_LOSER_SECONDS = 90 * 24 * 3600  # at least the 30 days the build prompt asks for
STAGING_DIR = "staging"


@dataclass
class GameContext:
    """What sync needs to know about one game on this device."""

    game_key: str
    files: Callable[[], Mapping[str, list[str]]]  # current files per root, scanned fresh each call
    roots: Mapping[str, str | None]
    running: Callable[[], bool]


class SyncState:
    def __init__(self, runtime_dir: str) -> None:
        self._path = os.path.join(runtime_dir, STATE_FILE)
        self._lock = threading.Lock()

    def _all(self) -> dict[str, Any]:
        data = read_json(self._path, default={})
        return data if isinstance(data, dict) else {}

    def get(self, game_key: str) -> dict[str, Any]:
        with self._lock:
            record = self._all().get(game_key)
        return dict(record) if isinstance(record, dict) else {}

    def update(self, game_key: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            data = self._all()
            record = dict(data.get(game_key) or {})
            record.update(changes)
            data[game_key] = record
            atomic_write_json(self._path, data)
            return record

    def games(self) -> dict[str, Any]:
        with self._lock:
            return self._all()


class SyncEngine:
    def __init__(self, engine: SnapshotEngine, runtime_dir: str, clock: Callable[[], float] = time.time) -> None:
        self.engine = engine
        self.state = SyncState(runtime_dir)
        self.clock = clock
        self._staging = os.path.join(runtime_dir, STAGING_DIR)

    # DAG

    def _cloud(self, game_key: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
        metas = self.engine.list_metas(game_key)
        by_id = {m["snapId"]: m for m in metas}
        return by_id, sorted(dag_heads(metas))

    @staticmethod
    def _summary(meta: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "snapId": meta["snapId"],
            "device": meta.get("deviceName"),
            "created": meta.get("created"),
            "files": len(meta.get("files", [])),
            "bytes": sum(int(f.get("size", 0)) for f in meta.get("files", [])),
            "kind": meta.get("kind"),
        }

    def _local_hash(self, ctx: GameContext) -> tuple[str, int]:
        entries = scan_entries(ctx.files(), ctx.roots)
        return content_hash(entries), len(entries)

    def _set_base(self, game_key: str, snap_id: str) -> None:
        self.state.update(game_key, base=snap_id, basePublished=False)
        self._publish_base(game_key)

    def _publish_base(self, game_key: str) -> None:
        record = self.state.get(game_key)
        if not record.get("base") or record.get("basePublished"):
            return
        try:
            self.engine.publish_base(game_key, record["base"])
            self.state.update(game_key, basePublished=True)
        except StoreError:
            pass  # retried by the idle pass; retention still protects heads and pins meanwhile

    def _conflict(
        self, game_key: str, kind: str, heads: list[str], by_id: Mapping[str, Any], local_files: int
    ) -> dict[str, Any]:
        conflict = {
            "kind": kind,
            "heads": [self._summary(by_id[h]) for h in heads if h in by_id],
            "localFiles": local_files,
            "raised": self.clock(),
        }
        self.state.update(game_key, conflict=conflict)
        return {"action": "conflict", "conflict": conflict}

    # Pull before launch

    def pull(self, ctx: GameContext) -> dict[str, Any]:
        """Decide what to do before the game starts. Always ends with the game playable."""
        gk = ctx.game_key
        record = self.state.get(gk)
        try:
            result = self._pull(ctx, record)
        except NewerSchemaError:
            result = {"action": "launch", "blocked": "newer-schema"}
        except StoreUnavailable:
            self.state.update(gk, pending=True)
            result = {"action": "launch", "pending": True}
        self.state.update(gk, sessionOpen={"started": self.clock()})
        return result

    def _pull(self, ctx: GameContext, record: dict[str, Any]) -> dict[str, Any]:
        gk = ctx.game_key
        if record.get("conflict"):
            # "Decide later": play the local save; auto-pull stays off until resolved.
            return {"action": "launch", "conflict": record["conflict"]}
        by_id, heads = self._cloud(gk)
        local_hash, local_files = self._local_hash(ctx)
        base = record.get("base")
        self.state.update(gk, pending=False, lastCheck=self.clock())
        if not heads:
            return {"action": "launch", "reason": "no-cloud-snapshots"}
        matching = [h for h in heads if by_id[h]["contentHash"] == local_hash]

        if base is None or base not in by_id:
            # Adoption: this device has never synced this game.
            if len(heads) > 1:
                if matching:
                    self._set_base(gk, matching[0])
                return self._conflict(gk, "fork", heads, by_id, local_files)
            if matching:
                self._set_base(gk, heads[0])
                return {"action": "launch", "reason": "adopted"}
            if local_files == 0:
                return self._restore(ctx, heads[0])
            return self._conflict(gk, "adoption", heads, by_id, local_files)

        if len(heads) > 1:
            return self._conflict(gk, "fork", heads, by_id, local_files)
        head = heads[0]
        local_changed = local_hash != by_id[base]["contentHash"]
        cloud_changed = head != base
        if not cloud_changed:
            return {"action": "launch", "reason": "local-changed" if local_changed else "up-to-date"}
        if not local_changed:
            return self._restore(ctx, head)
        if local_hash == by_id[head]["contentHash"]:
            self._set_base(gk, head)  # both sides arrived at the same files
            return {"action": "launch", "reason": "converged"}
        return self._conflict(gk, "both-changed", heads, by_id, local_files)

    def _restore(self, ctx: GameContext, snap_id: str) -> dict[str, Any]:
        if ctx.running():
            # Section 10: never restore under a running game; ask the user to quit.
            self.state.update(ctx.game_key, pending=True)
            return {"action": "launch", "pending": True, "reason": "cloud-newer-game-running"}
        staged = os.path.join(self._staging, ctx.game_key, f"{snap_id}.zip")
        result = self.engine.restore(ctx.game_key, snap_id, ctx.files(), ctx.roots, False, staged_blob=staged)
        self._set_base(ctx.game_key, snap_id)
        self.state.update(ctx.game_key, lastPull=self.clock())
        return {"action": "restored", "snapId": snap_id, "prerestore": result.get("prerestore")}

    # Push after exit

    def push(self, ctx: GameContext, kind: str = "auto-exit") -> dict[str, Any]:
        gk = ctx.game_key
        try:
            result = self._push(ctx, kind)
        except NewerSchemaError:
            result = {"status": "blocked", "reason": "newer-schema"}
        except StoreUnavailable:
            self.state.update(gk, pending=True)
            result = {"status": "pending"}
        self.state.update(gk, sessionOpen=None)
        return result

    def _push(self, ctx: GameContext, kind: str) -> dict[str, Any]:
        gk = ctx.game_key
        record = self.state.get(gk)
        base_id = record.get("base")
        by_id, heads = self._cloud(gk)
        base = by_id.get(base_id) if base_id else None
        local_hash, _ = self._local_hash(ctx)
        if base is not None and local_hash == base["contentHash"]:
            self.state.update(gk, pending=False)
            return {"status": "no-change"}
        if base is None and heads:
            # Never synced but the cloud has history: do not guess a parent.
            if any(by_id[h]["contentHash"] == local_hash for h in heads):
                self._set_base(gk, next(h for h in heads if by_id[h]["contentHash"] == local_hash))
                return {"status": "no-change"}
            if not record.get("conflict"):
                self._conflict(gk, "adoption", heads, by_id, len(scan_entries(ctx.files(), ctx.roots)))
        result = self.engine.take(gk, ctx.files(), ctx.roots, kind, base)
        if result["status"] == "quarantined":
            self.state.update(gk, pending=False, quarantined=result["snapId"])
            return result
        if result["status"] != "published":
            self.state.update(gk, pending=False)
            return result
        new_id = result["snapId"]
        self._set_base(gk, new_id)
        self.state.update(gk, pending=False, lastPush=self.clock())
        # Re-fetch heads: if the cloud moved during play, the upload above made a fork.
        by_id, heads = self._cloud(gk)
        if len(heads) > 1 and not self.state.get(gk).get("conflict"):
            self._conflict(gk, "fork", heads, by_id, len(result["meta"]["files"]))
            return {"status": "published-fork", "snapId": new_id}
        return {"status": "published", "snapId": new_id}

    # Conflicts

    def resolve(self, ctx: GameContext, choice: str, head: str | None = None) -> dict[str, Any]:
        """Apply the user's choice. ``use-cloud`` needs ``head`` when there are several."""
        gk = ctx.game_key
        record = self.state.get(gk)
        if choice == "decide-later":
            return {"status": "deferred", "conflict": record.get("conflict")}
        if ctx.running():
            raise SnapshotError("quit the game before resolving a conflict")
        by_id, heads = self._cloud(gk)
        base_meta = by_id.get(record.get("base") or "")
        until = self.clock() + PIN_LOSER_SECONDS
        if choice == "use-cloud":
            target = head or (heads[0] if len(heads) == 1 else None)
            if target not in heads:
                raise SnapshotError("choose which cloud save to use")
            # Keep this device's files first, pinned, so choosing never destroys data.
            kept = self.engine.take(
                gk, ctx.files(), ctx.roots, "manual", base_meta, gate=False, flags=["conflict-loser"]
            )
            if kept["status"] == "published":
                self.engine.pin(gk, kept["snapId"], until)
            result = self._restore_now(ctx, target)
            # Close the fork: a merge with the chosen files whose parents are every head,
            # so the next launch sees one head. Every losing head stays pinned.
            by_id, heads_now = self._cloud(gk)
            merged_id = target
            if len(heads_now) > 1:
                merged = self.engine.take(
                    gk, ctx.files(), ctx.roots, "merge", by_id[target], parents=heads_now, force=True, gate=False
                )
                if merged["status"] == "published":
                    merged_id = merged["snapId"]
                    self._set_base(gk, merged_id)
            for loser in heads_now:
                if loser != target:
                    self.engine.pin(gk, loser, until)
            self.state.update(gk, conflict=None)
            return {"status": "resolved", "used": target, "merge": merged_id, "keptLocal": kept.get("snapId"), **result}
        if choice == "use-local":
            merged = self.engine.take(
                gk, ctx.files(), ctx.roots, "merge", base_meta, parents=heads, force=True, gate=False
            )
            if merged["status"] != "published":
                raise SnapshotError(f"could not upload this device's save ({merged['status']})")
            for loser in heads:
                self.engine.pin(gk, loser, until)
            self._set_base(gk, merged["snapId"])
            self.state.update(gk, conflict=None)
            return {"status": "resolved", "used": merged["snapId"], "pinned": heads}
        raise SnapshotError(f"unknown choice {choice}")

    def _restore_now(self, ctx: GameContext, snap_id: str) -> dict[str, Any]:
        staged = os.path.join(self._staging, ctx.game_key, f"{snap_id}.zip")
        result = self.engine.restore(ctx.game_key, snap_id, ctx.files(), ctx.roots, False, staged_blob=staged)
        self._set_base(ctx.game_key, snap_id)
        return {"prerestore": result.get("prerestore")}

    # Background work

    def prefetch(self, ctx: GameContext) -> list[str]:
        """Download cloud heads newer than the base into local staging, verified, so a launch restore is local."""
        gk = ctx.game_key
        by_id, heads = self._cloud(gk)
        base = self.state.get(gk).get("base")
        folder = os.path.join(self._staging, gk)
        os.makedirs(folder, exist_ok=True)
        fetched: list[str] = []
        for head in heads:
            target = os.path.join(folder, f"{head}.zip")
            if head == base or os.path.exists(target):
                continue
            tmp = target + ".part"
            try:
                self.engine.store.get_to_file(f"games/{gk}/blobs/{head}.zip", tmp)
                verify_blob(tmp, by_id[head])
                os.replace(tmp, target)
                fetched.append(head)
            except (StoreError, SnapshotError):
                if os.path.exists(tmp):
                    os.unlink(tmp)
        for name in os.listdir(folder):
            if name.endswith(".zip") and name[:-4] not in heads:
                os.unlink(os.path.join(folder, name))  # local cache only
        return fetched

    def idle(self, ctx: GameContext) -> dict[str, Any]:
        """The 30-minute pass: prefetch heads and push changes made with no session open."""
        gk = ctx.game_key
        record = self.state.get(gk)
        if record.get("sessionOpen") or ctx.running():
            return {"status": "skipped", "reason": "session-open"}
        try:
            self._publish_base(gk)
            fetched = self.prefetch(ctx)
            if record.get("pending") and not record.get("conflict"):
                # Reconcile a launch that happened offline, using the normal decision table.
                outcome = self._pull(ctx, record)
                if outcome["action"] == "conflict":
                    return {"status": "conflict", "fetched": fetched}
            pushed = self._push(ctx, "auto-exit")
        except NewerSchemaError:
            return {"status": "blocked", "reason": "newer-schema"}
        except StoreUnavailable:
            self.state.update(gk, pending=True)
            return {"status": "pending"}
        return {"status": "ok", "fetched": fetched, "push": pushed["status"]}

    def recover_session(self, ctx: GameContext) -> dict[str, Any] | None:
        """Crash recovery: a session left open for a game that is not running gets an exit push."""
        if not self.state.get(ctx.game_key).get("sessionOpen") or ctx.running():
            return None
        return self.push(ctx, kind="auto-recovered")

    def status(self, game_key: str) -> dict[str, Any]:
        return self.state.get(game_key)
