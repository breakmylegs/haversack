# ADR-0080: "When saves differ: take the newest", an opt-in exception to principle 4

- Status: accepted (Peter's request of 21 November 2026, R16 step 2, decided under ADR-0037). It amends principle 4 for one opt-in setting, and principle 1 within it. This loosening was an escalation item, recorded here as the standing delegation asks.
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

With several save locations (ADR-0071), Peter asked for step 2:

- take the newest save when versions differ;
- a clock guard;
- Undo;
- History showing which locations hold each snapshot;
- a "When saves differ" setting.

Two principles stand in the way:

- **Principle 4:** hashes decide, timestamps inform. Timestamps never pick a winner.
- **Principle 1:** never silently overwrite. When local and cloud have both changed, the user resolves the conflict.

Taking the newest by itself breaks both, unless the user turns it on and every safeguard stays.

## Decision

1. **A setting, "When saves differ".**
   - **"Ask me"** is the default, and works exactly as before.
   - **"Take the newest"** is opt-in.
   - It sits in Settings, Sync and safety, and on the desktop app's Settings page.
2. **With "Take the newest", a fork is settled by time only when time can be trusted** (`keepsake/newest.py`):
   - Exactly two versions differ: this device and one other. Several versions still ask.
   - Both times are known: this device's last file change, and the other version's snapshot time.
   - Neither time is more than 5 minutes ahead of this device's clock. A device with a fast clock would otherwise always win.
   - The times are at least 2 minutes apart. Devices whose clocks are a minute or two out cannot flip the answer.

   Otherwise Keepsake asks, as before, and says why: "too close in time", "a device's clock looks wrong", or "more than two versions".
3. **The same resolution as the user's choice** (`SyncEngine.resolve`):
   - This device's files are kept, pinned, before anything is replaced.
   - A pre-restore snapshot is taken (principle 3).
   - The other version stays pinned in History.
   - The fork is closed with a merge.

   No data is lost, so principle 2 and principle 3 hold in full.
4. **When it runs:**
   - wherever a conflict was announced: after a launch, after an exit, in the idle pass, and after a manual pull or push;
   - as a background task that waits for the game's lock.

   If the game is running, it waits and tries again at the next exit or idle pass (principle 6).
5. **Telling the user.**
   - A toast names the version kept, the device and the margin, for example "Example Quest: kept the other device's newer save from Handheld A (60 min newer). The other one is in History; Undo brings it back."
   - The game's History shows "Keepsake took the newer save" with **Undo**.
   - Undo restores the replaced version through an ordinary restore, which is reversible too. There is one Undo per choice.
6. **History shows which save locations hold each snapshot** when there are several, for example "In: onedrive, direct". It comes from each location's listing, fetched when History opens.

## Consequences

- **Principle 4 now reads:** hashes decide and timestamps inform, except where the user turned on "Take the newest", under the guard above. Principle 1's "the user resolves" is met by the user's own opt-in, with Undo.
- **The setting stays on this device** and is not shared across devices, so each device decides for itself.
- **Threat model:** T145.
- **Device run:** part 4, step 28.
