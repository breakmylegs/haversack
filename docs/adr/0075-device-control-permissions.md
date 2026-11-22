# ADR-0075: How Keepsake changes device settings without root, and what to do about the controls that need it

- Status: **Tier 0 accepted** (decided under ADR-0037). **Tier 1 accepted, option B**: Peter approved it on 22 November 2026 as recommended, a separate signed, version-locked helper with an authenticated minimal interface and an allow-list. The helper is ADR-0083.
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

R21 makes Keepsake the main Legion Go and Legion Go 2 app, covering power, fans, battery, controllers, RGB and display. The research is `docs/research/legion-control.md`. Its findings that matter here:

- **Every kernel control is root-write only:**
  - the platform profile and the power-limit firmware attributes;
  - the hwmon fan target;
  - the battery's `charge_types`;
  - the `hid-lenovo-go` controller and RGB attributes;
  - the backlight.

  No shipped udev rule loosens them.
- **steamos-manager exposes many of them without root.** Its user daemon on the session bus (`com.steampowered.SteamOSManager1`) has `TdpLimit1`, `PerformanceProfile1`, `CpuBoost1`, `GpuPerformanceLevel1`, `BatteryChargeLimit1`, `WifiPowerManagement1` and others. Its root daemon writes the files. Valve's device file supports both Legion models, and Bazzite 44 ships it.
- **InputPlumber's D-Bus policy lets any user send to it** (remap profiles). It runs on Bazzite 44, and on SteamOS it is unverified.
- **Steam's frontend settings cover the display:** refresh rate, VRR, TDP and brightness (`SteamClient.System.Perf`, `SteamClient.System.Display`). These are Steam writes under principle 15.
- **What only root can do:** fan curves and fan speed, separate SPL, SPPT and FPPT, RGB, the controller's hardware settings (gyro, sleep, touchpad, vibration) and the power LED.
- **Keepsake's own constraints:**
  - it runs as the user (P8);
  - it bundles no binary (P9);
  - every feature works from Gaming Mode with no terminal (P7);
  - the root flag is an escalation item.

## Decision

### Tier 0: no root (accepted, ships stage by stage)

1. **Reading:** world-readable sysfs only (`keepsake/hardware.py`, ADR-0074).
2. **Writing goes through these routes, in this order:**
   1. **steamos-manager on the session bus, through Keepsake's own pure-Python D-Bus client** (`keepsake/desktop/dbus.py`, already used by the tray). This needs no binary, no new library and no polkit.
      - It covers TDP limit, performance profile, CPU boost, GPU clock and charge limit, where the device's steamos-manager offers them. A property that is missing means the feature is unsupported, and Keepsake shows it as unavailable.
   2. **InputPlumber on the system bus** for controller remapping, where it runs. Unverified; it is checked in its stage.
   3. **Steam's frontend calls** for refresh rate, VRR and brightness. These are principle 15 writes, with their own decision in the display stage.
3. **Safety, for every write:**
   - each value is clamped to both the device profile's limits (`devices.py`) and the range steamos-manager reports;
   - every write is read back, and a mismatch is reported;
   - what Keepsake changed is put back when the feature is switched off or the plugin unloads;
   - after resume, the game's profile is applied again (the firmware resets Custom on a mode change);
   - Keepsake never leaves the fans in a mode it cannot monitor.
4. **Coexistence: never fight another tool over a setting.**
   - **Detection:**
     - running services: hhd and PowerStation;
     - Decky plugins: SimpleDeckyTDP, PowerControl, LeGoTDP, Legion Go Companion and LegionGoRemapper;
     - Steam's own per-game TDP setting.
   - **When another tool manages a setting,** Keepsake shows it read-only, names the tool, and says how to hand it over: for example, turn off that tool's per-game profiles.
   - **Keepsake never disables, moves or edits another tool.**
5. **No cloud and no peer messages carry device settings.** Profiles stay on the device that made them, until a later stage decides otherwise.

### Tier 1: controls that need root (accepted 22 November 2026, option B, ADR-0083)

These need root, and Peter must approve one of these options first:
- fan curves and fan speed (kernel v7.0 and later have a fan target; no kernel curve interface exists yet);
- separate SPL, SPPT and FPPT;
- the RGB rings;
- the controller's hardware settings: gyro, auto-sleep, touchpad, vibration, mode;
- the power LED.

| Option | What it is | For | Against |
|---|---|---|---|
| A. Decky root flag on Keepsake | The whole backend runs as root | One plugin, simple | Everything would run as root: the network code, the cloud tokens, the Replication listener and the Installer. Far too much power for a few attributes. **Rejected.** |
| **B. A separate helper plugin with the root flag (recommended)** | "Keepsake Device Helper": a second, tiny Decky plugin (a few hundred lines, Python stdlib only, no network). It accepts requests from Keepsake on a Unix socket in the runtime folder. It checks the caller's user ID (`SO_PEERCRED`) and a per-boot token. It writes only to an allowlist of exact sysfs attributes (by kernel driver name, never by path from the request), with each value validated and clamped against the device profile. Installed through Decky's own installer from Keepsake's releases (ADR-0002), signed like Keepsake (ADR-0036). | Keepsake itself stays non-root. The root code is small enough to read in one sitting, with no network and no shell. It can be uninstalled on its own, and every feature without root works without it. | A second plugin to install and update. Its code runs as root, so a bug in its checks is a root bug. It needs its own tests, threat model entries and device checks. |
| C. A udev rule giving the user's group write access to those attributes | One rules file grants group write to the exact attributes | No root code at run time | Installing it needs root once (a terminal or a helper, against principle 7). SteamOS updates may reset `/etc`. It lets any program run by the user write those attributes. |
| D. polkit with pkexec | A policy file plus a helper | Standard Linux | `pkexec` and policy files need `/usr`, which is read-only on SteamOS and Bazzite. **Not viable.** |
| E. Wait for steamos-manager or InputPlumber | Use their interfaces when they appear | No root at all | No timeline. Steam already offers what steamos-manager exposes, so the controls Peter most wants beyond Steam (fan curves, RGB) would not arrive. |

**Recommendation: option B.** It keeps principle 8 for Keepsake itself and puts the root code in one small, auditable place. Every root write stays inside an allowlist with the same clamps, read-back and restore rules as tier 0. Until Peter approves, Keepsake shows tier 1 controls as "needs the Device Helper, not available yet", and ships no root code.

If approved, the helper gets its own ADR covering:
- its allowlist;
- its socket protocol;
- its install and update flow;
- its uninstall;
- its device checks;
- a threat-model section.

## Consequences

- Stages 2 (TDP and per-game profiles) and 4 (battery) build on tier 0 now. Fans (stage 3), RGB and controller hardware settings (stage 5) wait for the tier 1 decision, apart from what steamos-manager, InputPlumber or Steam expose without root.
- Threat model: T141 (tier 0 writes through steamos-manager) is added with stage 2. Tier 1 entries come with the helper's ADR, if approved.
- Principle 8 holds for Keepsake in every option except A, which is rejected.
