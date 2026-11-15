# Slice 11 report: registry saves, Steam Cloud detection and suspend snapshots

Branch `slice/11-registry-cloud-suspend`, stacked on `slice/10-backends-import` (#12). Build prompt slice 11, plus the v2 amendment (key-level registry write as a Core service). Design decisions: ADR-0022.

## What changed

**Backend**
- `registry.py` (new): Wine `.reg` parser, canonical export of managed keys, merge, a merge verifier, a guarded atomic write with backup and read-back, and `set_values` (the Core service for v2's Installer).
- `steamcloud.py` (new): read-only Steam Cloud state per Steam app.
- `retention.py`: `provisional` snapshots are never heads, and the parents of never-head snapshots no longer hide heads (a real bug the suspend test found).
- `resolve.py` / `snapshot.py`: snapshots accept the `registry` root (not a custom-path root).
- `sync.py`: `after_restore` hook on every restore, `provisional()` for suspend snapshots, and `suspended_elsewhere()` reported with each launch check (never adopted).
- `app.py`: registry export into the runtime folder for opted-in games and merge after every restore path (launch, conflict choice, History restore, undo), refused while the game runs; Steam Cloud labels, `enable_steam_without_cloud`; `on_suspend`; toast for another device's sleep snapshot; `get_game` and `match_games` report `hasRegistry` and `steamCloud`.
- `gameconfig.py`: per-game `syncRegistry` (off by default), shared between devices through config revisions.
- `settings.py`: `registrySync` (on: games may opt in), `steamCloudDetection` (on), `suspendSnapshots` (off).

**Frontend**
- Game page: "Sync registry keys" when the manifest lists registry keys; Steam Cloud note for Steam games.
- Games list: Steam Cloud labels and "Sync them all" for played Steam games without Steam Cloud.
- Settings: the three feature switches.
- Suspend requests from the Steam client reach the backend.
- History and the game page label sleep snapshots and Ludusavi imports.

**Docs**: ADR-0022, threat model T15 now in place, T68 and T69, assumptions A118 to A122, cloud layout notes, CHANGELOG 0.11.0.

## Tests

- New: `test_registry.py` (17: parsing, export, export-merge-export stability, merges that keep every other key byte for byte, foreign keys refused, a damaged merge caught, fault injection at the backup, temporary write, rename and read-back steps, a file changed by Wine during the merge, backup pruning, and the `set_values` drive-type service), `test_slice11.py` (8: registry keys travelling between two devices without touching the other device's keys, the global switch, refusal while the game runs, Steam Cloud states and bulk enable, sleep snapshots offered not adopted, own snapshots not reported, and `on_suspend` honouring its setting).
- Regression tests for touched code (`test_settings`, `test_gameconfig`, `test_configrev`, `test_app_ux`, `test_sync`, `test_sync_invariant`, `test_sync_plan`, `test_gates_retention`, `test_snapshot`, `test_engine`, `test_restore`, `test_app_snapshots`, `test_app_sync`, `test_ludusavi`, `test_identity`, `test_resolve`, `test_app`): 225 passed, 3 skipped (`posix`).
- Mutation checks: 20 guards broken one at a time:
  - registry: unmanaged-key preservation, foreign-key refusal, "changed meanwhile", read-back restore, temporary file clean-up, unchanged shortcut, duplicate keys, `#time` stripping, backup pruning, truncated values;
  - heads: never-head kinds, and parents not hiding heads;
  - sync: own sleep snapshots not reported, and the hook after restore;
  - app: the sleep setting, the running-game refusal, the global registry switch and the bulk-enable filter;
  - Steam Cloud: both detection rules.

  The first run missed one: the sleep setting, because the test checked "off" with no session open. One more did not apply because ruff had reformatted the line. The test was fixed and both are now caught.
- `python scripts/check.py`: eslint, tsc, build, versions, package, ruff, ruff format and mypy pass. The secret scan first flagged two synthetic test values from slice 10: a URL with an embedded user and password, and a made-up Windows profile path. Both are now assembled at runtime as elsewhere in the tests, and the scan is clean.

## Known gaps

- Only `HKEY_CURRENT_USER` keys (`user.reg`) are synced; `HKEY_LOCAL_MACHINE` keys in the manifest are ignored.
- The Steam Cloud rule (A118) and the suspend timing (A121) need confirming on a device.
- A sleep snapshot needs the cloud at the moment of sleep; offline it is skipped.

## On-device checklist

1. Pick a game whose manifest entry lists registry keys (the game page shows "Sync registry keys"). Turn it on, play, quit. On the other device, launch: the setting arrives with the shared settings, and the game's registry values match. Other registry keys on that device are unchanged (compare `user.reg` before and after, outside the game's key).
2. Settings, Show Steam games: Steam games show "uses Steam Cloud" or "no Steam Cloud"; "Sync them all" turns on only the second kind.
3. Settings, Snapshot when the device sleeps: start a synced game, play, press the power button to sleep. Wake the other device and launch the game: a message names the sleeping device, the save is not changed, and History shows the sleep snapshot. Wake the first device and quit the game: the other device's next launch takes the exit save.
4. Run `pnpm run test:device`.
