# Slice 19b report: the Send and Offers pages

The second part of slice 19 (ADR-0059 and its addendum). Slice 19 is now complete.

## What changed

- **Gaming Mode:**
  - a **Send to <device>** panel on a non-Steam game's page (`SendPanel.tsx`), shown while Replication runs, with a confirmation;
  - **Games between devices** on Devices: offers with **Accept** (it asks before copying a missing compatibility tool) and **Decline**, games being received with **Stop and remove** (confirmed), finished ones with **Clear from this list**, and this device's own offers with **Withdraw**.
- **Desktop:** the same Send buttons on the Games page, and the same offers card on Devices.
- **Backend:** `dismiss`, which forgets a finished offer and keeps the game, and the `replication_dismiss` call in `main.py`, the PC host and `backend.ts`.
- **Docs:**
  - the user guide, `docs/user/replication.md`: Send a game;
  - the changelog, the plan and the ADR-0059 addendum.
- **Threat model: no change.** The pages only call the 19a calls, and `dismiss` deletes nothing.

## Test results

- **The feature:** `tests/test_replication_sendgame.py` (39, one new for `dismiss`). The new test was proven by breaking the check it guards: it fails, and passes once restored.
- **Regression for what changed:** `tests/test_host.py`, which checks that the call lists match.
- **Frontend:** `tsc`, the desktop build and eslint are clean.
- `python scripts/check.py`: all checks passed.

## Known gaps

- Ludusavi `config` tags are not yet excluded by default (slice 20).

## On-device checklist

The acceptance run is in `docs/slices/19a-report.md`, using these buttons.
