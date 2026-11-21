# R9 report: games you can stream from another device

Recorded in ADR-0064, which amends ADR-0015 (Peter's two requests and correction of 21 November 2026).

## What changed

- **Presence of each shortcut.** `discovery.shortcut_presence` gives the file's view: `local`, or `unsure` when nothing of the shortcut is found here. It never gives `remote`. A new `presence` field is on every game.
- **`keepsake/remotecopies.py`:**
  - combines Steam's install state with the file; a shortcut in `shortcuts.vdf` is never remote;
  - lists the streaming entries, which exist only in Steam's report;
  - keeps the tidy-up log for Undo;
  - provides the guard against local shortcuts hidden from elsewhere, and the device check's findings.
- **`src/remotecopies.ts`:** reads `appStore` and `collectionStore` (read only), 15 s after start, every 5 minutes, and when the Games page opens.
- **App:**
  - `discover_games` attaches presence;
  - new calls `remote_copies_report`, `remote_copies_status`, `tidy_copies`, `undo_tidy` and `unhide_local`;
  - read-back of `set-hidden` is recorded;
  - `tidy_copies` and automatic tidy-up refuse unless `streamTidyVerified`. That setting is off and not a user setting.
- **Steam Operations Executor:** a new `set-hidden` kind (`SetAppsAsHidden`, read back with `BIsHidden`).
- **Settings:** `tidyAutomatically` (off) and `streamTidyVerified` (off, backend only).
- **Interface:** `TidyCopies` on the Games page and in Settings:
  - the count, and **Show games you can stream from another device**;
  - **Show it again**, from the guard;
  - the tidy-up controls, only when verified.
- **Device check:** `remote-shortcuts`, "Games you can stream from another device".
- **Docs:** ADR-0064, T122, T123, A199 to A202, FAQ, CHANGELOG, device run part 4 step 2 (including the hidden test).

## Peter's correction, and what it changed

The tiles are Steam Remote Play entries, not a Steam bug. A first version marked shortcuts as remote from the file alone: exe missing, no prefix, internal storage. That could drop real games with unusual paths. That rule is gone:
- the file never makes a shortcut remote;
- the name-clash rule that promoted unsure shortcuts is gone;
- the dead filters it needed are removed;
- the `test_slice11` fixture change made for it was reverted, and that fixture's made-up exe path still passes.

The tidy-up is hidden until A201 is verified, and all user-facing text says "games you can stream from another device".

## Tests

- `tests/test_remote_copies.py`, 33 tests:
  - the file's view (never remote), combination, report checks and streaming entries;
  - the guard and the device check's findings;
  - real shortcuts staying listed, and the tidy-up being off until verified;
  - with it verified: tidy-up, Undo, failed read-back and automatic tidy-up;
  - unhiding, the device check, a Windows host, and op validation.
- **Regression:** discovery is used almost everywhere, so every test file that builds a fake Steam was run.
  - `test_storage` changed the dicts `discover_games` returned and relied on them being the cache. They are copies now, so it changes the cache.
- **Fixed on the way:** `test_app::test_startup_notice_after_update_is_given_once` had failed on `main` since the What's new notes were added; it now checks only the versions.
- **Mutation:** 31 mutants of presence, combination, the streaming list, the guard, the tidy-up gate and rules, Undo, the read-back, settings and the device check. All are killed. Two filters that could no longer fire once the file stopped making shortcuts remote were removed rather than kept as dead code.

## Known gaps

- What a device really shows (A199 to A202) is unverified until the device run.

## On-device checklist

- `docs/device-run.md` part 4, step 2, with the hidden test for A201.
