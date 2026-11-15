# Slice 8 report: lifecycle integration

- Branch: `slice/06-08-cloud-sync-lifecycle` (slices 6, 7 and 8 together, see below), stacked on `slice/05-snapshots-clean`
- Target version: 0.8.0
- Date: 15 November 2026
- Built without your input, at your request. Decisions are in ADR-0010.

## Why three slices share one branch

Git writes were blocked for most of slices 6 to 8, so all three were built in one working tree. The same files (the app core, settings, frontend bindings) carry changes from all three, and splitting them into separate honest commits needs interactive staging, which is not available here. They are committed together, with a report per slice (06, 07, 08).

## What changed

**Backend**
- `lifecycle.py`: app ID normalisation (signed, unsigned, 64-bit shortcut ID), polling helper, abort flag for abandoned pulls, launch option wrapping and the store of originals, gate handshake files with one-off tokens, played-without-Keepsake check, the toast texts from the build prompt.
- `bin/keepsake-gate`: the strict launch gate, a shell script (no binary).
- `app.py`: `on_game_event` for start and exit; `_launch` (strict handshake, else freeze with the watchdog, pull with the configurable timeout, release in `finally`; when the game cannot be held, never restore under it); `_exit` (wait for the game to end, push, toasts); `strict_wrap` and `strict_unwrap`; session records; played-without-Keepsake warning in the idle pass.
- `gameconfig.py`: per-game `launchGate` (freeze, strict, off). `settings.py`: `launchPullTimeout` (5 to 60, default 20) and `toastOnSync`.
- `scripts/package.py`: `bin/` scripts are packed with LF line endings.

**Frontend**
- `lifecycle.ts`: forwards lifetime notifications and game action starts.
- Game page "Launch gate" (Freeze, Strict, Off), strict mode with a confirmation; launch options read and set through the verified Steam APIs.
- Settings: launch check timeout slider and "Show a message after each save".

## Test results

Local, Windows, Python 3.14.3:

- New: `tests/test_lifecycle.py` (23 tests: ID normalisation, launch option wrapping and exact round trip, originals never overwritten, token handshake, played-without check, and app-level launch with a synthetic `/proc`: restore while frozen with freeze then release, game not found in time never restored under, timeout releases the game and the late pull cannot restore, a forced failure still releases the game, strict handshake, exit save, events for every ID shape, played-without warns once and saves). Changed: `test_scripts.py` (CRLF script packed as LF).
- Re-run because they touch changed code: `test_settings.py`, `test_gameconfig.py`, `test_app_sync.py`, `test_app.py`, `test_freeze.py`, `test_procs.py`, `test_sync.py`: 104 passed, 2 skipped (`posix`).
- `pnpm run check`: all checks passed.
- Mutation checks: 11 guards broken one at a time, all caught.

## Acceptance (build prompt slice 8)

- Playing on one device and launching on the other loads the newer save with no Desktop Mode: needs the device checklist.
- Killing Steam during a game produces a recovered backup on the next start: implemented (session left open, idle pass a minute after start-up, toast "Recovered missed exit backup"); tested in slice 7 and through the app here; device check below.
- The watchdog always releases a game in a forced-failure test: yes (`test_unexpected_failure_still_releases_the_game`, plus the slice 1 watchdog tests).
- The strict wrapper round-trips launch options exactly: yes (`test_strict_wrap_and_unwrap_round_trip_exactly`).

## Known gaps

- Whether Steam reports a shortcut's real app ID in lifetime notifications is still unverified (ADR-0001). Every ID shape is accepted.
- Freezing has only been tested against a synthetic `/proc` here; the real `SIGSTOP` test is a `posix` test for the device.

## On-device checklist

1. `pnpm run test:device`: all `posix` tests pass (including the real freeze and watchdog test).
2. On both devices, enable "Sync this game" for one shortcut and one Steam game.
3. Play the shortcut on device A and quit: toast "Saved ... to the cloud."
4. Launch it on device B: it pauses for a moment and starts with A's progress.
5. Start the game on B and kill Steam (or hold the power button and restart). After Decky starts again, within about a minute: "Recovered missed exit backup for ...".
6. Switch the shortcut to "Strict" and accept. Launch: the game waits briefly, then starts. Check its launch options in Steam show the gate in front of your options. Switch back to "Freeze": the launch options are exactly what they were.
7. Turn off Wi-Fi and launch: after the timeout the game starts with "Cloud check timed out. Playing the local save."
