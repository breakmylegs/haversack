# R29 stage 3: pausing a game (v0.58.0)

## What changed

- **Pause game and Resume game** in the quick access menu's Now playing, while a game runs, with the Device module on (ADR-0094).
- **A separate `Freezer`** with its own record (`paused.json`) and an hour's watchdog, built on the existing PID and start-time rules. Haversack's own freezes keep their 30 seconds.
  - The `Freezer` constructor gains `state_file`, `max_ceiling` and `on_watchdog`. The defaults are unchanged.
  - Any ceiling is capped at an hour.
- **Always released:** on Resume, game exit, the Device module stopping, unload, the next start, and the hour.
- **Never paused** while Haversack's own save-check freeze is under way.

## Tests

- **New:** `tests/test_pause.py`, 8 tests:
  - the freeze keeps 30 seconds and the pause is capped at an hour;
  - the watchdog resumes and tells;
  - a failing notice never undoes the resume;
  - pause and resume;
  - release on exit and on the module stopping;
  - release at the next start after a crash;
  - release on unload;
  - no pause during a save check.
- **Mutation testing:** 11 mutants, all killed. One survivor (the start-up release) led to a tighter test.
- **Regression tests:** `test_freeze` and the host callables test pass, and so do the navigation rules for the new quick menu button.
- **Checks:** `tsc` and eslint on the changed files pass. The gate result is in the pull request.

## Threat model

T166.

## Known gaps

- How Steam's overlay and gamescope show a stopped game is unverified (device run step 56).
- The desktop app has no Pause button. A paused game is a Gaming Mode moment.

## On-device checklist

Device run step 56.
