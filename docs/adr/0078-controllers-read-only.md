# ADR-0078: The Legion controllers, read-only for now

- Status: accepted (Peter's request of 21 November 2026, item 3, stage 5, decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

Stage 5 of the Legion Go controls covers the controllers and RGB. Peter asked for:

- button remapping, including the back paddles;
- stick and trigger dead zones;
- gyro, touchpad and controller sleep;
- RGB lighting (colour, effect, brightness, per profile);
- controller battery levels.

The research (`docs/research/legion-control.md`) found:

- **The kernel's driver shows the controllers.** From kernel 7.1, `hid-lenovo-go` covers the Legion controllers (USB 17EF:61EB to 61EE). Each controller's battery is a power supply with scope `Device`, and the stick rings are the LED class `go:rgb:joystick_rings`.
  - Settings it exposes include mode, rumble, auto-sleep, gyro and the touchpad.
  - Every one of these files is 0644 root: any user can read it, but only root can write it.
- **Existing tools write as root.** They use these files, or hidraw vendor reports, as root or behind a udev rule that opens every Lenovo USB device to all users.
- **Steam Input already covers several controls,** for any controller: remapping (back buttons included), dead zones, trigger settings and gyro.
- **InputPlumber can remap without root,** through its D-Bus policy, where it runs (Bazzite). Steam Input already offers remapping, so this adds little now.

## Decision

1. **Read what the kernel shows** (`keepsake/device/controllers.py`):
   - each controller's battery;
   - the settings the controllers report;
   - the stick lights' state;
   - whether InputPlumber or Handheld Daemon is running.

   Nothing is written.
2. **Point remapping, dead zones and gyro to Steam's controller settings.** Steam Input already does these well and per game, so Keepsake does not duplicate them.
3. **Changing the controllers' own settings and the stick lights needs root,** so it is ADR-0075 tier 1. The Controllers tab says so plainly. Those controls arrive only if Peter approves the helper.
4. **Where it appears:** Device, Controllers, and the desktop app's Controllers page.
5. **The Device check "Controllers"** records what each device's kernel shows: controllers, battery count, the rings, and any tool in charge. Tier 1 would be planned from that record.

## Consequences

- No writes, root or binary.
- Older kernels (before 7.1) show nothing, and the tab says why.
- Threat model: T143.
- Device run: part 4, step 26.
