# ADR-0094: Pausing the running game, with its own record and an hour's watchdog

- Status: accepted (R29 stage 3; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

R29's research recommends a user-triggered **pause a game** for the performance and display area. Pause Games does this, but it is GPL-3.0, so the feature is written clean-room. Haversack already stops a game's processes behind a watchdog (`freeze.py`, P11, T6), but only for its own short freezes:
- before launch;
- around a restore.

Those freezes have a hard ceiling of 30 seconds, which is a safety default. A pause the user asks for must last longer, without loosening that default.

The research also judged the other items in this area:
- **CPU and GPU clocks:** only if a need shows (new root jobs).
- **Undervolting:** skipped (it needs `ryzenadj`, which breaks P9).
- **Colour saturation:** later, after a gamescope probe on both devices.
- **A profile on AC or dock:** later.

## Decision

1. **Pause game and Resume game** in the quick access menu's Now playing, while a game runs, as part of the Device module (the performance area's module). This is a user action only, and Haversack never pauses by itself.
2. **A separate freezer.** The pause uses its own `Freezer`, with its own record (`paused.json`) and a watchdog ceiling of 60 minutes. It reuses the existing safety rules:
   - the PID list is persisted before any signal;
   - a PID is resumed only if its start time still matches;
   - the watchdog runs on its own thread.

   Haversack's own freezes keep `frozen.json` and their 30-second ceiling unchanged. The `Freezer` constructor caps any ceiling at one hour, whatever a caller asks.
3. **Always released (P11).** The paused game runs again on Resume, and also when:
   - the game exits;
   - the Device module stops;
   - Haversack unloads;
   - the next start, after a crash or reboot with the game still paused;
   - the hour is up, in which case a toast says so.
4. **No clash with saves.** Haversack never pauses while its own freeze for that game (the save check) is under way, and a pause touches processes only, never files (P6, P19).
5. **The other items stay in the plan:**
   - AC or dock profiles;
   - saturation, after a probe;
   - clocks, only if needed.

## Consequences

- **Threat model:** T166.
- **Device run:** step 56.
- **Unverified on a device:** how gamescope and Steam's overlay show a stopped game.
