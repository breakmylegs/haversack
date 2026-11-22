# ADR-0086: The Legion controllers' own settings, the stick lights, and the power LED

- Status: accepted (R24, Peter's request of 22 November 2026; ADR-0075 tier 1, ADR-0083; decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

R24 includes:
- the controllers' own settings: mode, gyro, sleep, touchpad, rumble;
- the RGB stick lights;
- the power LED.

ADR-0078 showed these read-only. The research, `docs/research/controller-control.md`, read the kernel's `hid-lenovo-go` source (v7.1 to v7.4-rc3), InputPlumber, hhd and four Legion plugins. It found:

**The controller settings and lights**
- **The driver** exposes them as sysfs attributes, 0644 root, for the controllers on 17EF:61EB to 61EE. On the Go 1 that needs the 2025 controller firmware.
- **Writes are not reliable on their own.** They report success even when the controller does not answer, so every write needs a read-back.
- **The lights need the driver's write order:**
  - read the profile before any other write to the light;
  - write the speed last.
- **Driver bugs:**
  - `right_handle/imu_enabled` switches IMU bypass;
  - `right_handle/reset` resets the left controller.
- **Other tools:**
  - InputPlumber rewrites `os_mode`, the gyro bypass and touchpad vibration on every reconnect;
  - hhd drives the same controller interface directly.

**The power LED**
- No mainline driver offers it.
- Every working route uses `acpi_call` (the firmware's WMAF method) or `/dev/mem`.
- The `/dev/port` routes are unverified: no source shows them switching the LED.

## Decision

1. **The helper's controller job** (`keepsake_helper/controller.py`, jobs `ctrl.read` and `ctrl.set`):
   - **An allow-list of attributes, each checked against the values the driver's source accepts.** All values are checked before anything is written.
   - **Never offered:**
     - the resets, which are destructive (and one resets the wrong controller);
     - calibration;
     - `right_handle/imu_enabled`;
     - the light's Windows-only `dynamic` mode.
   - **Order and read-back.** The light's profile is read first and its speed written last. Every value is read back for up to 250 ms.
   - **Names.** The device is found by its exact HID name (`…:17EF:61EB.0001` to `61EE`) or the light's symlink.

2. **Keepsake** (`keepsake/device/controller_settings.py`):
   - **Reading needs no root.** It reads the attributes itself, because they are world-readable.
   - **Changes are written through the helper.** "Keep my changes" stores them, and the settings are applied again when the controller comes back: a reconnect, a wake (the wall clock jumps against the monotonic clock) or a reboot. A cheap sysfs check runs every 10 s.
   - **Never fight another tool.**
     - With Handheld Daemon running, everything is read-only.
     - Where InputPlumber is installed, the button chords and touchpad haptics are left to it. The gyro bypass is not offered anyway.

3. **Screens.** Device, Controllers, in Gaming Mode and the desktop app:
   - controller mode, button chords, rumble and its style, FPS mouse DPI, sleep times, the left gyro, the touchpad and its haptics;
   - the stick lights: on or off, effect, brightness, speed and colour.

4. **The power LED is not built.**
   - **The confirmed routes are ruled out.** `acpi_call` breaks P9, and `/dev/mem` is too dangerous.
   - **The rest is unconfirmed.** The only remaining routes are guessed EC addresses through `/dev/port`, and no source shows them working. Writing a guessed EC byte could disturb other firmware state, so under P5 (fail closed) Keepsake does not do it.
   - **What would change it:** a device experiment that reads the Go 2's EC byte 0xC310 before and after switching the LED in Windows or through hhd. It needs Peter's device, and it is recorded here rather than on the device-run list, because it needs tools outside Keepsake.
   - **The other way in** is a kernel driver for WMAF. If one appears, the LED arrives through it.

5. **Write allowlist (helper).** The listed `hid-lenovo-go` attributes of the 17EF:61EB to 61EE device and of `/sys/class/leds/go:rgb:joystick_rings/`.

## Consequences

- **What it needs.** It needs kernel 7.1 or later and, on the Go 1, the 2025 controller firmware; otherwise the page says so. Persistence on the controller itself is unverified, which is why "Keep" re-applies.
- **No power LED.** The page and the user guide say why.
- **Threat model:** T158 and T159. **Assumptions:** A239 and A240. **Device run:** step 47.
