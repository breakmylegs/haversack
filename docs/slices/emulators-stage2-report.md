# Emulators, stage 2: sending a game to the other handheld (R26, v0.49.0)

## What changed

- **The plan** (`replication/emuplan.py`):
  - the game always travels;
  - the emulator and its settings only where the other device lacks them;
  - keys only with the separate tick;
  - Flatpak emulators are refused.

  The offer has its own validator. Destinations are chosen by the receiver, and the summary carries no paths.
- **Receiving** (`replication/emureceive.py`):
  - each part lands in a staging folder beside where it belongs, then moves in only where nothing of that name exists;
  - settings only where there are none;
  - keys owner-only, and the executable bit set on the emulator;
  - the shortcut from the receiver's own Steam ROM Manager parser, never by running it.
- **The link:** the `emu-summary` and `emu-offer` requests, with the emulator branch through the existing offer flow (`replication/offers.py`), and `emulator_peer` and `emulator_send` in the app.
- **Screens:** a Send to button per game with the firmware-and-keys tick, in Gaming Mode and the desktop app.
- **Docs:**
  - the ADR-0087 protocol addendum;
  - T161;
  - the user guide;
  - device run step 49;
  - CHANGELOG and plan.

## Tests

- `tests/test_emuplan.py`: 16 passed, 1 skipped (POSIX).
- `tests/test_emureceive.py`: 5 passed, 1 skipped (POSIX).
- `tests/test_emu_transfer.py`: 6 passed, end to end through the real transfer with a fake link, including a bad offer refused and not stored.
- Mutation tests:
  - 11 on the plan, all caught;
  - 8 on receiving, all caught;
  - 6 on the offer wiring, all caught (an unvalidated offer survived the first run and gained a test).

## Known gaps

- Flatpak emulators are not copied (ADR-0087: a separate System Binary Register decision).
- Keeping the two devices' emulator games in step after a copy is not built yet; each game is sent on request.

## On-device checklist

Device run step 49.
