# Slice 13 report: module framework

Branch `slice/13-module-framework`, stacked on `slice/12-hardening` (#16). v2 spec slice 13 plus the deferred section 10 amendments for v1 slices 3 and 8. ADR-0012 to ADR-0019 were taken as approved per the C0 recommendations (Q8). Implementation decisions: ADR-0024.

## What changed

- `modules.py`: registry with flags, failure isolation, health and "Try again". Saves is registered as a module; the four v2 modules are listed as not yet available.
- `bus.py`: lifecycle bus. `app.py` publishes `game_started`, `game_frozen`, `game_released` and `game_exited`.
- `locks.py`: per-game lock, held by every Saves write path.
- `statedb.py`: one SQLite database with migrations namespaced per module, atomic per step, refusing a newer database.
- `steamops.py` and `src/steamops.ts`: the Steam Operations Executor queue and frontend runner (originals, apply, wait, read back), plus a probe.
- `discovery.py`: launch options, compatibility tool, artwork files and icon per shortcut (v2 section 10, slice 3); compatibility tool for Steam apps.
- `settings.py`: `moduleFlags`. Saves' flag gates game events, the idle loop and sleep snapshots.
- Frontend: live Modules section in Settings; "Probe Steam APIs" in Diagnostics.
- Docs: ADR-0024, threat model T46 partial, T70 to T72, assumptions A126 to A128, CHANGELOG 0.13.0.

## Acceptance

- Disabling a module removes its listeners, jobs and UI: `test_flags_control_start_stop_and_listeners` (no start and no listeners while off, both removed when switched off again) and `test_lifecycle_events_reach_subscribers_and_saves_can_be_switched_off`.
- A forced failure in a stub module leaves Saves fully working: `test_a_failing_module_leaves_saves_working` (the module fails at start, Saves pushes a snapshot and reports running).

## Tests

- New: `test_modules.py` (12).
- Re-run because they cover touched code: `test_discovery`, `test_discovery_games`, `test_settings`, `test_app`, `test_app_sync`, `test_app_ux`, `test_app_snapshots`, `test_slice11`, `test_lifecycle`, `test_app_cloud`, `test_app_backends`, `test_ludusavi`: 137 passed, 4 skipped (`posix`).
- Mutation checks: 13 guards broken one at a time, all caught on the first run:
  - registry: the flag check, listener removal, start-failure isolation and health-failure handling;
  - bus handler isolation and the lock holder record;
  - state database: migration rollback and the newer-database refusal;
  - queue: kind validation and the stale-claim re-offer;
  - app: the Saves gate and the `game_exited` publish;
  - discovery: the compatibility tool capture.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan).

## Known gaps

- Executor write operations have no user yet (they arrive with Replication and Installer) and are unverified on a device.
- The deferred section 10 amendments are now all delivered except slice 11's (delivered in slice 11) and slice 10's (unchanged by design).

## On-device checklist

1. Settings, Modules: Saves shows Running with its health; switch it off, launch a synced game: no pause, no save message; switch it on again.
2. Diagnostics, Probe Steam APIs: the result lists the Steam functions and which exist.
3. Games, a shortcut with launch options and custom artwork: the diagnostics export or the game list data shows them.
4. Run `pnpm run test:device`.
