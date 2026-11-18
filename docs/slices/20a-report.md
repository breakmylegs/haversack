# Slice 20a report: keeping games in step

The first part of slice 20, recorded in ADR-0060. Slice 20b adds the controls.

## What changed

- **`replication/ongoing.py`:**
  - game links (folders, peer, policy, state and base);
  - scans that leave out Saves' and config files, whatever their case;
  - a link's first scan becomes its base;
  - the states.
- **`replication/transfer.py`:** jobs carry a keep list. `carry_over` copies those files from the current folder into the new copy before the swap, after every check and never through a link leading outside it.
- **`replication/offers.py`:**
  - update offers (`update: {link, base}`; game files only), validated;
  - `Outgoing.prepare_update`, which offers only the folders whose root changed;
  - `Incoming.accept_update`, which writes into the game's existing folders with the keep lists;
  - a finished update reports through `on_done`, and new offers through `on_offer`;
  - "Stop and remove" on an update never deletes the game's folders.
- **App:**
  - links are made after a send and after a received game is ready, with the base taken in the background;
  - a scan runs when a linked game exits;
  - "Send update", "Apply update" (refused when both sides changed, unless "Take theirs") and "Keep mine";
  - Auto applies an update by itself when only the other side changed;
  - 6 calls: `replication_games`, `_set_policy`, `_check_game`, `_send_update`, `_apply_update` and `_keep_mine`.
- **Docs:** ADR-0060, T118, A196, the module document, the plan and the changelog.

## Test results

- **The feature:** `tests/test_replication_ongoing.py`, 12 passed and 1 skipped on Windows (the link-escape test is POSIX-only). It covers:
  - **the P14 assertion:** after an update, the receiving device's save is byte for byte as it was, and the sender's save is never sent;
  - a save that reached the copy anyway is still replaced by this device's own;
  - a stopped update leaves the game as it was;
  - an update with no change is not offered;
  - update validation, and accepting an update needing the game's folders;
  - carry-over, links and their base, the states, and case-insensitive save exclusion;
  - both sides changed, Take theirs and update done, in the app;
  - Auto applying by itself while Manual waits.
- **Regression for what changed:** `test_replication_sendgame.py` (offers), `test_replication_transfer.py` (jobs), `test_replication_protocol.py` (the offer format) and `test_host.py` (the call lists): 116 passed in all.
- **Mutation checks:** 12 mutations of the new logic. 11 are killed on Windows. The 12th, the carry-over's link check, is covered by the POSIX test on the device.

## Known gaps

- There are no controls yet (20b).
- Scans run when a game exits or on request, not on the idle timer (ADR-0060 point 3).

## On-device checklist (after 20b)

1. Send a game from the Legion Go 2 to the Legion Go (slice 19), and play it on both.
2. **Manual:** patch or mod the game on the Legion Go 2 and quit it. Check that it shows "changed here", press **Send update**, and apply it on the Legion Go. Check that the patch is there and that the Legion Go's saves are its own.
3. **Auto:** set the game to Auto on both devices, change it on one, and check that the other takes it by itself.
4. **Both changed:** change the game on both devices, then send an update. Check that the receiving device asks, and that **Keep mine** writes nothing.
5. Run `python scripts/test_on_device.py tests/test_replication_ongoing.py` for the POSIX test.
