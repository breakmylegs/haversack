# Slice 20b report: controls for games kept in step

The second part of slice 20 (ADR-0060). Slice 20 is now complete. The minor release it calls for waits for the device checks.

## What changed

- **Gaming Mode:**
  - **The game page:** a "Kept in step" panel (`InStepPanel.tsx`) for a linked game, with its state, **Updates** (Ask me, Take them by themselves, Off), **Check now** and **Send update**.
  - **Devices:** update offers show **Apply update** and **Keep mine**. When both sides changed, **Apply update** asks, offering Take theirs or Keep mine. An update in progress has **Stop update**, which leaves the game as it was.
- **Desktop:** the same update controls in the offers card, and a "Games kept in step" card on Devices, with Updates, Check now and Send update.
- **Docs:** the user guide (Keep a game in step), the changelog and the plan.
- **No backend change.** Threat model: no change, because the controls only use the 20a calls.

## Test results

- No Python changed, so there are no Python tests to run for this part. The 20a tests cover the calls these controls use.
- **Frontend:** `tsc`, the desktop build and eslint are clean.
- `python scripts/check.py`: all checks passed.

## On-device checklist

Slice 20's checks are in `docs/slices/20a-report.md`, using these controls.
