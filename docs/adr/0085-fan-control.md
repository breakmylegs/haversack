# ADR-0085: Fan control through the Keepsake Helper

- Status: accepted (R24, Peter's request of 22 November 2026; ADR-0075 tier 1, ADR-0083; decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

**What Peter asked for.** Fan control with every feature of Legion-Go-1-Fan-Control (everancii) and LeGo2-Fan-Control (Rodpad), and the best of five other Legion plugins. That covers:
- live temperature and RPM;
- a curve, stepped or smooth;
- per-mode, named and per-game profiles;
- smoothing and hysteresis;
- the Go 2 absolute override;
- the Go 1's full fan speed and BIOS fan table;
- a test;
- limits with an off-by-default unlock;
- a failsafe at 101 °C;
- hand-back to the firmware;
- re-applying after resume and reboot;
- a performance budget;
- firmware checks, including the Go 2 validated list;
- acpi_call detection;
- coexistence;
- a Device check.

**The research.** `docs/research/fan-control.md` read all seven plugins and the kernel, and found:
- **Go 2.** The fan is set through an RPM override in the embedded controller (EC 0xC6C8/9; 0 hands the fan back to the firmware), reached through `/dev/port`. Only LegionGo2Companion checks firmware: BIOS RRCN16WW with EC 1.16 is validated, and other pairs get a self-test.
- **Go 1.** The custom fan table needs `acpi_call`, an out-of-tree GPL kernel module. SteamOS does not ship it; tools that use it build and install it into the system. Full fan speed is also a firmware attribute (`fan_full_speed`, kernel 7.2).
- **Every one of these plugins runs as root.** Keepsake runs only the helper as root.
- **Licences.** Rodpad and everancii are GPL-3.0, so only their feature lists are used. Facts are not copyrightable, and Keepsake's code is its own.

## Decision

1. **Go 2: software curve control through the helper.** These are new helper jobs (`keepsake_helper/fan.py`):
   - **Exact DMI identity.** The 83N0 "Legion Go 8ASP2" with board LNVNB161216, or the 83N1 "8AHP2" with BIOS RQCN as a beta.
   - **The EC protocol.** Index ports 0x4E and 0x4F, three selector rounds, and every selector write read back. Port access is under `flock`.
   - **Allow-lists.** Reads only from an allow-list of EC addresses; writes only to the override.
   - **Firmware gate.** A speed is set only on the validated pair (RRCN16WW, EC 1.16), or on a pair that passed the self-test on this device:
     - the self-test asks for 3000 RPM (4800 if already fast), needs the measured speed within 15 % twice in 15 s, and hands back;
     - the pairs that pass are kept in the helper's own settings.
   - **The override is read back.**
   - **The lease.** Every speed carries a lease of at most 60 s. When it runs out, the helper hands the fan back to the firmware.
   - **The failsafe.** At 101 °C or above, the helper sets 4800 RPM itself, and never accepts a lower speed while it stays hot.
   - **Other fan control.** The helper refuses when another fan driver (`legion_laptop`, `gpd_fan`) is loaded, or when anything else claims the EC ports.
   - **Start, unload and uninstall.** The helper hands back on start (left over from a crash), on unload and on uninstall.

2. **Go 1: full fan speed only,** through the firmware attribute `fan_full_speed` (kernel 7.2 and later), under the same lease.
   - **No custom fan table.** It needs `acpi_call`, and building or installing a kernel module breaks P9 and writes outside the allowlist.
   - **Detection only.** Keepsake detects `/proc/acpi/call` and reports it in the Device check and on the page, but does not use it, even when another tool has installed it.
   - **Curves later.** They arrive when the kernel's announced fan-curve interface lands.

3. **Keepsake chooses the speed** (`keepsake/device/fancurve.py`, `fans.py`):
   - **Curves.** 2 to 8 points, each 1500 to 4800 RPM, rising, with at least 2000 RPM at the hottest point. The unlock (two steps, off by default) allows up to 5200 RPM; it never lifts the floor or the failsafe. Relocking brings curves back inside the limits.
   - **Stepped or smooth** interpolation.
   - **The controller.**
     - It rises at once.
     - It falls only after a 2 °C drop held for 5 s, then by at most 300 RPM every 2 s.
     - It always goes to full speed at the failsafe.
   - **Profiles.** Named profiles (Balanced, Quiet and Cool to start), a default, one per performance mode, and one per game. A game's choice wins, then the mode's.
   - **The loop.** Every 2 s:
     - read the world-readable temperature (the hotter of k10temp and amdgpu);
     - send a speed only when it changes, otherwise renew a 10 s lease;
     - after sleep (the wall clock jumps against the monotonic clock), send the speed again;
     - on a reboot the loop starts with the plugin.
   - **The performance budget.** A tick is microseconds of work, and a test holds 10,000 controller updates under 0.5 s.
   - **Never fight.** If another fan tool is installed or running, Keepsake shows the readings only:
     - LeGo2 Fan Control, Legion Go 1 Fan Control, LegionGoRemapper, Legion Center, Legion Decky, Legion Go Toolbox, LegionGo2Companion, PowerControl;
     - Handheld Daemon.

4. **Screens.** Device, Fans, in Gaming Mode and the desktop app:
   - **The readings** refresh in place without remounting anything.
   - **Controls:** the on switch, the smooth switch, a curve editor (sliders in Gaming Mode; a draggable SVG and a table in the desktop app), save, default, use in this mode, use for this game, the unlock, the fan test, and Hand back.
   - **Go 1:** the full speed switch.

5. **The Device check "Fan control"** records:
   - the model, firmware and validation;
   - the readings;
   - whether `acpi_call` and the full-speed attribute are present;
   - any other fan control.

6. **Write allowlist (helper).**
   - EC 0xC6C8/9 through `/dev/port`, Go 2 only.
   - `fan_full_speed`'s `current_value`, Go 1 only.
   - The helper's own settings, for the self-test results.

## Consequences

- **Principles.** P8 holds for Keepsake. P9 holds: no `acpi_call`, no binary.
- **The Go 1 gets less than the Go 1 plugins offer.** It has full speed and readings, but no custom table until the kernel provides one. The page says why.
- **Threat model:** T155 to T157. **Assumptions:** A236 to A238. **Device run:** steps 42 to 44.
