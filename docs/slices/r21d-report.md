# R21 stage 5 report: controllers, read-only (v0.36.0)

Stage 5 of Peter's Legion Go controls. The decisions are in ADR-0078.

## What changed

- **`keepsake/device/controllers.py`** reads what the kernel shows. It writes nothing and opens no hidraw device. It reads:
  - controller batteries (power supplies with scope Device);
  - `hid-lenovo-go` settings: mode, rumble, firmware, gyro, auto-sleep and the touchpad;
  - the `joystick_rings` LED;
  - whether InputPlumber or Handheld Daemon is running.
- **A new call:** `device_controllers`.
- **Where it shows:** Device, Controllers, and the desktop app's Controllers page.
- **The Device check "Controllers"** records what each device's kernel shows.

## Not done, and why

- **Changing the controllers' settings and the stick lights:** the files are root-write only, so this is tier 1, waiting for Peter.
- **Remapping, dead zones and gyro:** Steam Input already does these per game, so Keepsake points to it.
- **InputPlumber remapping:** it would duplicate Steam Input, and it runs only on Bazzite. It is left for a later decision.

## Tests

- **New:** `tests/test_device_controllers.py`, 5 tests:
  - batteries, lights and tools;
  - an older kernel shows nothing;
  - the device check, in two states;
  - the Legion controller settings (POSIX only, because HID folder names hold colons; it runs on the device).
- **Regression:** `tests/test_devicechecks.py`.
- **Mutation tests:** 4 mutations, all caught.
- **A fix found on the way:** on Windows, `os.path.join` reads a component like `*:rgb:...` as a drive and drops the folders before it. The LED pattern is now joined by hand.

## Threat model

T143.

## On-device checklist

`docs/device-run.md` part 4, step 26. Run `python scripts/test_on_device.py tests/test_device_controllers.py` on the device for the POSIX test.
