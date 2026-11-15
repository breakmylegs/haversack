# Slice 7 report: sync engine

- Branch: `slice/06-08-cloud-sync-lifecycle` (shared with slices 6 and 8, see the slice 8 report)
- Target version: 0.7.0 (changelog section added; bumped by `pnpm release prepare`)
- Date: 15 November 2026
- Built without your input, at your request. Decisions are in ADR-0009.

## What changed

**Backend**
- `sync.py`: heads from the snapshot DAG; pull before launch (adoption, up to date, local only, cloud only with restore, converged, conflicts); push after exit with fork detection when the cloud moved during play; conflict records with each head's device, time, file count and size; "Use cloud save" (keep local pinned, restore, closing merge), "Use this device's save" (merge with every head as parent, losers pinned), "Decide later"; offline pending state and reconciliation; prefetch of newer heads into verified local staging; idle pass; crash recovery for sessions left open.
- `engine.py`: `take()` can force a snapshot (merges), skip gates for explicit choices and set flags; `restore()` can use a staged blob; device bases published to and read from `games/<gameKey>/bases/<deviceId>/<deviceSeq>.json`; retention protects every device's base.
- `store`: `StoreUnavailable` is shared by all stores (offline detection).
- `gameconfig.py`: "Sync this game" (`enabled`, off by default).
- `app.py`: `sync_pull`, `sync_push`, `resolve_conflict`, `sync_status`, `idle_pass`; idle loop every 30 minutes (first pass a minute after start-up) for enabled games, with the toast "Recovered missed exit backup for <game>".

**Frontend**
- Game page sync panel: "Sync this game", status, "Check before play" and "Save after play" (manual until slice 8), conflict choices with confirmation; the modal's cancel button is "Decide later".
- Backend toasts are shown.

## Decisions made for you (ADR-0009)

1. "Use cloud save" ends with a merge snapshot so history converges to one head (the build prompt's two steps alone would bring the conflict back).
2. Losing sides are pinned for 90 days (at least 30 required).
3. Explicit conflict choices skip the automatic safety gates; the loser stays pinned.
4. A device that never synced a game but has different files uploads them as a new root on exit and raises an adoption conflict, rather than guessing a parent.
5. Games are opt-in ("Sync this game").
6. Game config revisions are deferred to slice 9.

## Test results

Local, Windows, Python 3.14.3:

- New: `tests/sim.py` (two-device simulator: separate save folders and device IDs, one clock three days behind, offline switch, race hook) with `tests/test_sync.py` (16 scenarios: first push and adoption by restore, pull and push with skewed clocks, silent adoption, adoption conflict, both changed with each resolution, fork from the same base and its resolution, decide later, offline then reconcile, offline reconcile with a conflict, a push racing a pull, cloud newer while the game already runs, crash recovery, prefetch makes the launch restore local, resolve needs the game closed, bases published); `tests/test_sync_invariant.py` (randomised sequences on two devices, 60 per run: no version seen at a sync boundary is ever lost); `tests/test_app_sync.py`.
- Re-run because they touch changed code: `test_engine.py`, `test_gameconfig.py`, store and app tests.
- Tests run by name for this slice and the code it touches (`test_sync.py`, `test_sync_invariant.py`, `test_app_sync.py`, `test_engine.py`, `test_gameconfig.py`, `test_app_snapshots.py`, `test_app_cloud.py`, `test_app.py`, `test_store_contract.py`, `test_graph_store.py`): 105 passed.
- `pnpm run check`: everything passes except the secret scan, which correctly flags the locked Codehouse file while git still tracks it (see the slice 5 and 6 reports); it clears when the file is untracked.
- Mutation checks: 12 guards in the sync engine broken one at a time, all caught by the scenario tests. Two findings about the randomised invariant:
  - Dropping a quarantined snapshot was not caught, correctly: its files are still on the device, so nothing the invariant protects is lost.
  - Removing both protections behind "Use cloud save" at once (the kept upload and the pre-restore snapshot) was not caught by the randomised test even after its generator was rewritten around whole actions, because a conflict normally arises after the local files were already pushed. A targeted scenario (`test_use_cloud_never_loses_an_unsynced_local_edit`: conflict, then more local progress, then "Use cloud save") was added and catches the double fault and each single fault. The randomised invariant stays as a broad net; the targeted scenario guards this path.

## Acceptance (build prompt slice 7)

- Two-device simulator with skewed clocks covering no-op, pull, push, adoption, conflict, fork, merge, offline then reconcile, and a push racing a pull: yes.
- Invariant that no file version that ever existed in a snapshot or on a device is lost across randomised sequences: yes, with one stated exception: progress the player overwrites before it was ever synced is the player's own change.

## Known gaps

- Pull and push are manual until slice 8 connects them to launch and exit (with the freeze gate and launch timeout).
- Game config revisions (sharing aliases, custom paths and exclusions between devices) arrive in slice 9.
- Nothing has run on a device.

## On-device checklist

1. Install this build on both devices, signed in to OneDrive, "Use OneDrive for snapshots" on.
2. On device A, open a game, switch on "Sync this game", "Check before play", play, quit, "Save after play".
3. On device B (no saves for that game yet), open the game, switch on sync, "Check before play": the save from A is restored.
4. Play on both without syncing, then "Save after play" on A and "Check before play" on B: a conflict appears with both saves listed. Try "Use cloud save" on B; then on A "Check before play" says up to date.
5. Turn off Wi-Fi on B, "Check before play" (the game is allowed), play, "Save after play" (waits). Turn Wi-Fi on and wait up to 30 minutes, or restart Decky: the save reaches the cloud.
