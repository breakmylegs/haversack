# R29 stage 2: library extras (v0.56.0)

## What changed

- **Artwork for any non-Steam game** (ADR-0093):
  - The game's page shows **Artwork** when the game lacks a cover, wide cover, background or logo.
  - Find artwork queues SteamGridDB's images for only those kinds, through Steam's artwork call. Nothing already set is replaced.
  - The code: `Installer.queue_game_art` (shared with streaming tiles through `_queue_art`), `game_art_status` and `game_art_apply`, and `src/pages/GameArtSection.tsx`.
- **ProtonDB on the library badge:**
  - `Advisor.protondb_line` reads the index already on the device, only while the ProtonDB source is on. It never downloads, caches up to 500 games, and is used for Steam games only.
  - The badge shows it as a second line, or alone when there is no saves line.
- **Docs:** the guide's Install and Advisor pages, the Help rebuilt, ADR-0093, T165 and device run step 54.

## Tests

- **New:** `tests/test_library_extras.py`, 6 tests.
- **Mutation testing:** 12 mutants, 11 killed. The survivor was a redundant condition (zero reports already give no share), and it was removed.
- **Regression tests for the touched files:** `test_badges_and_stream_art`, `test_advisor_protondb` and the host callables test pass (222).
- **Checks:** `tsc` and eslint on the changed files pass. The gate result is in the pull request.

## Threat model

T165.

## Known gaps

- Deferred: syncing TabMaster and SteamGridDB settings (their file names are unverified), and the PlayTime import.
- The artwork section is in Gaming Mode only.

## On-device checklist

Device run step 54.
