# ADR-0079: Wi-Fi power saving, the BIOS check, and leaving the display to Steam

- Status: accepted (Peter's request of 21 November 2026, item 3, stage 6, decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

Stage 6 of the Legion Go controls covers the display and other useful features. Peter asked for:

- the refresh rate, with a smooth mode matching it to the frame cap;
- brightness;
- the HDR and colour fixes;
- Wi-Fi power-saving tweaks;
- a BIOS version check with warnings.

The research (`docs/research/legion-control.md`) found:

- **Steam already owns refresh rate, frame limit, VRR and brightness** in Gaming Mode, per game, through its own performance settings. Keepsake could reach them only through Steam's frontend calls, which are principle 15 writes, and it would compete with Steam's own controls.
- **steamos-manager offers Wi-Fi power saving without root**, through `WifiPowerManagement1`.
- **The Legion Go's BIOS has known problems:**
  - N3CN42WW bricked units, and Lenovo withdrew it;
  - before v28 there are no custom fan curves;
  - before v29 there is no 80 percent charge limit;
  - on v29, a custom fan curve and custom TDP could not be used together (fixed in v29.1).

## Decision

1. **Wi-Fi power saving** is a toggle through steamos-manager, read back. It appears where the device offers it, and otherwise shows as not offered.
2. **The BIOS check** reads the DMI version (world-readable) and states what is known about it for the Legion Go (`N3CNxxWW`): the bricking warning for N3CN42WW, and the missing features before v28 and v29. Keepsake never updates a BIOS.
3. **The display stays with Steam.**
   - The Other tab says where the refresh rate, frame limit and brightness controls are.
   - A "smooth mode" that matches refresh to the frame cap would set Steam's per-game settings for the user. That needs principle 15's explicit per-action consent and would compete with Steam's own toggle, so it is not built.
   - The HDR and colour fixes (an EDID fix on the Go 2) change gamescope's state and need X tools. They are left out.
4. **Where it appears:** Device, Other, and the desktop app's Other page.
5. **The Device check "BIOS check"** records the version, with a pass, warn or fail level from the known notes.

## Consequences

- No root, binary or new library.
- This closes R21's stages that need no root. Fans (stage 3) and the tier 1 parts of stages 4 and 5 wait for Peter's decision on ADR-0075. Those parts are writing `charge_types`, controller settings and RGB.
- Threat model: T144.
- Device run: part 4, step 27.
