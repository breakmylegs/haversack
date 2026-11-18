# R1 report: save safety and control

Slice R1 of the post-v2 roadmap (ADR-0047), recorded in ADR-0048.

## What changed

- **Conflict screen.**
  - **Backend:** each side carries a per-file list (added, removed or changed since the last shared save, at most 200). The local side shows the device name and when its save last changed.
  - **Interfaces:** the Gaming Mode modal shows up to 8 files per side. The desktop page has an expandable list.
- **Checkpoints.**
  - **Backend:** `snapshot_game(key, label)` takes a new snapshot even without changes and pins it with the label, which is stored in the write-once pin object.
  - **Interfaces:** a "Save checkpoint" modal, in the Quick Access Menu while playing and in each game's History. Checkpoints are listed by name.
- **Partial restore.** `restore_preview` and `restore_snapshot(key, snapId, paths)` restore only the chosen files. The full pre-restore snapshot comes first, and the base stays. Gaming Mode lists the preview with switches.
- **Games.** Search, plus "Sync all shown" and "Stop syncing all shown" (with a confirmation), in Gaming Mode and on the desktop.
- **Activity.** `activity(limit)` gives plain sentences from the log. There is a new Activity tab in Gaming Mode and a new desktop page with a screenshot in the guide.
- **Docs:** ADR-0048, T105, A179, the user guide (conflicts, history and Activity) and the changelog.

## Test results

- `tests/test_save_safety.py` (17 new): passed.
- Covering tests passed: `tests/test_app_snapshots.py`, `tests/test_app_ux.py`, `tests/test_engine.py`, `tests/test_restore.py`, `tests/test_sync.py` and `tests/test_host.py`, 92 in all.
- Mutation checks: 14 mutations of the new backend code, all killed.
- Frontend: `tsc` and eslint clean. The desktop pages were rendered by the screenshot harness.

## Known gaps

- The Gaming Mode screens (the checkpoint modal, the partial restore switches, Games search and bulk, Activity) need the device check below.
- Playtime and save thumbnails on the conflict screen come later (ADR-0047 items 11 and 12).

## On-device checklist (handheld)

1. **Checkpoint while playing.** Start a synced game, open the Quick Access Menu, choose **Save checkpoint**, keep or change the name, and save. Quit, then check that Games, the game and History show "Checkpoint: <name>", pinned.
2. **Partial restore.** In that game's History, choose **Restore some files** on an older snapshot. Turn on one file and restore it. Check that only that file changed, then use **Undo to this**.
3. **Conflict.** Make a conflict between the two handhelds. Check that the modal shows this device's time and the per-file lists, and that "Decide later" still has the first focus.
4. **Games.** Type part of a name in **Find a game**, then try **Stop syncing all shown** and **Sync all shown** with the confirmation.
5. **Activity.** Open the Activity tab and check that it describes the steps above in plain words.
