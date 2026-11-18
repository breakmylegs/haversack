# R5 report: storage

Slice R5 of the post-v2 roadmap (ADR-0047), recorded in ADR-0052.

## What changed

- **`keepsake/storage.py`:**
  - folder sizes (symlinks never followed, time-limited);
  - per-game disk use, with the install, the prefix, the shader cache and the saves each timed separately, and broad installs not counted;
  - shader cache removal;
  - moving a prefix aside, putting it back, and deleting a prefix that was moved aside (only one named after the game's own reset).
- **Engine:** `keep_copy` and `restore_copy`. A verified kept copy of the saves sits outside the rolling pre-restore list.
- **App calls:** `storage_usage`, `clear_shader_cache`, `reset_prefix`, `cancel_prefix_reset` and `delete_old_prefix`.
  - **On exit:** the saves go back after the first launch on the fresh prefix.
  - **While a reset waits:** the launch gate and exit save are skipped for that game.
  - **Every action** refuses while the game runs.
- **Interface:** a Storage page in Gaming Mode.
- **Docs:** ADR-0052, T110, A186, `docs/user/storage.md`, the changelog and the plan.

## Test results

- `tests/test_storage.py` (13 new): passed. The full reset runs end to end: kept, moved, gate skipped, restored, old prefix deleted.
- Covering tests passed, 161 in all: engine, lifecycle, app snapshots and UX, host, launchers, R1, restore and resolve.
- Mutation checks: 17 of 18 killed after four tests were added.
  - The survivor is symlink-following, whose test is POSIX-only and runs on the device.
  - The new tests also found one leftover: a half-made copy after a failed verification. It is fixed.
- `tsc` and eslint clean.

## Known gaps

- Proton rebuilding a missing prefix, and Steam a cleared shader cache, are unverified until the device run (A186).

## On-device checklist (handheld, a game you do not mind resetting)

1. **Count disk use.** Open Storage and choose **Count disk use**. Check the sizes look right for a few games.
2. **Shader cache.** Choose **Clear shader cache** on one game, then start it. It should run, perhaps with a little stutter at first.
3. **Prefix reset.** On a non-Steam game with saves, choose **Reset prefix, keep saves**. Start it once and quit at the title screen. Check that a toast says the saves are back, and that your progress loads next time. Then choose **Delete old prefix**.
4. **Undo.** On another game, reset and then choose **Undo reset** before starting it. The game should work exactly as before.
