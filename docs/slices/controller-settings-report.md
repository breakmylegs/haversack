# Controller settings and stick lights (R24, v0.47.0)

## What changed

- **Research:** `docs/research/controller-control.md` covers the `hid-lenovo-go` attributes, the power LED routes, coexistence and licences.
- **The helper:** `helper/py_modules/keepsake_helper/controller.py`, jobs `ctrl.read` and `ctrl.set`.
  - An allow-list of attributes, each checked against the driver's values before any write.
  - The light's profile is read first and its speed written last.
  - Every value is read back for up to 250 ms.
  - Resets, calibration, the buggy right-handle gyro and the Windows-only light mode are never offered.
- **Keepsake:** `py_modules/keepsake/device/controller_settings.py`.
  - It reads the settings without root and writes them through the helper.
  - Kept settings are re-applied when the controller comes back or the device wakes.
  - Read-only while Handheld Daemon runs; InputPlumber's settings are left to it.
- **Screens:** Device, Controllers (`src/pages/ControllerSettingsPanel.tsx`) and the desktop app's Controllers page.
- **The power LED is not built** (ADR-0086): every confirmed route needs acpi_call or `/dev/mem`.
- **Docs:** ADR-0086, T158 and T159, A239 and A240, a write allowlist row, the user guide, device run step 47, CHANGELOG and plan.

## Tests

- `tests/test_controller_settings.py`: 11 passed.
- Regressions: `tests/test_device_controllers.py`, `tests/test_root_helper.py`, `tests/test_host.py`, `tests/test_desktop_calls.py`, `tests/test_frontend_navigation.py`. With the new tests, 82 passed and 2 skipped.
- Mutation tests: 12 mutations, all caught. They covered:
  - the allow-list, the range and colour checks, read-back, profile first and speed last;
  - checking before writing, hhd, InputPlumber;
  - re-apply on reconnect and after sleep;
  - the exact device name. A test caught a loose pattern that matched `…61EB.0001.gone`; it is now anchored.

## Known gaps

- On-device: the driver on SteamOS 3.9 and the sleep-time units (A239, A240).
- No power LED.

## On-device checklist

Device run step 47.
