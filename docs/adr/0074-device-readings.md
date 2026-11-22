# ADR-0074: Device readings, the first stage of the Legion Go controls

- Status: accepted (Peter's request of 21 November 2026, item 3, stage 1, decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

Peter wants Keepsake to be his main Legion Go and Legion Go 2 app. The controls ship in stages, each a stable release, starting with read-only status: temperatures, fan speed, power, BIOS and modes.

The research into existing tools (`docs/research/legion-control.md`) and the permission model for controls that write come before stage 2, the first stage that changes anything. This stage writes nothing and needs no permission beyond what any user has, so it does not wait for them.

## Decision

1. **Readings come from world-readable sysfs files only** (`keepsake/hardware.py`, in Core). That means:
   - every hwmon chip's temperatures, fan speeds and power;
   - the system battery: level, state, power, and the `charge_control_end_threshold` where the kernel exposes it;
   - the amdgpu power reading;
   - the BIOS version and date from DMI;
   - the ACPI platform profile, from `/sys/class/platform-profile/*` (kernel 6.14 and later) or the older `/sys/firmware/acpi/platform_profile`;
   - CPU boost, SMT and the cores online.
2. **What is never read or done:**
   - serial numbers and UUIDs are never read;
   - no file is written, and no root, helper or binary is used;
   - a missing or broken file is left out, never guessed.
3. **Lenovo's mode names.** The kernel's profile names are shown in Legion Space's words: low-power is Quiet, then Balanced, Performance and Custom. The kernel's own name is shown beside each.
4. **Core, not Advisor.** The Advisor's session sensors are Advisor internals (P13). The device controls will be their own module, so the readings live in Core, where both can use them.
5. **Where the readings show.**
   - Device, Status in Gaming Mode and in the desktop app, every 2 seconds while the page is open.
   - The new Device check "Device readings" records what each device exposes: chips, sensor and fan counts, the profile and its choices, the BIOS version and the charge limit. The next stages are built against that record.
6. **What this stage proves.** Which fan reading, mode file and charge limit each of Peter's devices exposes. These decide stages 2 to 4, after the research and the permission ADR.

## Consequences

- **No new endpoint, scope, binary, write or privilege.**
- **Threat model:** T140.
- **Device run:** part 4, step 22.
- **Next:** stage 2 (TDP and per-game profiles) starts with `docs/research/legion-control.md` and the permission-model ADR. Anything there that needs root waits for Peter's approval of that ADR.
