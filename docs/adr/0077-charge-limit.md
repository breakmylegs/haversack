# ADR-0077: The battery charge limit, through steamos-manager only

- Status: accepted (Peter's request of 21 November 2026, item 3, stage 4 (folding in R17), decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

Stage 4 of the Legion Go controls is the battery: the charge limit and charging status. R17, the charge limit for the Legion Go and Go 2, folds in here.

The research (`docs/research/legion-control.md`) found:

- **Lenovo's firmware has one limit, at 80 percent** ("Long Life", BIOS v29 and later). It is not a percentage you can choose.
- **The kernel route needs root.** From kernel 7.2 the kernel shows the limit as the battery's `charge_types` (`Standard` or `Long_Life`), and only root can write it. There is no `charge_control_end_threshold` for the Legion.
- **steamos-manager may offer it without root.** Its `BatteryChargeLimit1` sets `MaxChargeLevel` (a percentage, or -1 for none) without root, where Valve's device file enables it. Valve's Legion file did not enable it when last read. SteamOS 3.8 has "preliminary" Legion charge limiting in Steam's own settings.
- **Every other tool uses root.** They write `charge_types` or use acpi_call.

## Decision

1. **Read the state from the kernel** (world-readable): the system battery's `charge_types`, or a threshold where a kernel shows one. A controller's battery (scope `Device`) is never read.
2. **Change it only through steamos-manager** (ADR-0075 tier 0). On sets `MaxChargeLevel` to 80, and off sets it to -1. Each change is read back.
3. **Where steamos-manager does not offer it:**
   - Keepsake shows the limit's state, on or off.
   - It says where to change it: Steam's settings, Power, or Desktop Mode's power settings.
   - It writes nothing.

   Writing `charge_types` needs root, so it is tier 1, waiting for Peter's decision.
4. **Where it appears:**
   - Device, Battery.
   - A "Stop charging at 80%" toggle in the quick access menu, shown only where Keepsake can change it.
   - The desktop app's Battery page.
   - Charging state and power were already on Device, Status (ADR-0074).
5. **The Device check "Battery charge limit"** records who controls the limit on each device, and its state:
   - **pass** when steamos-manager offers it;
   - **warn** when only the kernel shows it;
   - **fail** when neither shows it.

## Consequences

- No root, binary or new library.
- If Valve enables the charge limit in the Legion device file, Keepsake's toggle appears by itself, with no new release needed.
- Threat model: T142.
- Device run: part 4, step 25.
