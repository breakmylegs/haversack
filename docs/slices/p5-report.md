# P5 report: PC package, install and self-update

P5 of the multi-device re-plan (ADR-0038), built in two changes:
- #51: the package, install and launcher (ADR-0042);
- the self-update, with rollback (ADR-0043).

## What changed

- **The PC package.**
  - **Contents:** `Keepsake-desktop-v<version>.zip` holds the core, the desktop interface, `install.pyw` and `VERSION`.
  - **Build and signature:** it is built deterministically and listed in the signed `SHA256SUMS`.
- **Install.** It goes into the user's own folders, one folder per version, with `current.json` naming the current and previous versions. Start at sign-in uses a `HKCU` Run value or XDG autostart. Uninstall keeps settings and saves.
- **Launcher.** It reuses a running host only after a token-protected check. `--restart` waits for the old host to stop.
- **Self-update.**
  - **Proof:** the release must be signed with the pinned key, and the download must match the signed hash.
  - **Unpack:** each member is checked before anything is written, and `VERSION` must equal the signed version.
  - **Install:** beside the running version, with start-up entries left alone.
  - **Rollback:** "Go back" switches to the previous version.
  - **Where it lives:** host-only API calls and a desktop Updates page.

## Test results

- `tests/test_pcupdate.py`, `tests/test_host.py`, `tests/test_pcinstall.py`, `tests/test_update.py` and `tests/test_signatures.py` all pass.
- Mutation checks: 19 of 20 killed. The survivor is recorded in A171.
- Quality gate: clean after the lint, format and type fixes.

## Known gaps

- The interface has no update notice yet; Updates is a page the user opens. A notice comes with the desktop interface's second pass (P3).
- A real update from one published release to the next needs a release that carries the PC package on both sides. v0.25.0 has none, so the first possible run is from the next release to the one after.

## On-device checklist (PC runs)

1. **Windows PC with Python 3.11 or newer.**
   1. Download the next release's `Keepsake-desktop-v<version>.zip`, unzip it and double-click `install.pyw`.
   2. Check that Keepsake opens in the browser, and starts again after signing out and back in.
2. **When a later release exists.**
   1. Open Updates and choose Check, then Install, then Restart. Confirm the new version is shown under Running.
   2. Choose Go back, then Restart. Confirm the previous version runs.
3. **Linux PC.** Repeat steps 1 and 2, with the app menu entry and XDG autostart.
4. **Uninstall.** Run `python install.pyw --uninstall` and confirm that settings in `%APPDATA%\Keepsake` or `~/.config/keepsake` remain.
