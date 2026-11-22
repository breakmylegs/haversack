# Fan control on the Legion Go and Legion Go 2: interfaces, safety rules and licences

Research of 22 November 2026 for R24 (ADR-0085). Facts and interfaces only: no code from these projects is used. Commits read: everancii `958f069`, Rodpad `de1a45e`, aarron-lee `6ea2044`, U53R3RR0R `10c3cc7`, onullusoy `8457e43`, kazzzzzzzzzzuya `4f830d9`, Rayekkk `8aec7ee`.

## Licences

| Repository | Licence | Use in Keepsake |
|---|---|---|
| everancii / Legion-Go-1-Fan-Control | GPL-3.0 | Facts only (feature list) |
| Rodpad / LeGo2-Fan-Control | GPL-3.0 | Facts only (feature list) |
| aarron-lee / LegionGoRemapper | BSD-3-Clause | Facts |
| U53R3RR0R / legion-center | BSD-3-Clause | Facts |
| onullusoy / legion-decky | BSD-3-Clause (bundled acpi_call is GPL-3.0) | Facts |
| kazzzzzzzzzzuya / LeGo-decky-toolbox | MIT (vendors acpi_call source) | Facts |
| Rayekkk / LegionGo2Companion | BSD-3-Clause | Facts (register map, safety design) |

All of them run their whole plugin as root. Keepsake runs only the helper as root (ADR-0083).

## Interfaces

| | Go 1 (83E1) | Go 2 (83N0, 83N1) |
|---|---|---|
| Temperature | hwmon `k10temp` / `amdgpu` `temp1_input`, world-readable | the same; use the higher of the two |
| Fan RPM | EC 0xC664/5 (16-bit LE) via the `/dev/port` index protocol (root); or hwmon `fan1_input` from `lenovo-wmi-other` (kernel 7.0 and later) where exposed | EC 0xC6C0/1 via `/dev/port` (root) |
| Curve | Firmware 10-point table (percent, 10 to 100 °C) through `\_SB.GZFD.WMAB` method 0x06, only with `acpi_call`, only in Custom mode | No firmware curve used: a software loop writes an RPM override |
| Override | hwmon `fan1_target` (kernel 7.0 and later, root; 0 = automatic) where exposed; hhd notes setting may not work on the Go 1 | EC 0xC6C8/9, 16-bit LE RPM: 0 = firmware automatic, 256 = stop, 1500 to 4800 otherwise (5200 plateaus near 4800) |
| Full fan speed | firmware attribute `fan_full_speed` (kernel 7.2, root) or WMAE feature 0x04020000 via `acpi_call` | override 4800 RPM |
| Hand-back | full speed off; Performance then Custom reloads the stock table (WMAA) | write 0 to 0xC6C8/9 and read back 0 |
| Power mode | platform profile; EC 0xC683 on the Go 2 (176 Performance, 177 Balanced, 178 Quiet, 179 Custom) | |
| Firmware | BIOS v28 or later for curves; v29 could not combine curve and custom TDP (fixed in v29.1); N3CN42WW bricked units | validated: 83N0 "Legion Go 8ASP2", board LNVNB161216, BIOS RRCN16WW, EC 1.16 (EC version at 0xC300/0xC301); other pairs need a self-test |

**The `/dev/port` EC protocol (Go 2 and Go 1 reads):** index port 0x4E, data port 0x4F. For each access, three selector rounds: write 0x2E to 0x4E and the selector to 0x4F, then 0x2F to 0x4E and a byte to 0x4F. Selector 0x11 takes the high address byte, 0x10 the low byte, and 0x12 then reads or writes the data byte at 0x4F. LegionGo2Companion reads back every selector write, restores the selectors and holds `flock` on `/dev/port`.

**acpi_call:** an out-of-tree GPL kernel module. SteamOS does not ship it. Bazzite is disputed (one README says yes; two Bazzite tools build it themselves; ublue-os akmods has no entry). Tools that install it build it with DKMS or in containers and write to the system partition or `/etc`.

**Kernel fan curve:** none in mainline up to 7.3. A patch on the 10-point WMI curve was announced on 15 January 2026.

## Safety rules the projects agree on

- A curve never falls as temperature rises.
- **Go 1 floors** (percent across the 10 points): 44, 48, 55, 60, 71, 79, 87, 87, 100, 100, with a maximum of 115 %.
- **Go 2 limits:** a positive minimum of 1500 RPM and a ceiling of 4800 RPM, with at least 2000 RPM at the 100 °C point.
- **Failsafe:** full speed at 100 °C (Companion) or at 101 °C (Rodpad).
- **Smoothing:**
  - Rodpad ignores changes under 5 °C and re-evaluates every 6 s.
  - Companion rises at up to +2000 RPM per 0.25 s, and falls only after a 2 °C drop and a 5 s dwell, by at most 300 RPM every 2 s.
- **Releasing control.** Release to firmware automatic on any fault, unload or sleep. The Go 2 override is re-armed after resume; Rodpad also re-writes it every 30 s.
- **Firmware resets.** The Go 1 firmware drops a custom table and full speed on any mode change and after sleep; re-check every 5 s, or re-apply 3 s after resume.
- **Other fan tools.** Refuse if the `legion_laptop` or `gpd_fan` modules are loaded, if anything claims I/O ports 0x4E to 0x4F, or if another process holds `/dev/port`. hhd's "Enforce Windows minimums" fights user curves.
- **Watchdog.** Companion runs a separate guardian process with a 3 s lease that releases control if the main process stops.
