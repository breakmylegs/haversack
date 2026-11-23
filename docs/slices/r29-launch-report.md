# R29 stage 5: launch option presets (v0.60.0)

## What changed

- **Launch options on each game's page,** for Steam and non-Steam games (ADR-0097): five switches for documented Proton variables.
  - **Kept as it was:** the rest of the line, exactly.
  - **The original:** kept the first time, and restored by Put back original.
  - **How Steam is changed:** through `SteamClient` after a press, then read back.
  - **The strict gate:** while it manages a game's options, the presets are refused.
- **Declined:** GE-Proton install, because it would download and install a binary (P9).
- **Store launchers:** their shortcuts are already handled, with no change.
- **R29 is complete.**

## Tests

- **New:** `tests/test_launchopts.py`, 7 tests:
  - composing the line, keeping everything else;
  - switching presets off;
  - which presets are on;
  - bad lines and unknown presets refused;
  - the first original kept;
  - the app's apply and restore;
  - the strict gate guard.
- **Mutation testing:** 11 mutants, all killed.
- **Regression tests:** the host callables test and the navigation rules pass.
- **Checks:** `tsc` and eslint on the changed files pass. The gate result is in the pull request.

## Threat model

T168.

## Known gaps

- Reading a game's launch options needs Steam to have loaded its details. If it has not within 3 seconds, the page asks to open the game's page in the library once.

## On-device checklist

Device run step 58.
