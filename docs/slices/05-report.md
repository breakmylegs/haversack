# Slice 5 report: snapshot engine and safety rails

- Branch: `slice/05-snapshots`, stacked on `slice/04-manifest` (PR 5, not merged)
- Target version: 0.5.0 (changelog section added; bumped by `pnpm release prepare`)
- Date: 14 November 2026
- Built without your input, at your request. Decisions are in ADR-0007.

## What changed

**Backend**
- `snapshot.py`: file hashing, content hash, `snapId`, schema 1 metadata (as in the build prompt), metadata validation (paths, kinds, recomputed content hash, newer schema detection), deterministic zip packing that re-hashes while packing, full zip verification and checked extraction.
- `restore.py`: plan (create, replace, delete), journalled atomic restore with staging and backups beside each root, immediate rollback on errors, `recover()` for crashes, file-to-folder changes in both directions, refusal when a folder with unmanaged files is in the way.
- `gates.py`: zero files, more than 50% removed, more than 70% smaller; thresholds can be tightened only.
- `retention.py`: heads, active pins, protections and the keep policy.
- `engine.py`: take (no change, nothing to save, quarantine, publish blob then metadata with hash verification), release from quarantine with confirmation, restore with a verified pre-restore snapshot (five kept per game), undo from a pre-restore snapshot, pins, retention with `pruned/` markers, orphan blobs after 24 hours, device sequence.
- `store`: `put_new_file` and `get_to_file` (streamed, hash of what was written or received).
- `resolve.py`: scans skip `.keepsake-` folders; preview can return full file lists.
- `settings.py`: `gateMaxRemovedPercent` (5 to 50) and `gateMaxSizeDropPercent` (5 to 70).
- `app.py`: restore recovery on start; snapshot, list, restore, undo, pin, release and retention methods against a local test store in the runtime folder, run as tracked jobs (updates wait), refused while the game's processes run, when a prefix mismatch is recorded, in safe mode, or when the game is unmatched.

**Frontend**
- Game page "Snapshots (local test store)": take, restore (with confirmation), pin, quarantine with release (with confirmation and the reasons), undo to a pre-restore snapshot, run retention.
- Settings: two sliders for the safety gates, limited to stricter values.

## Decisions made for you (ADR-0007)

1. Restore uses a journal with staging and backups beside the save root; moves aside first, creations last.
2. Pins are write-once cloud objects at `games/<gameKey>/pins/<snapId>.json` (a layout addition before slice 6 freezes it); no unpinning in v1.
3. Retention never prunes `manual`, `merge` or `import` snapshots.
4. Gate settings range from 5% to the default; the zero-files gate is fixed.

## Bugs found by the new tests and fixed

- A file turning into a folder (or back) made the restore fail halfway and leave a mix until the next recovery. Found by the Hypothesis property test; fixed by ordering moves aside before creations, clearing emptied folders, and rolling back immediately on any ordinary error.
- A file present on disk but hidden from the scan (for example by an exclusion) would have been overwritten without a backup. It is now moved aside like a replacement.

## A file for your decision

While reporting the first counterexample, the Codehouse tooling created `tests/test_restore_regression_tmp_path_factory_temppathfactory.py`, marked "Locked: change it only with the person". As generated it is not valid Python (the `@example` line contains a pasted object description), so it cannot run and a full pytest run reports a collection error for it. I have not changed or deleted it. The same counterexample (and its reverse) is pinned correctly with `@example` in `tests/test_restore.py`, and ruff is configured to skip that one file. Recommended: delete the generated file, or let me replace its `@example` line with `@example(old={("winLocalAppData", "0"): b""}, new={("winLocalAppData", "0/0"): b""})`.

## Test results

Local, Windows, Python 3.14.3:

- New: `test_snapshot.py`, `test_restore.py` (two Hypothesis properties: restoring reproduces the scanned state exactly; a crash at any step leaves the old or the new state, never a mix), `test_gates_retention.py` (property over 200 random histories: protected snapshots are never pruned), `test_engine.py`, `test_app_snapshots.py`. Changed: `test_settings.py`. Re-run because they touch changed code: `test_store_local.py`, `test_resolve.py`, `test_app.py`, `test_gameconfig.py`. Result: 148 passed, 2 skipped (`posix`).
- `pnpm run check`: all checks passed.
- Mutation checks: 21 guards broken one at a time; all 21 caught, each by a genuine test failure (syntax errors excluded). The first run missed two: the restore ordering mattered only for rollback, and the manual and merge test snapshots were also protected as heads. A crash-and-recover test for a file turning into a folder was added and the retention test now gives those snapshots children; both mutations are then caught.

## Acceptance (build prompt slice 5)

- Property tests prove that restoring a snapshot reproduces the scanned state exactly: yes.
- Deletion-only and empty snapshots are refused and quarantined: yes (`test_gate_refusal_quarantines_and_never_uploads`).
- Retention never prunes protected snapshots: yes, including the random-history property.
- An interrupted restore leaves either the old state or the new state: yes, property test with a crash at every step plus recovery.

## Known gaps

- Snapshots go to a local test store; slice 6 adds OneDrive and slice 7 the sync decisions.
- Pre-restore snapshots are not uploaded (optional in the build prompt).
- Nothing has run on a device yet; `posix` tests include the symlink escape checks from slice 4.

## On-device checklist

1. `pnpm run test:device`: all `posix` tests pass.
2. Install this build. Open a game you do not mind experimenting with (quit it first).
3. "Take snapshot". Play briefly, quit, "Take snapshot" again. Both appear, newest first, the newest marked "current base".
4. "Restore" the older one and confirm. Launch the game: the older progress is back. Quit.
5. Under "Before each restore", press "Undo to this" on the newest entry. The newer progress is back.
6. Rename the game's save folder, "Take snapshot": expect "refused and quarantined" with the reason. Rename it back. Do not release it.
7. Settings: move a safety gate slider; it should not go above its default.
8. While the game is running, try "Restore": expect a refusal mentioning the running game.
