# ADR-0060: Keeping games in step between devices (slice 20a)

- Status: accepted (decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

Spec section 8.2, "Ongoing sync", asks for:
- a per-game policy of Off, Manual (the default) or Auto;
- a change scan on `game_exited` and in the idle loop;
- an offer or an automatic pull when one side changed, and when both changed, showing the user and doing nothing until they choose.

Two hard rules apply:
- **P14:** Replication never writes a Saves-managed path after the first copy, and a test must assert it.
- **Exclusions:** config-tagged paths are excluded by default, because the screens differ.

Slice 20 is built in two parts, like the others:
- **20a (this ADR):** the backend;
- **20b:** the controls on the game page and on Devices.

## Decision

1. **Links.** Every game sent (slice 19) is linked on both devices under its offer ID.
   - **What a link records:**
     - the game's folders on this device (`install` and `prefix`, never the tool or the artwork);
     - the paired device;
     - the policy, Manual by default;
     - a state: in step, changed here, update available, both changed, or updating;
     - the base: each folder's root hash at the last sync.
   - **Where links live:** `replication-games.json`, at most 64.
2. **What counts as a change.**
   - **The scan:** it hashes the folders, leaving out the usual exclusions plus every file Saves resolves for the game, with config files included in that resolution. The comparison ignores case, as Windows names do.
   - **The base:** a link's first scan becomes its base. It is taken in the background when the link is made.
   - **A change:** a later root that differs from the base means the game changed on this device.
3. **When scans run:**
   - when a linked game exits;
   - when the user presses **Check now** (20b).

   The idle loop does not rehash whole installs. Changes to an installed game happen while it runs or while it is patched, and both end in `game_exited` or a user action. Rehashing tens of gigabytes on a timer would cost battery for nothing. This is a deliberate narrowing of the spec's "and on the idle loop".
4. **Updates are offers.**
   - **The offer:** an update carries `update: {link, base}`, the base it started from, and only the folders whose root changed. That is a new optional field of the `offer` request (ADR-0059), so it adds to protocol version 1 and changes nothing existing.
   - **What it may hold:** game files only, so no `exe`, no tool and no artwork.
   - **The sender's side:** sending an update sets the sender's base to what it sent.
5. **On the receiving device:**
   - **Manual:** the update waits for **Apply** (20b).
   - **Auto:** it is applied by itself, unless this device changed the game too.
   - **When both changed** (this device's scan differs from its base):
     - nothing is written;
     - the link shows both changed;
     - the user chooses **Take theirs** (apply with `take_theirs`) or **Keep mine** (decline the update, so this device can send its own).
   - **While a game is running:** a transfer already waits (ADR-0058).
6. **Applying an update never writes saves (P14).**
   - **Where it goes:** the copy goes into staging as always, against the game's existing folders.
   - **Before the swap, after every check** (`transfer.carry_over`):
     - each file in the job's keep list is copied from the current folder into the new copy, over anything there;
     - the keep list is this device's own Saves files and config files, as Saves resolves them here;
     - a link in the new copy can never lead outside it.
   - **The swap:** the folders are then swapped as before (ADR-0057). Saves' files come out byte for byte as they were, and the sender's saves are never sent in an update at all.
   - **The test:** `tests/test_replication_ongoing.py` asserts it.
7. **"Stop and remove" on an update** stops the copy and deletes its staging, and never deletes the game's folders: they are not the offer's. The game is left exactly as it was.
8. **The Steam game page context menu.** The spec asks for menu entries there. Keepsake puts the controls on its own game page instead (20b), because adding entries to Steam's own menu needs patching Steam's interface, which goes beyond the Steam write policy (P15).

## Consequences

- No new endpoint, binary or permission.
- **T118 and A196:**
  - T118: an update overwriting saves or settings, or a hostile update;
  - A196: whether a patch changes files only while the game runs or during an update by the user.
- **Device checks:** a patch propagating under Manual and Auto, in `docs/slices/20a-report.md`.
