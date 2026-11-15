# Module: Saves

Cloud save sync with the snapshot DAG. This is Keepsake v1, unchanged by v2 except where noted.

| | |
|---|---|
| Flag default | On |
| Spec | `docs/build-prompt.md` (v1), `docs/build-prompt-v2.md` sections 4 (P14) and 7 |
| ADRs | 0001, 0006 to 0011; v2: 0012, 0014 |
| Code | Core packages in `py_modules/keepsake` (snapshot, sync, store, auth, lifecycle, identity, resolve, restore and the rest). Not moved |

## What it does

Pulls the newest cloud save before a game launches, pushes new progress after it exits, raises conflicts whenever both sides changed, and keeps every restore reversible with a verified pre-restore snapshot. Cloud storage is OneDrive (`Apps/Keepsake`), with WebDAV, S3 and Google Drive planned in v1.

## What it writes

- Save files inside the logical roots resolved for each game (v1 write allowlist, build prompt section 8), through journalled restores.
- Its own settings, state, cache and logs in Decky's folders for Keepsake.
- Cloud objects in `Apps/Keepsake` (frozen layout, `docs/cloud-layout.md`).
- Launch options only for the per-game strict launch gate (ADR-0010).

## v2 rules that apply

- **P14 Saves owns save data.** Only Saves writes save files after a game's initial replication. Saves publishes the set of paths it manages through Core so the path validator can refuse other modules' writes there.
- **P19 lock.** Saves jobs take the per-game lock and pre-empt Replication jobs for the same game.
- **Lifecycle bus.** The slice 8 lifecycle code becomes the publisher of `game_started`, `game_frozen`, `game_released` and `game_exited`.
- **Replication hand-off.** Before Replication sends a game, Saves provides a source checkpoint: local saves equal the Saves `base`, or a push runs first. On the target, discovery re-keys the game and adoption is silent because the hashes match.

## Health checks

Sign-in state, store reachability, manifest age, pending pushes, unresolved conflicts, prefix mismatches.

## Remaining v1 slices

9 (Gaming Mode UX, with navigation ready for module tabs and a Modules placeholder), 10 (Ludusavi import), 11 (registry engine, with key-level write exposed as a Core service), 12 (hardening and v1.0.0). See `docs/plan.md`.
