# Separate power limits (R24, v0.43.0)

## What changed

- **The helper:** a new job, `power.set` and `power.read` (`helper/py_modules/keepsake_helper/power.py`).
  - Only the three `ppt_*` firmware attributes.
  - Each value within the firmware's range and step, rising from SPL to FPPT, and only in Custom mode.
  - Ordered writes, and read-back.
- **Keepsake:** `device/powerlimits.py` reads the values and ranges without root and clamps them.
  - Per-game profiles gain `limits`, in `device/performance.py`.
  - Custom is set first; the limits are restored before the mode; a change from outside stops the profile.
- **Screens:** Device, Power, Separate power limits, in Gaming Mode and the desktop app.
  - The Power panel's rows no longer remount on every update: a component defined inside the render is now a plain function.
- **Docs:** ADR-0084, T154, A235, a write allowlist row, the user guide, device run step 41, CHANGELOG and plan.

## Tests

- `tests/test_power_limits.py`: 20 passed.
- Regressions: `tests/test_device_performance.py`, `tests/test_root_helper.py`, `tests/test_frontend_navigation.py`, all passed.
- Mutation tests: 10 mutations on Custom required, the range, step, rising-order and write-order checks, read-back, Keepsake's clamp, Custom for limits, restore order and outside changes. All caught; read-back gained a test after surviving the first run.

## Known gaps

- Whether both Gos expose the attributes on SteamOS 3.9 is unverified (A235, device run step 41).

## On-device checklist

Device run step 41.
