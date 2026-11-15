"""Atomic restore with a journal (build prompt sections 3 and 9, principle 3).

A restore either leaves the old files or the new files, never a mix:

1. New files are extracted, hash-checked and fsynced into a staging folder
   beside the save root (``<root>/.keepsake-stage-<token>``).
2. A journal listing every operation is written (state ``prepared``), then
   switched to ``committing``.
3. Each file to replace or delete is first renamed into a backup folder
   beside the root, then the staged file is renamed into place. Renames stay
   inside one root, so each is atomic.
4. The journal is marked ``committed``; backups and staging are removed.

:func:`recover` runs on start and before every restore. A journal that never
reached ``committed`` is rolled back from the backups (old state); a
committed one is only cleaned up (new state).

Callers must take and verify a pre-restore snapshot first and must not
restore under a running game (principle 6).
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from .fsutil import atomic_write_json, read_json
from .safepath import ensure_within, join_within
from .snapshot import FileEntry, entries_of, extract, verify_blob

JOURNAL_DIR = "restore-journal"
STAGE_PREFIX = ".keepsake-stage-"
BACKUP_PREFIX = ".keepsake-backup-"

Hook = Callable[[str, int], None]


class RestoreError(Exception):
    pass


def plan(current: list[FileEntry], target: list[FileEntry]) -> list[dict[str, str]]:
    """Operations that turn ``current`` into ``target`` (within the scanned scope)."""
    now = {(e.root, e.rel): e for e in current}
    want = {(e.root, e.rel): e for e in target}
    ops: list[dict[str, str]] = []
    for key, entry in sorted(want.items()):
        existing = now.get(key)
        if existing is None:
            ops.append({"root": entry.root, "rel": entry.rel, "action": "create", "sha256": entry.sha256})
        elif existing.sha256 != entry.sha256 or existing.size != entry.size:
            ops.append({"root": entry.root, "rel": entry.rel, "action": "replace", "sha256": entry.sha256})
    for key in sorted(set(now) - set(want)):
        ops.append({"root": key[0], "rel": key[1], "action": "delete", "sha256": ""})
    return ops


def _journal_dir(runtime_dir: str) -> str:
    path = os.path.join(runtime_dir, JOURNAL_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _fsync_parent(path: str) -> None:
    if os.name != "posix":
        return
    fd = os.open(os.path.dirname(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def restore(
    blob_path: str,
    meta: Mapping[str, Any],
    current: list[FileEntry],
    roots: Mapping[str, str | None],
    runtime_dir: str,
    hook: Hook | None = None,
) -> dict[str, Any]:
    """Replace the files in ``current`` with the snapshot's files. Returns counts.

    ``hook(stage, index)`` is called at each step for fault-injection tests.
    """
    recover(runtime_dir)
    verify_blob(blob_path, meta)
    target = entries_of(meta)
    ops = plan(current, target)
    if not ops:
        return {"changed": 0, "created": 0, "replaced": 0, "deleted": 0}
    token = uuid.uuid4().hex[:12]
    journal_path = os.path.join(_journal_dir(runtime_dir), f"{token}.json")
    wanted = {(e.root, e.rel): e for e in target}

    # Resolve every path before touching anything.
    resolved: list[dict[str, str]] = []
    for op in ops:
        root = roots.get(op["root"])
        if not root:
            raise RestoreError(f"root {op['root']} is not available on this device")
        os.makedirs(root, exist_ok=True)
        target_path = join_within(root, op["rel"])
        if op["action"] == "create" and os.path.lexists(target_path) and not os.path.isdir(target_path):
            # Present on disk but not scanned (for example hidden by an exclusion):
            # move it aside like a replacement so it can never be lost.
            op = {**op, "action": "replace"}
        resolved.append(
            {
                **op,
                "target": target_path,
                "staged": join_within(os.path.join(root, STAGE_PREFIX + token), op["rel"]),
                "backup": join_within(os.path.join(root, BACKUP_PREFIX + token), op["rel"]),
                "rootPath": root,
            }
        )
    # Moves aside first (deletions, then replacements), creations last, so a file
    # can become a folder and a folder can become a file.
    order = {"delete": 0, "replace": 1, "create": 2}
    resolved.sort(key=lambda op: (order[op["action"]], op["root"], op["rel"]))
    deleted = {op["target"] for op in resolved if op["action"] == "delete"}
    for op in resolved:
        if op["action"] in ("create", "replace") and os.path.isdir(op["target"]) and not os.path.islink(op["target"]):
            _check_folder_clears(op["target"], deleted, op["rel"])
    journal: dict[str, Any] = {"token": token, "snapId": meta["snapId"], "state": "staging", "ops": resolved}
    atomic_write_json(journal_path, journal)

    try:
        to_extract = [op for op in resolved if op["action"] in ("create", "replace")]
        by_key = {(op["root"], op["rel"]): op for op in to_extract}
        extract(
            blob_path,
            meta,
            [wanted[(op["root"], op["rel"])] for op in to_extract],
            lambda e: (os.path.join(by_key[(e.root, e.rel)]["rootPath"], STAGE_PREFIX + token), e.rel),
        )
    except BaseException:
        _cleanup(journal)
        os.unlink(journal_path)
        raise
    if hook:
        hook("staged", 0)

    journal["state"] = "committing"
    atomic_write_json(journal_path, journal)
    try:
        for index, op in enumerate(resolved):
            if op["action"] in ("replace", "delete"):
                os.makedirs(os.path.dirname(op["backup"]), exist_ok=True)
                os.replace(op["target"], op["backup"])
            if hook:
                hook("moved-aside", index)
        for index, op in enumerate(resolved):
            if op["action"] in ("create", "replace"):
                parent = os.path.dirname(op["target"])
                os.makedirs(parent, exist_ok=True)
                ensure_within(op["rootPath"], parent)
                if os.path.isdir(op["target"]) and not os.path.islink(op["target"]):
                    _remove_empty_tree(op["target"])  # emptied by the moves above
                os.replace(op["staged"], op["target"])
                _fsync_parent(op["target"])
            if hook:
                hook("placed", index)
    except Exception:
        # An ordinary error: undo now rather than leave a mix until the next recover().
        _rollback(journal)
        _cleanup(journal)
        os.unlink(journal_path)
        raise

    journal["state"] = "committed"
    atomic_write_json(journal_path, journal)
    if hook:
        hook("committed", 0)
    _cleanup(journal)
    os.unlink(journal_path)
    counts = {a: sum(1 for op in resolved if op["action"] == a) for a in ("create", "replace", "delete")}
    return {
        "changed": len(resolved),
        "created": counts["create"],
        "replaced": counts["replace"],
        "deleted": counts["delete"],
    }


def _cleanup(journal: Mapping[str, Any]) -> None:
    roots = {op["rootPath"] for op in journal["ops"]}
    for root in roots:
        for prefix in (STAGE_PREFIX, BACKUP_PREFIX):
            shutil.rmtree(os.path.join(root, prefix + journal["token"]), ignore_errors=True)


def _check_folder_clears(folder: str, deleted: set[str], rel: str) -> None:
    """A folder may be replaced by a file only if every file inside it is being deleted."""
    for current, _dirs, files in os.walk(folder):
        for name in files:
            if os.path.join(current, name) not in deleted:
                raise RestoreError(f"a folder with other files is in the way of {rel}")


def _remove_empty_tree(folder: str) -> None:
    for current, dirs, files in os.walk(folder, topdown=False):
        if files:
            raise RestoreError(f"folder {folder} is not empty")
        for d in dirs:
            os.rmdir(os.path.join(current, d))
    os.rmdir(folder)


def _rollback(journal: Mapping[str, Any]) -> None:
    # Reverse order: creations are undone before moved-aside files come back.
    for op in reversed(journal["ops"]):
        target, backup, staged = op["target"], op["backup"], op["staged"]
        if op["action"] in ("replace", "delete"):
            if os.path.lexists(backup):
                if os.path.isdir(target) and not os.path.islink(target):
                    _remove_empty_tree(target)  # left by creations already undone
                elif os.path.lexists(target):
                    os.unlink(target)  # the new file that replaced it
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.replace(backup, target)
        elif op["action"] == "create" and os.path.lexists(target) and not os.path.lexists(staged):
            os.unlink(target)  # created by this restore


def recover(runtime_dir: str) -> list[dict[str, str]]:
    """Finish or undo any interrupted restore. Returns what was done per journal."""
    folder = os.path.join(runtime_dir, JOURNAL_DIR)
    if not os.path.isdir(folder):
        return []
    outcomes: list[dict[str, str]] = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        try:
            journal = read_json(path)
        except (OSError, ValueError) as exc:
            raise RestoreError(f"restore journal {name} is unreadable; saves were left untouched") from exc
        if not isinstance(journal, dict) or "ops" not in journal:
            raise RestoreError(f"restore journal {name} is invalid; saves were left untouched")
        if journal.get("state") == "committed":
            outcome = "completed"
        else:
            _rollback(journal)
            outcome = "rolled-back"
        _cleanup(journal)
        os.unlink(path)
        outcomes.append({"snapId": str(journal.get("snapId")), "outcome": outcome})
    return outcomes
