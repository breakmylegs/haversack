# ADR-0048: Save safety and control (R1)

- Status: accepted (slice R1 of ADR-0047; decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0047 accepted four items for R1:
- a better conflict screen;
- named checkpoints;
- partial restore;
- search and bulk actions on Games, with a plain-words Activity list.

Two of them touch the cloud: a checkpoint's name has to live somewhere every device can read, and a partial restore must still honour principle 3. The cloud layout and snapshot schema are frozen (an escalation item after slice 6), so each decision below says how it stays within them.

## Decision

1. **Conflict details.**
   - **The files:** each side lists the files added, removed or changed since the last shared save, by logical path (`winLocalAppData/...`), at most 200.
   - **This device's time:** the local side shows the device name and when its save last changed, taken from the newest file modification time instead of "now".
   - **Times inform only:** they are shown, never used to choose (P4), and nothing is auto-picked.
2. **Checkpoints use the pin record, not the snapshot schema.**
   - **What a checkpoint is:** a manual snapshot taken even when nothing changed (a new `snapId`), then pinned.
   - **Where the name lives:** in the pin object (`games/<key>/pins/<snapId>.json`) as an optional `label`, one line of 1 to 60 characters.
   - **Why the layout is unchanged:** pins are already write-once objects with an optional field (`until`). Readers since slice 5 accept any pin object with a `snapId` and ignore other fields, so older devices still see the checkpoint as a pin.
   - **Retention keeps it,** as it keeps every pin.
   - **What the name may hold:** it is free text the user types, so it should not name anything personal. The help text says what it is for.
3. **Partial restore.**
   - **The preview:** `restore_preview` lists what restoring a snapshot would do to each file (create, replace, delete). It reads metadata only and changes nothing.
   - **The restore:** `restore_snapshot(key, snapId, paths)` restores only the chosen `root/rel` paths. Each is checked: a known root, and a safe relative path.
   - **Principle 3 is kept whole:** the full pre-restore snapshot is still taken and verified first, so the partial restore can be undone like any other.
   - **What stays untouched:** every unchosen file. A file the snapshot lacks is removed only if chosen.
   - **The base is not moved,** because the result is a mix. The next sync records it as a new local save, so nothing is silently lost.
4. **Games search and bulk actions.**
   - **Who can use them:** search, then "Sync all shown" and "Stop syncing all shown", in Gaming Mode and on the desktop.
   - **What they touch:** only games whose save data is known (matched by title, Steam ID or by hand) and not waiting for a match confirmation.
   - **Confirmation:** both need a confirmation. Turning sync off never deletes anything.
5. **Activity.**
   - **The source:** `activity(limit)` turns the structured log into sentences, newest first, with game keys shown as game names.
   - **What it covers:** syncs, pulls, conflicts, checkpoints, restores, sign-in, imports and updates. Everything else stays in Logs.
   - **Nothing new is recorded:** the log was already redacted (T11). A new `snapshot.checkpoint` event marks checkpoints.

## Consequences

- No change to the snapshot schema or the cloud layout, beyond an optional field in an existing write-once object.
- Restoring a subset can leave a game in a state no snapshot holds. That is expected, and the next sync uploads it as a normal new snapshot.
