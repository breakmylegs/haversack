# ADR-0061: Save sync directly between paired devices, with no cloud account (R7)

- Status: accepted (decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

Peter chose option C on 18 November 2026: saves going between his own devices with no cloud account, beside one-button cloud sign-in (option A). ADR-0054 made it slice R7, after the transfer engine, to reuse Replication's link. The rules that stay:
- never silently overwrite (P1);
- write-once objects (P2);
- reversible restores (P3);
- hashes decide (P4);
- fail closed (P5);
- Saves owns save data (P14);
- modules do not reach into each other (P13).

## Decision

1. **A store on every device, merged by copying.**
   - **The store:** "Directly between my devices" (`snapshotStore` `direct`) keeps the snapshot store in a folder on the device (`<runtime>/direct-store`).
   - **The engine:** the sync engine, retention, pins, conflicts, restores and every safety gate work on it unchanged.
   - **The exchange:** when two paired devices can reach each other, each copies from the other the save objects it lacks.
   - **Why copying is safe:** every object is written once, so copying what is missing never overwrites anything. Two devices that exchanged hold the same history.
   - **Saves changed on both devices** meet as two branches. The engine shows a conflict exactly as with a cloud store (P1).
2. **Order and retention.**
   - **Blobs first:** objects are fetched with snapshots last, so a snapshot never arrives before the blob it names. This is the engine's own commit order.
   - **A pruned marker wins:** retention writes a write-once `pruned` marker before it deletes a blob (slice 6).
     - A blob with a marker on either device is never copied.
     - A blob here whose marker arrives from the other device is deleted here.

     Retention on one device decides for both, as it does in a shared cloud store. This is retention's own decision carried over, not a deletion outside retention.
3. **When exchanges run.**
   - **Before a launch's pull,** bounded by half the launch pull timeout.
   - **On the idle pass.**
   - **When the other device says it pushed** (`store-changed`).
   - **When the user presses Sync now.**
   - **After a push,** this device tells its paired devices, so they fetch soon.
   - **An unreachable device never blocks play** (P5). It is noted, and play goes on with the saves this device has. Later exchanges bring the rest, and anything changed on both sides becomes a conflict.
4. **Three additions to protocol version 1** (ADR-0059's rule: only new request types):
   - `store-list`: the keys and sizes under `games/`;
   - `store-get`: one part of an object, at most 4 MiB, by key, offset and length;
   - `store-changed`.

   **What a device refuses:**
   - all three, unless it syncs saves directly itself;
   - any key outside `games/` or not a valid store key;
   - parts over 4 MiB;
   - an object that arrives at the wrong size, which is not kept.

   Only paired devices reach them at all (ADR-0054).
5. **Module isolation (P13).**
   - **`keepsake/directsync.py` is Saves' side.** It does not import Replication. The app hands it a connection that offers `request` and `request_blob`, and registers its handlers on the Replication listener.
   - **The dependency:** direct sync needs Replication on, for pairing and the listener. The Cloud page says so, and until then it shows the choice as not ready.
   - **P14 is unaffected:** these are Saves' own snapshot objects, written by Saves.
6. **What the user gives up.** There is no copy away from the user's devices, and the Cloud page says so. If every device is lost, so is the history. A cloud store remains the choice for an off-site copy. Switching between stores later works as it always has.

## Consequences

- No new endpoint, binary or permission. The store is in Keepsake's own folder, and the link is Replication's.
- **T119 and A197:**
  - T119: a paired device sending bad objects, or a retention marker used to delete;
  - A197: whether both devices are seldom on together.
- **Device checks:** in `docs/slices/r7-report.md`.
