# ADR-0076: Performance profiles per game, through steamos-manager

- Status: accepted (Peter's request of 21 November 2026, item 3, stage 2, decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

Stage 2 of the Legion Go controls is TDP and per-game profiles, applied at launch. Peter asked for:
- Lenovo's performance modes (quiet, balanced, performance, custom), with SPL, SPPT and FPPT where supported;
- CPU boost, SMT and cores;
- the GPU clock range;
- later, Auto TDP.

ADR-0075 tier 0 allows writes through steamos-manager only. The research is in `docs/research/legion-control.md`.

## Decision

1. **A new module, Device** (`device`, P13).
   - It is on by default, and unavailable on Windows.
   - It has its own flag, health check, profiles file (`device-profiles.json`, kept on this device only) and lifecycle listeners.
2. **What it controls now:** the performance mode, one TDP limit and CPU boost.
   - It sets them through steamos-manager's session-bus interfaces (`PerformanceProfile1`, `TdpLimit1`, `CpuBoost1`), using Keepsake's own D-Bus client.
   - Each part is optional. A part the device's steamos-manager does not offer is shown as unavailable.
3. **What is left out, and why:**
   - **Separate SPL, SPPT and FPPT.** steamos-manager sets all three from one value. Setting them separately needs root (tier 1).
   - **SMT and cores.** steamos-manager offers no control for them.
   - **The GPU clock range.** steamos-manager's GPU clock is a single manual value, which Steam already offers.
   - **Auto TDP.** It needs frame-rate feedback (the Advisor's session data and Steam's performance reports). It follows once these profiles are proven on the devices.
4. **Profiles are per game.**
   - A profile holds a mode, a TDP and boost, each optional, keyed by Steam app ID on this device.
   - While a game runs, a change made on the Power tab or in the quick access menu is kept for that game.
5. **The game's lifecycle:**
   - **Start:** the game's profile is applied in the background, so it never delays the launch.
   - **Exit:** each value that still holds what Keepsake set goes back to what was there before.
     - The mode is restored last, because restoring it resets the firmware's limits.
     - A value that something else has changed is never undone.
   - **Resume:** the profile is applied again, because the firmware resets Custom when the mode changes.
   - **Module off, or plugin unload:** what Keepsake set is put back.
6. **A TDP means Custom.** The firmware uses power limits only in Custom (the kernel docs and every tool agree). So asking for a TDP switches to Custom first, when the device offers it.
7. **Two clamps on every value:** steamos-manager's range and the device profile's range (`devices.py`). Every write is read back, and a mismatch is an error.
8. **Never fight another tool.**
   - **Tools that set TDP or the mode themselves:**
     - the Decky plugins SimpleDeckyTDP, PowerControl, LegionGo2Companion, LeGoTDP, Legion Go Toolbox and Legion Center;
     - a running Handheld Daemon.

     While any of them is present, Keepsake shows the settings read-only, names the tool and says how to hand over. It never disables, moves or edits the other tool.
   - **Steam's own per-game performance settings** write through the same steamos-manager.
     - Five seconds after applying a profile, Keepsake looks again.
     - If anything has changed a value it set, Keepsake stops applying until the next launch, keeps that value, and says so in a toast and on the Power tab.
9. **Where the controls appear:**
   - Device, Power: mode, TDP slider, boost, and this game's profile with "Forget it".
   - The quick access menu's Now playing section: mode and TDP.
   - The desktop app's Power page.
10. **The Device check "Performance control."** It records what steamos-manager offers on each device. It also writes the current TDP or mode back unchanged, to prove a write works.

## Consequences

- No root, binary, endpoint or new library. The only write route is steamos-manager.
- Threat model: T141.
- Assumptions: A221, A222.
- Device run: part 4, steps 23 and 24.
