# Fan control (R24, v0.44.0)

## What changed

- **Research:** `docs/research/fan-control.md` covers seven plugins, the kernel and the licences. Facts only: GPL code is not used.
- **The helper:** `helper/py_modules/keepsake_helper/fan.py`, jobs `fan.status`, `fan.set`, `fan.renew`, `fan.release`, `fan.full` and `fan.selftest`.
  - Exact DMI identity, and the Go 2 EC through `/dev/port` with selector read-back, under `flock`.
  - Allow-listed reads, and writes to the override only, read back.
  - Validated firmware or a self-test before any speed.
  - The lease, the 101 °C failsafe, refusal when other fan drivers are present, and hand-back on start, unload and uninstall.
  - The Go 1's `fan_full_speed`.
- **Keepsake:**
  - `device/fancurve.py`: curves, limits, unlock, stepped and smooth, and the hysteresis controller.
  - `device/fans.py`: named, per-mode and per-game profiles; the 2 s loop with a renewed lease; a resend after sleep; read-only when another fan tool is present.
  - App calls, and the Device check "Fan control".
- **Screens:** Device, Fans in Gaming Mode (`src/pages/FansPanel.tsx`) and in the desktop app (draggable SVG curve). "Fans" is added to the static sidebar.
- **Docs:** ADR-0085, T155 to T157, A236 to A238, a write allowlist row, the user guide, device run steps 42 to 44, CHANGELOG and plan.

## Tests

- `tests/test_fans.py`: 29 passed, with a fake EC that models the index protocol byte by byte.
- Regressions: `tests/test_root_helper.py`, `tests/test_power_limits.py`, `tests/test_devicechecks.py`, `tests/test_host.py`, `tests/test_frontend_sidebar.py`, `tests/test_frontend_navigation.py`, `tests/test_desktop_calls.py`, `tests/test_device_performance.py`. With the new tests, 169 passed and 2 skipped.
- Mutation tests: 20 mutations, all caught. They covered:
  - the EC allow-lists, selector and override read-back;
  - the firmware gate, lease, expiry and failsafe;
  - the hot floor, conflicts, self-test and exact model;
  - the curve shape, floor and hottest point, the curve's failsafe and the dwell;
  - read-only with other tools, hand-back when off, and the resend after sleep.

  Override read-back survived the first run and gained a test.

## Known gaps

- **Go 1 has no custom fan table.** It needs acpi_call, which is not used under P9; it will come with the kernel's fan-curve interface.
- **On-device only:** the EC read-back semantics (A236), `fan_full_speed` (A237) and the DMI strings (A238).

## On-device checklist

Device run steps 42 to 44.
