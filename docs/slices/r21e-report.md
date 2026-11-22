# R21 stage 6 report: Wi-Fi power saving and the BIOS check (v0.37.0)

Stage 6 of Peter's Legion Go controls. The decisions are in ADR-0079. With this, every R21 control that needs no root is built.

## What changed

- **steamos-manager:** it now reads `WifiPowerManagement1`, and a new `set_wifi_power_saving` changes it, read back.
- **`keepsake/device/bios.py`:** reads the DMI version and gives the known notes for the Legion Go: N3CN42WW, before v28, before v29, and v29.
- **New calls:** `device_extras` and `device_set_wifi_power_saving`.
- **Where it shows:** Device, Other, and the desktop app's Other page. The page also says the display settings stay in Steam.
- **The Device check "BIOS check".**

## Not done, and why

- **Refresh rate, frame limit, brightness and a "smooth mode":** Steam owns these per game. Writing them would be principle 15 writes that compete with Steam's own controls.
- **HDR and colour fixes:** they would change gamescope state and need X tools.
- **Waiting for Peter's decision on ADR-0075 tier 1:** fans, and the root parts of the battery and controller stages.

## Tests

- **New:** `tests/test_device_extras.py`, 14 tests:
  - five Legion Go BIOS versions;
  - another model;
  - Wi-Fi power saving through steamos-manager, read back;
  - no Wi-Fi interface;
  - the device check, in five states;
  - the app changes Wi-Fi power saving.
- **Regression:** `tests/test_device_performance.py` and `tests/test_device_battery.py`.
- **Mutation tests:** 5 mutations. One survived (the v28 boundary), which led to a stricter assertion. Now all 5 are caught.

## Threat model

T144.

## On-device checklist

`docs/device-run.md` part 4, step 27.
