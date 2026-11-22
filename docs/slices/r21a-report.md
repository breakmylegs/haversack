# R21 stage 1 report: device readings (v0.33.0)

The first stage of Peter's Legion Go controls (item 3 of 21 November 2026): read-only status. The decisions are in ADR-0074.

## What changed

- **`keepsake/hardware.py`** (Core) reads world-readable sysfs files only. It never writes, and never reads a serial number. It reads:
  - every hwmon chip's temperatures, fans and power;
  - the system battery, with its charge limit where the kernel exposes it;
  - GPU power;
  - the BIOS version and date;
  - the ACPI platform profile, in both the new and the old form, shown in Legion Space's words;
  - CPU boost, SMT and the cores online.
- **`device_readings`** is a new call. Device, Status shows the readings every 2 seconds in Gaming Mode, and the desktop app shows them as a sensor table.
- **The Device check "Device readings"** passes with temperatures, fans and a mode, warns without a fan reading or mode, and fails with no temperature. It records what each device exposes, for the next stages.

## Not done, and why

- **No controls yet.** Stage 2 (TDP and per-game profiles) starts with the research document and the permission-model ADR. Anything needing root waits for Peter's approval.
- **Unknown names on Peter's devices.** Which fan reading and mode file each device exposes is not known until the device run's Device check.

## Tests

- **New:** `tests/test_hardware.py`, 7 tests:
  - a Legion-like tree reads everything, with no serial number, the first system battery only, and a controller's battery ignored;
  - the older profile file, and missing files;
  - a broken reading is left out;
  - the device check in three states;
  - the app serves the readings.
- **Regression:** `tests/test_devicechecks.py`.
- **Mutation tests:** 8 mutations. One survived, the first-battery rule, which led to a new test case; now all 8 are caught.

## Threat model and assumptions

- **Threat model:** T140.
- **Assumptions:** no new ones. Which files each device has is exactly what the Device check records.

## On-device checklist

`docs/device-run.md` part 4, step 22.
