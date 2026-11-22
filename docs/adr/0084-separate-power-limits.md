# ADR-0084: Separate power limits (SPL, SPPT, FPPT) through the Keepsake Helper

- Status: accepted (R24, Peter's request of 22 November 2026; ADR-0075 tier 1, ADR-0083; decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

steamos-manager's TDP limit writes one value to all three of the firmware's power limits:
- SPL, sustained;
- SPPT, slow boost;
- FPPT, fast boost.

Peter asked for them separately. `docs/research/legion-control.md` records the facts:
- **Where they are.** The kernel's Lenovo WMI driver (from v6.17) exposes them as firmware attributes `ppt_pl1_spl`, `ppt_pl2_sppt` and `ppt_pl3_fppt` under `/sys/class/firmware-attributes/lenovo-wmi-other-*/attributes/`.
- **Permissions.** `current_value` is 0644 root. `min_value`, `max_value` and `scalar_increment` are world-readable.
- **Custom mode only.** Writes give EBUSY outside the Custom platform profile, and any other mode makes the BIOS override them.
- **Resets.** The firmware resets Custom to its defaults on every mode change.

## Decision

1. **Reading needs no root.** Keepsake reads the values and the firmware's ranges itself (`keepsake/device/powerlimits.py`).

2. **Writing goes through the helper.** It is a new job, `power.set` (`keepsake_helper/power.py`), with `power.read` to report:
   - **Only these three attributes,** found under the fixed root.
   - **Each value must be valid:** an integer within the attribute's own minimum and maximum and on its increment. SPL <= SPPT <= FPPT.
   - **Custom mode is required.** The helper refuses unless the platform profile is already `custom`. Keepsake switches the mode through steamos-manager first (tier 0), so the helper never changes the mode itself.
   - **The writes are ordered** so the three never cross, and all three are read back. A value the firmware did not keep is an error.

3. **Keepsake clamps first,** to the firmware ranges and steps, keeping the values rising, and the helper checks again.

4. **Per-game profiles** gain an optional `limits` part next to mode, TDP and boost. The existing rules apply:
   - Custom is set first, and the limits come after the TDP, because steamos-manager's TDP writes all three.
   - Values are restored on exit, the limits before the mode, and only where they still hold what Keepsake set.
   - A change by anyone else (Steam, the user, Legion L+Y) stops Keepsake until the next game. Keepsake never fights it.
   - The limits are applied again after resume, as the profile already is.

5. **Where it appears.** Device, Power has a "Separate power limits" section with three sliders, which change nothing until Apply. It needs the helper; without it the current values are shown read-only. The desktop app's Power page has the same.

6. **Write allowlist (helper).** `current_value` of the three `ppt_*` attributes only.

## Consequences

- **What goes through the helper:** only the three power limits. The mode stays on steamos-manager.
- **No new binary, endpoint or scope.**
- **Fixed on the way:** the Power panel's rows no longer remount on every update. A component was defined inside the render, and the row helper is now a plain function.
- **Threat model:** T154. **Assumptions:** A235. **Device run:** step 41.
