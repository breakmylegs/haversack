# R21 stage 2 report: performance profiles (v0.34.0)

The second stage of Peter's Legion Go controls (item 3 of 21 November 2026), plus the research and the permission model that come before any control that writes. Decisions: ADR-0075 (permissions) and ADR-0076 (profiles).

## What changed

- **Research:** `docs/research/legion-control.md`, from three research passes. It covers:
  - every existing Legion tool: LegionGoRemapper, Legion Center, LeGo-decky-toolbox, LegionGo2Companion and LeGoTDP;
  - the general tools: SimpleDeckyTDP, PowerControl, Handheld Daemon, InputPlumber, PowerStation and steamos-manager;
  - Bazzite;
  - the kernel's Lenovo drivers, release by release;
  - the firmware rules;
  - Legion Space parity.

  It lists sources throughout and copies no code.
- **The permission model:** ADR-0075.
  - **Tier 0 (accepted):** no root. Writes go only through steamos-manager on the session bus, through Keepsake's own D-Bus client, with InputPlumber and Steam's frontend calls to follow in their stages.
  - **Tier 1 (proposed, waiting for Peter):** fan curves, separate SPL, SPPT and FPPT, RGB, controller hardware settings and the power LED. The recommendation is a separate, tiny helper plugin with the Decky root flag and an allowlist of attributes. The Decky root flag on Keepsake itself is rejected.
- **The new Device module** (`keepsake/device/`):
  - `steamos.py` reads and sets the mode, TDP and CPU boost through steamos-manager, and reads every value back.
  - `performance.py` keeps per-game profiles and handles the lifecycle:
    - apply when the game starts, in the background;
    - restore when it exits, only values that still hold Keepsake's, with the mode last;
    - apply again after resume, and restore when the module is switched off.

    It also detects other tools and stays read-only while any is present. It watches for Steam or another app changing a value, and stops applying if one does.
- **Where the controls are:**
  - Device, Power: mode, TDP and boost, and this game's profile.
  - The quick access menu's Now playing section: mode and TDP.
  - The desktop app's Power page.
- **The Device check "Performance control":** what steamos-manager offers, plus a write that changes nothing, read back.

## Not done, and why

- **Tier 1 controls** wait for Peter's approval of ADR-0075: fan curves, separate SPL, SPPT and FPPT, RGB, the controller's hardware settings and the power LED.
- **SMT, cores and the GPU clock range:** steamos-manager does not offer them.
- **Auto TDP:** it needs frame-rate feedback. It follows once these profiles are proven on the devices.
- **On-device behaviour is unverified:**
  - whether the plugin reaches the session bus (A221);
  - how TDP behaves on these devices (A222).

  Steps 23 and 24 of the device run check both.

## Tests

- **New: `tests/test_device_performance.py`, 28 tests.**
  - **steamos-manager:**
    - reading what the device offers;
    - a missing steamos-manager or bus;
    - read-back on every set.
  - **Profiles:**
    - bad profiles are refused;
    - profiles are kept per game.
  - **Applying:**
    - a TDP switches to Custom first, clamped by the device profile;
    - a game's profile is applied, and the old values come back in order;
    - a game without a profile changes nothing;
    - a change by someone else is never undone, noticed or not;
    - several changes still put back the first value;
    - another tool means read-only;
    - resume applies the profile again;
    - a mode the device lacks is refused.
  - **Other tools** are found.
  - **The Device check** works in five states.
  - **The app** applies and keeps a profile for the running game, and applies it again after sleep.
- **Regression:** these named tests pass, with 2 skipped on Windows:
  - `tests/test_devicechecks.py`
  - `tests/test_hardware.py`
  - `tests/test_layout_v3.py`
  - `tests/test_modules.py`
  - `tests/test_desktop.py`
  - `tests/test_installer.py`
- **Mutation tests:** 12 mutations. 3 survived and led to three new tests: an unnoticed change, several changes in one game, and resume through the app. Now all 12 are caught.

## Threat model and assumptions

- **Threat model:** T141.
- **Assumptions:** A221 (session bus reachable, unverified) and A222 (TDP behaviour, verified from the source).

## On-device checklist

`docs/device-run.md` part 4, steps 23 and 24.
