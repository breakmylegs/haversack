# Slice 9 report: Gaming Mode UX complete

Branch `slice/09-gaming-mode-ux`, stacked on `slice/c0-consolidation` (#10). Build prompt section 14 in full and the section 15 health checks and diagnostics, plus the deferred game config revisions (A64) and the v2 amendment for slice 9 (navigation ready for module tabs, Modules placeholder). Design decisions: ADR-0020.

## What changed

**Backend**
- `sync.py`: `SyncEngine.plan` (read-only dry run of the decision table), `conflict_details` (each side with files changed since the base) and `changed_files`. A good push clears the quarantine flag.
- `health.py` (new): the section 15 checks as a pure function, the summary badge, and read-only detection of decky-ludusavi from Decky's plugin folders and `disabled_plugins`.
- `configrev.py` (new): write-once game config revisions (publish, list with validation, newest, concurrent edits).
- `app.py`: `qam_summary`, `sync_now`, `list_conflicts`, `conflict_details`, `recent_history`, `plan_sync`, `finish_setup`, `health_checks`, `game_config_sync`; shared settings published on change and fetched when a game is enabled and on every idle pass, kept pending while offline; `match_games` reports `enabled` and `sync`; `list_snapshots` reports the last sync per device; toasts for idle-pass conflicts, quarantines and sign-in trouble; the idle interval comes from settings; releasing a quarantined snapshot clears the flag; upgraded installs with enabled games skip the wizard; the diagnostics export includes the health checks.
- `settings.py`: `idleSyncMinutes` (10 to 240, default 30), `showSteamApps` (default off), `setupComplete`.
- `main.py`: the new callables.

**Frontend**
- Quick Access Menu: health badge, store and last sync, problems, "Set up Keepsake" until setup is done, current game card, conflicts row, "Sync now", "Open Keepsake". The old "Sync is not available yet" text is gone.
- Tabs Games, Conflicts, History (Saves) and Settings, Updates, Logs, Diagnostics (core), declared as a list tagged by module.
- Setup wizard route `/keepsake-setup` with the seven steps and "Skip setup".
- Conflict modal: "Decide later" focused and on B; two presses for replacing choices; both sides described.
- Games: status icons, "Synced games" filter, Steam games hidden unless enabled in Settings.
- Game page: Steam Cloud note on the enable switch for Steam games, shared settings origin and concurrent edit warning, last sync per device, conflicts open the modal.
- Settings: background sync interval, Show Steam games, Updates link, Run setup again, Modules placeholder.
- Diagnostics: health checks at the top, "Run checks" tests OneDrive.

**Docs**: ADR-0020, threat model T56 to T60, assumptions A105 to A110 and A64 closed, cloud layout row for config revisions, CHANGELOG 0.9.0 (the two Unreleased sections from #8 and C0 merged into it).

## Tests

- New: `test_sync_plan.py` (8), `test_health.py` (6), `test_configrev.py` (7), `test_app_ux.py` (12); changed: `test_settings.py` (+1). All pass.
- Re-run because they cover touched code: `test_settings.py`, `test_sync.py`, `test_sync_invariant.py`, `test_app_sync.py`, `test_app_snapshots.py`, `test_gameconfig.py`, `test_app.py`, `test_app_cloud.py`, `test_diagnostics.py`, `test_identity.py`: 82 passed, 1 skipped (`posix`).
- Mutation checks: 17 guards broken one at a time (plan decisions, changed-file counting, quarantine clearing, stale sessions, decky-ludusavi disabled detection, concurrent-edit rule, foreign revisions, newest ordering, revision numbering, applying shared settings, pending publish, sign-in toast once, current game, upgrade migration, quarantine release, idle interval floor). The first run missed three (quarantine cleared by a good push, same-device sibling revisions, pending publish before applying); tests were added for each and all 17 are now caught.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan). No em or en dashes in the repository.
- Device tests (`pnpm run test:device`): not run from here; part of the on-device checklist.

## Known gaps

- The frontend has no automated tests (as in earlier slices); its behaviour is in the on-device checklist. Type checks and lint pass.
- decky-ludusavi's per-game settings cannot be read (A109), so its health check warns whenever it is active alongside synced games, not per game.
- Config revisions are never pruned; they are small.
- "Run checks" tests OneDrive only; other backends arrive in slice 10.

## On-device checklist (both devices, controller only)

1. Fresh install or Settings, Run setup again: complete all seven steps. The on-screen keyboard opens for the device name. The dry run lists each chosen game with what will happen, and nothing changes until Finish setup.
2. The QAM shows the health badge, OneDrive and last sync. While a synced game runs, "Playing" shows it with its state.
3. Make a conflict (change a save on each device while offline, then go online and launch). Open it from the QAM conflicts row: "Decide later" has the focus, B closes the window and the conflict stays. Choose "Use cloud save": the first press only changes the label, the second resolves it. The other save is in History, pinned.
4. History: restore a snapshot of another game, then undo it from that game's page.
5. Add an exclusion on device A, run Sync now on A, then enable the game (or Sync now) on device B: the exclusion appears on B with "Last changed on <A>".
6. Diagnostics: Run checks. With Wi-Fi off, the cloud check says OneDrive could not be reached. Export diagnostics and check it includes `health`.
7. Settings, Show Steam games: Steam games appear in the Games list and the wizard; off again hides them.
8. Run `pnpm run test:device`.
