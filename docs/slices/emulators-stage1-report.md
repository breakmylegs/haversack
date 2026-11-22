# Emulators, stage 1: detection (R26, v0.48.0)

## What changed

- **Research:** `docs/research/emulators.md` covers EmuDeck, RetroDECK, standalone emulators, grouping, copying options, hash sources and licences.
- **`py_modules/keepsake/replication/emulators.py`** (read-only):
  - EmuDeck and RetroDECK setups, and standalone emulators;
  - games grouped one unit each (`.m3u`, `.cue`, `.gdi`, PS3 and Wii U folders), never reaching outside the ROM folder;
  - key, firmware and BIOS files counted by name and place, never opened.
- **The app** gets `emulator_setup` and the Device check "Emulator setup", with counts only.
- **Screens:** Games and devices, Emulators, in Gaming Mode (`src/pages/EmulatorsPanel.tsx`) and the desktop app.
- **Docs:** ADR-0087 (stage 1, plus the decisions fixed for stage 2), T160, the user guide, device run step 48, CHANGELOG and plan.

## Tests

- `tests/test_emulators.py`: 8 passed. One test fails if any key or BIOS file is opened.
- Regressions: `tests/test_devicechecks.py`, `tests/test_host.py`, `tests/test_frontend_sidebar.py`, `tests/test_frontend_navigation.py`, `tests/test_desktop_calls.py`, `tests/test_shortcuts.py`. With the new tests, 66 passed and 1 skipped.
- Mutation tests: 6 mutations, all caught:
  - a cue escaping the ROM folder;
  - playlists not first;
  - folder games split;
  - junk files counted;
  - secrets not counted;
  - BIOS files opened.
- Assumptions: no change. The paths come from the research, and device run step 48 checks them.

## Known gaps

- Copying is stage 2 (ADR-0087).

## On-device checklist

Device run step 48.
