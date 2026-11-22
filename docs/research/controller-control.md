# Legion controllers, stick lights and the power LED: interfaces and safety

Research of 22 November 2026 for R24 (ADR-0086). Facts only: no code from these projects is used.

## The kernel driver `hid-lenovo-go` (mainline from v7.1, unchanged to v7.4-rc3)

**IDs.** It binds 17EF:61EB, 61EC, 61ED and 61EE.
- The Go 2 always uses these IDs.
- The Go 1 uses them only after the 2025 controller firmware. Before that it reports 6182 to 6185 and has no sysfs interface.
- The driver keeps one global state, so it supports one controller per machine.

**Paths.** `/sys/bus/hid/devices/0003:17EF:61Ex.NNNN/`, with `left_handle/`, `right_handle/`, `touchpad/` and `tx_dongle/`. The stick rings are `/sys/class/leds/go:rgb:joystick_rings`, a symlink into the HID device's `leds/`.

**Permissions.** Read-write files are 0644 root, read-only 0444, write-only 0200.

**Reads and writes.**
- Reads query the controller live.
- Writes return success even when the controller does not answer (a driver bug), so every write needs a read-back. Reads may briefly return the old value; retry for about 250 ms.

| Path | Values | Notes |
|---|---|---|
| `mode` | `xinput` `dinput` | |
| `os_mode` | `windows` `linux` | Built-in button chords. InputPlumber rewrites it on every bind |
| `rumble_intensity` | `off` `low` `medium` `high` | |
| `fps_mode_dpi` | `500` `800` `1200` `1800` | |
| `{left,right}_handle/auto_sleep_time` | 0 to 255 | Units not stated; treated as minutes (0 = off) by other tools. Unverified |
| `left_handle/imu_enabled` | `true` `false` | **`right_handle/imu_enabled` really switches IMU bypass (driver bug)**: not offered |
| `{left,right}_handle/rumble_mode` | `fps` `racing` `standard` `spg` `rpg` | |
| `touchpad/enabled`, `touchpad/vibration_enabled` | `true` `false` | InputPlumber sets vibration off on every bind |
| `touchpad/vibration_intensity` | `off` `low` `medium` `high` | |
| LED `enabled` | `true` `false` | |
| LED `mode` | `dynamic` `custom` | Use `custom`; `dynamic` is a Windows sync mode |
| LED `effect` | `monocolor` `breathe` `chroma` `rainbow` | |
| LED `profile` | 1 to 3 | **Read or write it before any effect, speed, brightness or colour write**, or those go to the profile command |
| LED `speed` | 0 to 100 | **Write it last**: the driver's remembered value can invert after a read |
| LED `brightness` | 0 to 100 | |
| LED `multi_intensity` | three integers, each 0 to 100 (kernel 7.2 and later) | Red, green, blue |

**Not offered:**
- `reset_mcu` and `…/reset`, which are destructive (and `right_handle/reset` resets the left controller);
- the calibration files;
- `right_handle/imu_enabled`.

**Persistence** across reboot or reconnect is unverified. Tools re-apply on bind and after resume.

## The power LED

- **The light is a single bit, where 0 means on:**
  - Go 1: `LEDP`, memory region `ECMM` 0xFE0B0352 bit 5. From BIOS 35, `LEDM` at 0x58 bit 0 also controls breathing while asleep.
  - Go 2: `LPBL`, `ERAM` 0xFEEC2310 bit 6.
- **The firmware's method** is `\_SB.GZFD.WMAF` (GUID 8C5B9127-ECD4-4657-980F-851019F99CA5). No mainline driver binds it, so there is no LED class device and no firmware attribute.
- **Every working route uses acpi_call or `/dev/mem`.** The `/dev/port` routes, the standard EC ports and the Go 2's indirect 0xC310 bit 6, are unverified: no source shows them switching the LED.

## Coexistence

- **InputPlumber** (GPL-3.0; facts only).
  - On every bind its udev rule writes `os_mode=linux`, `imu_bypass_enabled=true` and `touchpad/vibration_enabled=false`.
  - It does not touch RGB.
  - Detect it by its rule file `99-inputplumber-device-setup.rules`, or by a running `inputplumber`.
- **Handheld Daemon (hhd)** (LGPL-2.1). It drives the controller's hidraw config interface directly, which collides with the kernel driver. Detect it by the running `hhd` process.

## Licences

| Source | Licence |
|---|---|
| Linux kernel | GPL-2.0 (facts from its ABI and source only) |
| InputPlumber | GPL-3.0 |
| hhd | LGPL-2.1 |
| LeGo-decky-toolbox | MIT |
| LegionGoLED | MIT |
| LegionGo2Companion | BSD-3-Clause |
| LegionGoRemapper | BSD-3-Clause |
