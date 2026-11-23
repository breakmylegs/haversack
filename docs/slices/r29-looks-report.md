# R29 stage 1: Looks (v0.53.0)

## What changed

- **A new module, Looks** (off by default, not on Windows), with Device, Looks in Gaming Mode and the desktop app (ADR-0091).
- **Boot and sleep animations** (`py_modules/keepsake/looks/animations.py`):
  - **Sources:** a WebM from Videos, Downloads, Animation Changer's sets or Haversack's folder.
  - **What changes:** one of Steam's three videos in `config/uioverrides/movies`.
  - **Safety:** copied, checked by hash and renamed into place. A video already there is kept and put back by **Use Steam's own**. Reset removes only Haversack's own file. Nothing changes while Animation Changer is installed.
- **Theme plugins, read only** (`py_modules/keepsake/looks/themes.py`): CSS Loader and Audio Loader are detected, with their themes and sound packs listed, size-limited.
- **Docs:**
  - the guide's Device page gains a Looks section in place of an outdated "Coming next" (fans and controllers already exist);
  - the Help is rebuilt;
  - ADR-0091, T163, A246 and A247;
  - device run step 52.

## Tests

- **New:** `tests/test_looks.py`, 12 tests plus one POSIX-only test.
- **Mutation testing:** 19 mutants. All are killed except the symlink check, which the POSIX test kills on the device. Two earlier survivors (a backup overwritten, the JSON size cap) gained tests.
- **Regression tests:** `test_modules`, `test_installer`, `test_host`, `test_desktop_calls`, `test_frontend_sidebar`, `test_frontend_navigation`, `test_settings` and `test_help` pass.
- **Checks:** `tsc` for both frontends and eslint on the changed files pass. The gate result is in the pull request.

## Known gaps

- Choosing videos needs WebM files on the device. Sending them from the other handheld is stage 1b, and downloading from steamdeckrepo.com would need an endpoint decision.
- Whether Steam picks the videos up at the next boot or sleep is unverified on our devices (A246).

## On-device checklist

- Device run step 52.
- `pnpm run test:device tests/test_looks.py`, for the symlink test.
