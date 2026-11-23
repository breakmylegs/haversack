# R29 stage 4: the SD card index (v0.59.0)

## What changed

- **Device, Storage, SD cards and drives** (ADR-0096):
  - every card and drive in Steam's `libraryfolders.vdf`, with its games;
  - names from the app manifests while the card is in, kept in `sdcards.json` for when it is out;
  - non-Steam games whose program is on the card;
  - inserted cards first.
- Read only, in Core.
- **Not built, with reasons:**
  - orphaned compatdata clean-up (a prefix may hold saves, P14);
  - one-tap Bluetooth (already in Reconnect help);
  - link speed (already a Device check).

## Tests

- **New:** `tests/test_sdcards.py`, 6 tests:
  - the listing, and the internal library and tools left out;
  - a card that is out keeps its names;
  - nothing changed;
  - broken files;
  - a card seen twice;
  - inserted cards first.
- **Mutation testing:** 9 mutants. All killed after one new test and the removal of a redundant filter.
- **Regression tests:** the menu tests and the host callables test pass.
- **Checks:** `tsc` and eslint on the changed files pass. The gate result is in the pull request.

## Threat model

T167.

## Known gaps

- A250: that Steam keeps a removed card's entry is unverified.
- The desktop app has no Storage page, so the index is in Gaming Mode only.

## On-device checklist

Device run step 57.
