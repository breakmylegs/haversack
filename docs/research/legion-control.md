# Legion Go and Legion Go 2 control: existing tools, interfaces and permissions

Research for R21, Peter's item 3 of 21 November 2026: make Keepsake the main app for the Legion Go and Legion Go 2. It covers the existing tools and their features, the kernel and system interfaces, the firmware rules, and parity with Lenovo Legion Space on Windows. Three research passes read project sources, kernel source at each release tag, and vendor and press pages (22 November 2026). No code was copied: the tools are listed for their features, mechanisms and licences only.

Facts marked unverified need a device run: Device check "Device readings" (v0.33.0) and the checks of each later stage.

## Summary for Keepsake

1. **Every kernel control is root-write only.** That includes:
   - the platform profile;
   - the power-limit firmware attributes;
   - the hwmon fan target;
   - the battery's `charge_types`;
   - every `hid-lenovo-go` controller and RGB attribute;
   - the backlight.

   Keepsake's backend runs as the user (P8), so it cannot write them directly.
2. **steamos-manager is the route that needs no root.** Valve's user daemon on the session bus (`com.steampowered.SteamOSManager1`) offers, among others:
   - the TDP limit;
   - the performance profile;
   - CPU boost;
   - the GPU clock;
   - the charge limit;
   - Wi-Fi power saving.

   Valve's own device file supports the Legion Go (83E1) and Legion Go 2 (83N0, 83N1), and Bazzite 44 ships it too. Keepsake already has a pure-Python D-Bus client (`keepsake/desktop/dbus.py`), so this needs no binary and no new library.
3. **Steam owns some settings already.** Steam's own quick access menu writes TDP, refresh rate and the charge limit through the same routes. Keepsake must not fight it: it reads Steam's per-game settings and stays read-only wherever Steam is managing a value.
4. **Root-only controls wait for the permission ADR.** These are:
   - fan curves and fan speed (no kernel fan-curve interface exists yet);
   - separate SPL, SPPT and FPPT;
   - RGB;
   - the controller's hardware settings;
   - the power LED.

   ADR-0075 sets out how they could be done, and they ship only after Peter approves it.
5. **acpi_call is ruled out.** It is out of tree, GPL, root-only and absent from SteamOS.

## Legion-specific tools

Every tool here runs as root (the Decky root flag), so none can be adopted as-is under P8 and P9:
- two install a udev rule that opens every Lenovo USB device to all users;
- two compile `acpi_call` on the device, from GPL-3.0 source;
- one downloads a `ryzenadj` binary;
- some poke EC registers through `/dev/port` or `/dev/mem`.

Names:
- **"LeGoTDP"** is deleted (404); its code went into LegionGo2Companion.
- **"Legion Go Companion"** is the name of LegionGo2Companion's desktop app. The repository `r0bledas/LegionGoCompanion` is a Windows-only fork of Handheld Companion (CC BY-NC-SA 4.0), so it is out of scope.
- **"Legion Center"** is `InnoVision-Games/legion-center`.

### LegionGoRemapper (aarron-lee)
- **Repository:** https://github.com/aarron-lee/LegionGoRemapper
- **Licence:** BSD-3-Clause; the bundled pyhidapi wrapper is MIT.
- **Activity:** v0.3.0 (12 March 2026), now in maintenance mode.
- **Devices:** the original Go only. On the Go 2 it runs only a brightness bridge.
- **Features:**
  - RGB, with per-game profiles;
  - back-button remapping (Y1 to Y3, M2, M3), in X-input mode only;
  - touchpad on or off, and gyro to a stick;
  - through acpi_call: the 80% charge limit, custom fan curves (BIOS v28 and later), full fan speed and the power LED;
  - ambient light auto-brightness.
- **Mechanisms:**
  - hidraw vendor reports (VID 17EF; PIDs masked to 0x6180 or 0x61E0; usage page 0xFFA0), through libhidapi via ctypes;
  - `\_SB.GZFD.WMAA/WMAB/WMAE/WMAF` through `/proc/acpi/call`.
- **Privilege:** the root flag, plus a sudo installer that writes a udev rule giving 0666 on all 17ef USB devices.
- **Problems:** hhd overwrites its LEDs; remapping is broken on current SteamOS; the charge limit cannot be turned off.

### Legion Center (InnoVision Games)
- **Repository:** https://github.com/InnoVision-Games/legion-center
- **Licence:** BSD-3-Clause.
- **Activity:** v0.1.1 (25 August 2026).
- **Devices:** the original Go only.
- **Features:** power LED, back-button remap, touchpad, gyro, per-game profiles, the 80% charge limit, custom fan curves, and an "Install Fan Support" button.
- **Mechanisms:**
  - the charge limit through the native `charge_types` (`Standard` or `Long_Life`), with ACPI as a fallback;
  - fans and modes through acpi_call;
  - its fan installer builds acpi_call with DKMS and writes to the SteamOS system partition, and needs a repair after each kernel update.
- **Privilege:** the root flag and a udev rule.

### LeGo-decky-toolbox (kazzzzzzzzzzuya)
- **Repository:** https://github.com/kazzzzzzzzzzuya/LeGo-decky-toolbox
- **Licence:** MIT, but it contains GPL-3.0 acpi_call source.
- **Activity:** created 13 November 2026; v1.0.6 (21 November 2026). Several features are not yet verified on a device.
- **Features:**
  - **Power:** the platform profile with a Custom watt slider; Auto TDP to a frame-rate target, with per-game memory; per-game profiles; CPU boost; a per-game Longest battery, Balanced or Smoothest mode; a battery playtime goal; a MangoHud frame cap with matching refresh rate.
  - **Fans:** a 10-point table with a safety floor, presets, curves per game and per charger, re-applied when the firmware drops it.
  - **Lights:** RGB, and the power light, including off while asleep.
  - **Controls:** button swaps and the gyro type Steam sees, through InputPlumber; back-button remap; touchpad.
  - **Motion:** a DSU (CemuHook) motion server.
  - **Other:** charge limit, speaker EQ, sleep-drain logging, and holding Steam client updates.
- **Mechanisms:**
  - the platform profile and the `lenovo-wmi-other` `ppt_*` attributes; cpufreq boost;
  - fans through acpi_call;
  - the power LED through WMAF, `/dev/mem` or `/dev/port`;
  - controllers through hidraw;
  - InputPlumber over D-Bus.
- **Privilege:** "runs as root". It loads a kernel module it compiles itself, and edits launch options and `steam.cfg`.
- **Advice in its README:** uninstall the other tools, and turn off Steam's own TDP limit.

### LegionGo2Companion (Rayekkk)
- **Repository:** https://github.com/Rayekkk/LegionGo2Companion
- **Licence:** BSD-3-Clause. It bundles pyudev (LGPL-2.1) and downloads ryzenadj (LGPL-3.0).
- **Activity:** 2.4.2 (12 November 2026).
- **Devices:** the Go 2 83N0 fully; 83N1 in beta; the Go and Go S in early beta.
- **Features:**
  - **TDP:**

    | Preset | SPL / SPPT / FPPT |
    |---|---|
    | Silent | 8 / 15 / 20 W |
    | Balanced | 16 / 25 / 30 W |
    | Performance | 20 / 32 / 35 W |
    | Maximum | 35 / 37 / 45 W |

    Also custom three-way or single-slider limits, per-game profiles with optional battery and charger settings, boost and EPP, and up to 50 W through ryzenadj.
  - **Fans (Go 2):** an 8-point RPM curve from 1500 to 4800 RPM, with a watchdog.
  - **Controllers:** vibration and its modes; RGB and the power light; button mapping through InputPlumber; gyro source and auto-sleep; controller firmware updates through fwupd.
  - **Battery and display:** console and controller battery levels, the Long Life charge limit, and an HDR EDID fix.
  - **Other:** a Wi-Fi band policy and a Qt desktop app.
- **Mechanisms:**
  - TDP through the firmware attributes and the platform profile, with ryzenadj above the firmware range;
  - RGB through the LED class `/sys/class/leds/go:rgb:joystick_rings`;
  - vibration, gyro and sleep through `hid-lenovo-go` attributes;
  - the controller battery from a hidraw input report;
  - the Go 2 fan through EC registers via `/dev/port`;
  - the power LED through `/dev/mem`.
- **Privilege:** the root flag. It writes `/var/lib` and `/etc/iwd/main.conf`, downloads ryzenadj, and ships a compiled binary.
- **Coexistence:** it pauses all its modules while LeGoTDP and similar tools are installed. Only one fan controller can run at a time.

### LeGoTDP (Rayekkk)
- **Status:** deleted (404); merged into LegionGo2Companion.
- **What it was:** a Go 2 SPL, SPPT and FPPT plugin, with Go S support from version 1.6.0.

### Firmware rules (all sources agree)
- **Power limits** and the fan curve take effect only in the `custom` profile. Any other profile makes the BIOS override them, and Legion L plus Y changes the profile through a WMI event.
- **The firmware drops the custom fan table** and full fan speed on every mode change, so tools re-apply them.
- **BIOS v29:** a custom fan curve and custom TDP could not be used together; fixed in v29.1. On v28, Custom reset on every mode switch.
- **Fan curves** are not kept across a reboot.
- **Controller IDs:** the controller's PID changes with its firmware (0x618x before 2025, 0x61Ex after) and with its mode.

### Lowest-privilege route for each control (from these tools)

| Control | Lowest-privilege route |
|---|---|
| Platform profile; SPL, SPPT and FPPT | the kernel files (root) or steamos-manager (no root) |
| Go fan | hwmon `fanX_target` (kernel 7.0 and later, root) or acpi_call (ruled out) |
| Go 2 fan | EC registers only (root, risky) |
| Charge limit | `charge_types` `Long_Life` (root), or Steam's or Bazzite's own settings |
| RGB, rumble, IMU, touchpad, controller sleep | `hid-lenovo-go` (kernel 7.1 and later, root), or hidraw with a udev rule |
| Remap, menu swap, gyro routing | Steam Input, or InputPlumber over D-Bus |
| Power LED | WMI or EC only (root) |

### Sources for this section
- https://github.com/aarron-lee/LegionGoRemapper, including the files `LICENSE`, `plugin.json`, `py_modules/legion_configurator.py`, `py_modules/legion_space.py`, `install.sh`, and issues 35, 36, 39, 41 and 42
- https://github.com/InnoVision-Games/legion-center, including its `LICENSE`, `THIRD_PARTY_NOTICES.md`, `py_modules/battery_charge.py`, `py_modules/acpi_enabler/acpi_enabler.py`, and issues 1, 3 and 5
- https://github.com/kazzzzzzzzzzuya/LeGo-decky-toolbox: README, `plugin.json`, and `py_modules/lgo_toolbox/{power,fan,battery,powerled,controller,plumber,acpi_install}.py`
- https://github.com/Rayekkk/LegionGo2Companion: README, `NOTICE`, `CHANGELOG.md`, `plugin.json`, the backends, and issues 1, 5 and 8
- https://github.com/Rayekkk/LeGoTDP (404)
- https://github.com/r0bledas/LegionGoCompanion
- https://github.com/antheas/hwinfo/tree/master/devices/legion_go
- https://kernel.org/doc/Documentation/ABI/testing/sysfs-driver-hid-lenovo-go
- https://kernel.org/doc/Documentation/ABI/testing/sysfs-driver-hid-lenovo-go-s
- https://phoronix.com/news/lenovo-go-s-hid-linux-7.1
- https://lkml.iu.edu/hypermail/linux/kernel/2412.3/02402.html
- https://github.com/OpenGamingCollective/steamos-manager/pull/12
- https://github.com/ValveSoftware/steam-for-linux/issues/12044

## General handheld tools

### SimpleDeckyTDP (aarron-lee)
- **Repository:** https://github.com/aarron-lee/SimpleDeckyTDP
- **Licence and activity:** BSD-3-Clause; pushed 2026-11-20.
- **Devices:** Legion Go (83E1), Go 2 (83N0, 83N1) and Go S (83L3, 83N6), among others.
- **Privilege:** Decky root flag. It falls back to a ryzenadj binary on other devices.
- **Features:**
  - per-game TDP, with separate charger profiles;
  - it re-applies TDP on a power change and after resume;
  - GPU clock range, CPU boost, SMT, governor and energy performance preference;
  - a charge limit, on the ROG Ally only.
- **How it sets Legion TDP:**
  - sets the platform profile `/sys/class/platform-profile/<lenovo-wmi-gamezone>/profile` to `custom`;
  - then writes the `current_value` of `/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes/{ppt_pl1_spl,ppt_pl2_sppt,ppt_pl3_fppt}`.
- **GPU files:** `power_dpm_force_performance_level` and `pp_od_clk_voltage`.
- **CPU files:** `cpufreq/policyN/boost` and `smt/control`.

### PowerControl (mengmeet)
- **Repository:** https://github.com/mengmeet/PowerControl
- **Licence and activity:** BSD-3-Clause; pushed 2026-10-23.
- **Privilege:** Decky root flag, and it bundles `bin/ryzenadj`.
- **Features:** CPU boost, SMT, core count, TDP, GPU clock, and fan curves.
- **Mechanisms:**
  - TDP through the firmware attributes `ppt_pl*` of `lenovo-wmi-other-0`;
  - fans through the hwmon `legion_wmi_fan`: `pwm1_enable` (1 = manual, 2 = automatic) and a 10-point curve `pwm1_auto_point{1..10}_pwm` at 10 to 100 degrees C;
  - PowerStation through `busctl`.

### Handheld Daemon (hhd)
- **Repository:** https://github.com/hhd-dev/hhd
- **Licence:** LGPL-2.1-or-later. Adjustor was GPL-3.0; it is archived and merged into hhd.
- **Privilege:** runs as root.
- **Bazzite:** removed in Bazzite 44 (19 August 2026).
- **Legion features:**
  - controller modes, choice of gyro device, button swaps, touchpad mode and RGB;
  - TDP and performance modes;
  - a 10-point fan curve and full fan speed;
  - the power light;
  - an 80% charge limit and charge bypass.
- **Legacy mechanism:** `acpi_call` to `\_SB.GZFD.WMAA/WMAB/WMAE/WMAF`.
- **Unified mechanism:**
  - the platform profile and the firmware attributes `ppt_pl*`, `fan_full_speed`;
  - hwmon `lenovo_wmi_gamezone_fan` with `pwm{n}_auto_point{p}_pwm` and `_temp`;
  - battery `charge_types` or `charge_behaviour`.
- **TDP limits it uses:**

  | Device | SPL | SPPT | FPPT |
  |---|---|---|---|
  | Go | 30 W | 32 W | 41 W |
  | Go 2 | 35 W | 37 W | 45 W |
  | Go S | 40 W | 43 W | 53 W |

- **Conflict handling:** it treats SimpleDeckyTDP and PowerControl as conflicts, and offers to stop plugin_loader and move those plugins away.
- **APIs:**
  - an HTTP API on port 5335, off by default, with a bearer token;
  - the Unix socket `/run/hhd/api`, chmod 0666 with no token (the code comment says "TODO: Reconsider").
- **udev rules:** hidraw `17ef:618*`, iio, uinput, uhid and backlight. Nothing for TDP.

### InputPlumber (ShadowBlip)
- **Repository:** https://github.com/ShadowBlip/InputPlumber
- **Licence and activity:** GPL-3.0; v0.79.
- **Devices:** Legion Go, Go 2 and Go S configurations.
- **D-Bus:** system bus `org.shadowblip.InputPlumber`. The policy lets anyone send to it.
- **Interfaces:**
  - `org.shadowblip.InputManager`;
  - `org.shadowblip.Input.CompositeDevice`: `LoadProfilePath`, `LoadProfileFromYaml`, `GetProfileYaml`, `TargetDevices`, `ProfileName`, `InterceptMode`.
- **Use:** remapping profiles. Gyro and RGB were broken on the Go 1 and Go S at the launch of Bazzite 44.

### PowerStation (ShadowBlip)
- **Repository:** https://github.com/ShadowBlip/PowerStation
- **Licence:** GPL-3.0.
- **Privilege:** root daemon. The policy lets anyone send to it.
- **D-Bus:**
  - `org.shadowblip.CPU`: `BoostEnabled`, `SmtEnabled`, `CoresEnabled`;
  - `org.shadowblip.GPU.Card`: `ManualClock` and the minimum and maximum clock;
  - `org.shadowblip.GPU.Card.TDP`: `TDP`, `Boost`, `PowerProfile`, `ThermalThrottleLimitC`.
- **Bazzite:** used only where steamos-manager cannot support a device.

### steamos-manager (Valve)
- **Repository:** https://gitlab.steamos.cloud/holo/steamos-manager
- **Licence and activity:** MIT; commit 2026-11-10.
- **Daemons:**
  - the user daemon is on the session bus: `com.steampowered.SteamOSManager1` at `/com/steampowered/SteamOSManager1`;
  - the root daemon is private.
- **Permission:** the bus policy lets anyone send. No polkit check was found.
- **Legion configuration** (`data/devices/legion-go-series.toml`):
  - 83E1 is `legion_go`; 83N0 and 83N1 are `legion_go_2`;
  - TDP: `tdp_limit` through the firmware attribute `lenovo-wmi-other-0`, with performance profile `custom`;
  - performance profile: platform profile `lenovo-wmi-gamezone`;
  - GPU: amdgpu;
  - there is no `battery_charge_limit` and no fan section for Legion.
- **Interfaces:**

  | Interface | What it offers |
  |---|---|
  | `TdpLimit1` | `TdpLimit` u (read and write), `TdpLimitMin`, `TdpLimitMax` |
  | `PerformanceProfile1` | `AvailablePerformanceProfiles`, `PerformanceProfile`, `SuggestedDefaultPerformanceProfile` |
  | `GpuPerformanceLevel1` | `ManualGpuClock` and its minimum and maximum |
  | `GpuPowerProfile1` | the GPU power profile |
  | `CpuBoost1` | `CpuBoostState` u |
  | `CpuScaling1` | the governor |
  | `CpuScheduler1` | the scheduler |
  | `BatteryChargeLimit1` | `MaxChargeLevel` i (-1 resets), `SuggestedMinimumLimit` |
  | `FanControl1` | `FanControlState`: 0 is the BIOS, 1 is the OS; no curves |
  | `WifiPowerManagement1` | Wi-Fi power saving |
  | `Manager2` | `DeviceModel` |

- **Not offered:** SMT, display settings, separate SPL, SPPT and FPPT values, and fan curves.
- **Shared with Steam:** Steam's quick access menu slider writes through the same daemon.

### Bazzite 44 (19 August 2026)
- **What it ships:** InputPlumber, steamos-manager, PowerStation and OpenGamepadUI. hhd is gone.
- **Controls:** TDP is set only in Steam's quick access menu. The charge limit is in the desktop power settings only.
- **Legion Go page:** the Go 1 gyro was broken at launch, and OpenGamepadUI has no TDP or CPU control on the Go 2.

### What this means for Keepsake
- **No root and no binary are needed** to reach steamos-manager through Keepsake's own pure-Python D-Bus client (`desktop/dbus.py`). That gives TDP, performance profile, CPU boost, GPU clock, charge limit (where configured) and Wi-Fi power saving.
- **These need root:** direct writes to sysfs (`firmware-attributes`, `platform-profile`, `pp_od_clk_voltage`, `smt/control`, the hwmon fan curves) and `acpi_call`.

## Kernel interfaces, firmware rules and Legion Space parity

### Which kernel has what (from the mainline source at each release tag)

| Feature | First kernel |
|---|---|
| lenovo-wmi-gamezone, -other, -capdata01, -events and -helpers drivers | v6.17 |
| firmware attributes `ppt_pl1_spl`, `ppt_pl2_sppt`, `ppt_pl3_fppt` | v6.17 |
| the Legion Go 2 (8ASP2, 8AHP2) in the no-extreme quirk | v6.19 |
| hwmon fan RPM (`lenovo_wmi_other`): `fanX_input`, and `fanX_target` (0644 root; 0 means automatic) | v7.0 |
| the `hid-lenovo-go` controller driver | v7.1 |
| 22 firmware attributes, and the battery `charge_types` and `charge_behaviour` | v7.2 |

There is no kernel fan-curve interface up to v7.3.

**Distribution kernels:**

| System | Kernel | Lenovo WMI drivers |
|---|---|---|
| SteamOS 3.8 | 6.16 | probably a Valve backport (unverified) |
| Bazzite 43 | 6.17.7 | yes |
| Bazzite 44 | OGC 7.2.x | everything up to v7.2, plus hid-lenovo-go |

### Platform profile
- **Where it lives:** `/sys/class/platform-profile/platform-profile-N/{name,choices,profile}`, where `name` is `lenovo-wmi-gamezone`. The older single file is `/sys/firmware/acpi/platform_profile`.
- **Choices:** `low-power`, `balanced`, `performance`, `custom`. Extreme mode is quirked away on both Gos.
- **LED colours:** quiet blue, balanced white, performance red, custom purple.
- **Legion L plus Y** changes the mode through a WMI event, so the mode can change underneath Keepsake.
- **Any mode other than custom** makes the BIOS override the power limits.
- **Writing needs root.**

### Power limits
- **Where they live:** `/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes/<attr>/`.
  - `current_value` is 0644 root.
  - `min_value`, `max_value`, `scalar_increment` and `default_value` are 0444.
- **Write rules:** `-EBUSY` unless the mode is custom; `-EINVAL` outside the range.
- **steamos-manager** writes one value to SPL, SPPT and FPPT, and suggests the custom profile.
- **Ranges** (from hhd; not yet checked against the BIOS's min and max values):

  | Device | SPL | SPPT | FPPT |
  |---|---|---|---|
  | Go | 30 W | 32 W | 41 W |
  | Go 2 | 35 W | 37 W | 45 W |

### Battery
- **Kernel v7.2 and later:** `charge_types` is `Standard` or `Long_Life`, where Long_Life is a fixed 80% limit. There is no `charge_control_end_threshold`. Writing needs root.
- **SteamOS 3.8** has preliminary Legion charge limiting in Steam's settings.

### Controllers (hid-lenovo-go)
- **USB IDs it binds:** 17ef:61eb, 61ec, 61ed and 61ee. Go 1 controllers report these only after Lenovo's 2025 controller firmware.
- **RGB:** `/sys/class/leds/go:rgb:joystick_rings/`, with `effect`, `mode`, `profile`, `speed`, `enabled` and `multi_intensity`.
- **HID attributes:** `mode`, `os_mode`, `rumble_intensity`, `fps_mode_dpi`; per handle `imu_enabled`, `auto_sleep_time` and calibration; the touchpad's `enabled` and vibration settings.
- **All of these are 0644 root.**

### Firmware rules
- **Custom mode** is needed for power limits and fan curves.
- **From BIOS v28,** Custom resets to 30 W, with everything at maximum, on every mode switch. Apply the limits again after any mode change.
- **On BIOS v29,** a custom fan curve and a custom TDP could not be used together. This is fixed in v29.1 and later.
- **BIOS milestones:**
  - v28 or later is needed for fan curves.
  - v29 added the 80% charge limit (22 December 2024).
  - N3CN42WW bricked units; Lenovo rolled support back to N3CN40WW.
  - v35 or later has a newer power-LED method.
- **Fan minimum:** hhd's own floor is 44, 48, 55, 60, 71, 79, 87, 87, 100 and 100 percent across its 10 points. Lenovo publishes no minimum.

### acpi_call and raw WMI
- **Methods:** `\_SB.GZFD.WMAA/WMAB/WMAE/WMAF` set the mode, features, fan table and power LED.
- **acpi_call** is an out-of-tree GPL module. `/proc/acpi/call` is 0660 root, and SteamOS does not ship it.
- **Not viable** under P8, P9 and the GPL rule.

### Display
- **Refresh rates:** gamescope gives the Go 60 and 144 Hz, and the Go 2 OLED 48 to 144 Hz in 1 Hz steps, with HDR.
- **Refresh and VRR without root:** frontend `SteamClient.System.Perf.UpdateSettings` with the per-app fields `display_refresh_manual_hz`, `is_vrr_enabled` and `tdp_limit`. The types are verified in `@decky/ui`; the encoding is not. This is a Steam write under P15.
- **Brightness:** `SteamClient.System.Display.SetBrightness`. The sysfs backlight is root-only.

### Legion Space parity
- **Thermal modes:**
  - Go: Quiet, Balance and Performance at 8, 15 and 20 W, and Custom from 5 to 30 W.
  - Go 2: 8, 16 and 20 W on battery (32 W on the charger), and Custom with three sliders at 35, 37 and 45 W.
- **Fans:** full speed fan, and a custom fan curve (Legion Space 1.0.2.6 and later, BIOS v29 or later).
- **Battery:** the 80% charge limit, and charging speed under high load (BIOS only).
- **Lights:** RGB rings (effect, colour, speed and profiles), and the power LED off.
- **Controllers:** vibration, dead zones, trigger dead zones, response curve, gyro, sleep, key mapping, and xinput or dinput.
- **Touchpad:** on, off and haptics. Also the FPS mode's DPI.
- **Display:** 60 or 144 Hz, adaptive brightness, the FPS limiter.
- **Other:** VRAM, and driver and BIOS updates.

### Sources
The agent's report lists them: docs.kernel.org (lenovo-wmi-gamezone, lenovo-wmi-other, platform_profile), torvalds/linux at each tag, lore and patchew patches, steamos-manager, gamescope display scripts, Bazzite news, legion-go-tricks, LegionGoRemapper, hhd, the acpi_call repository, Lenovo user guides, PSREF and forum posts, Notebookcheck, Engadget, Tom's Hardware.

## Sources

**General tools**

- SimpleDeckyTDP: https://github.com/aarron-lee/SimpleDeckyTDP
- PowerControl: https://github.com/mengmeet/PowerControl
- Handheld Daemon: https://github.com/hhd-dev/hhd, and its HTTP API docs at https://github.com/hhd-dev/hhd/blob/master/docs/http.md
- Adjustor (archived): https://github.com/hhd-dev/adjustor
- hhd Decky plugin (archived): https://github.com/hhd-dev/hhd-decky
- hhd's steamos-manager fork: https://github.com/hhd-dev/steamos-manager-hhd
- InputPlumber: https://github.com/ShadowBlip/InputPlumber, and https://www.phoronix.com/news/InputPlumber-0.79
- PowerStation: https://github.com/ShadowBlip/PowerStation
- steamos-manager:
  - https://gitlab.steamos.cloud/holo/steamos-manager
  - a mirror: https://github.com/matte-schwartz/steamos-manager
  - https://www.gamingonlinux.com/2025/05/steamos-manager-for-bios-updates-tdp-and-gpu-clock-controls-now-open-source
- Bazzite:
  - https://universal-blue.discourse.group/t/a-brighter-future-for-bazzite/11575
  - https://universal-blue.discourse.group/t/bazzites-biggest-update-deck-44-has-launched-happy-birthday-to-universal-blue/12373
  - https://docs.bazzite.gg/Handheld_and_HTPC_edition/Handheld_Wiki/Lenovo_Legion_Go/
  - https://www.gamingonlinux.com/2026/09/bazzites-september-13-update-adds-strix-halo-tdp-controls-restores-desktop-tdp-controls-and-brings-fixes/

**Kernel**

- Driver docs:
  - https://docs.kernel.org/wmi/devices/lenovo-wmi-gamezone.html
  - https://docs.kernel.org/wmi/devices/lenovo-wmi-other.html
  - https://docs.kernel.org/userspace-api/sysfs-platform_profile.html
- Driver source: https://github.com/torvalds/linux/tree/v6.17/drivers/platform/x86/lenovo, and the same folder at v6.18, v6.19 and v7.0 to v7.3
- Controller driver:
  - https://github.com/torvalds/linux/blob/v7.3/drivers/hid/hid-lenovo-go.c
  - https://github.com/torvalds/linux/blob/v7.3/Documentation/ABI/testing/sysfs-driver-hid-lenovo-go
- Patches:
  - https://lwn.net/Articles/1003992 (the Lenovo WMI driver series)
  - https://lkml.iu.edu/2605.2/07283.html
  - https://lkml.indiana.edu/hypermail/linux/kernel/2507.3/07953.html
  - https://lkml.iu.edu/2511.3/06159.html
- acpi_call: https://github.com/nix-community/acpi_call

**Display**

- gamescope display scripts: https://github.com/ValveSoftware/gamescope/tree/master/scripts/00-gamescope/displays
- `@decky/ui` 4.16.5 type definitions in this repository's `node_modules`: `globals/steam-client/system/Perf.d.ts` and `Display.d.ts`

**Firmware and community**

- https://github.com/aarron-lee/legion-go-tricks
- https://github.com/aarron-lee/LegionGoRemapper
- https://universal-blue.discourse.group/t/why-is-my-custom-fan-curve-not-working/3265

**Lenovo and press**

- Legion Go user guide: https://download.lenovo.com/pccbbs/pubs/legion_go_8apu1/user_guide/en/index.html
- Legion Go 2 user guide: https://download.lenovo.com/pccbbs/pubs/legion_go_8/user_guide/en/index.html
- Legion Go 2 specification (PSREF): https://psref.lenovo.com/syspool/Sys/PDF/Legion/Legion_Go_8ASP2/Legion_Go_8ASP2_Spec.pdf
- Lenovo community posts:
  - https://gaming.lenovo.com/legion-go/post/legion-go-update-12-22-2024-d7dl5EI7FLQ5fV5
  - https://gaming.lenovo.com/legion-go/post/legion-space-v1-0-2-6-beta-testing---end-of-january-MB4UTUq5xZbTwPQ
- Press:
  - https://www.notebookcheck.net/Lenovo-finally-acknowledges-Legion-Go-BIOS-bricking-issues-and-confirms-affected-devices-should-be-repaired-free-of-charge.1377253.0.html
  - https://www.engadget.com/gaming/pc/lenovo-legion-go-2-review-the-utility-pc-gaming-handheld-120000533.html
  - https://www.tomshardware.com/video-games/handheld-gaming/lenovo-legion-go-2-review
  - https://www.gamingonlinux.com/2026/03/steamos-3-8-0-preview-brings-initial-steam-machine-support-and-improvements-for-many-handhelds
