# ADR-0052: Storage: disk use, shader cache and "reset prefix, keep saves" (R5)

- Status: accepted (slice R5 of ADR-0047; decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0047 accepted two items for R5:
- a safe storage cleaner (item 13): per-game disk use, and clearing the shader cache;
- "reset prefix, keep saves" (part of item 14).

Whole-prefix backups stay deferred. Storage Cleaner lists "reset a prefix and keep saves" as an unfinished goal. Keepsake knows each game's save files, so it can do this safely. ADR-0047 decided that clearing a game's shader cache and moving its prefix are allowed new write locations after an explicit user action.

## Decision

1. **Disk use.**
   - **What is counted:** per game, the install folder, the prefix (Steam `compatdata/<appid>`, or a launcher's Wine prefix), the shader cache (`steamapps/shadercache/<appid>`) and the saves.
   - **How:** the walk never follows symlinks. Each part has its own share of the time (20 seconds a game, one minute for the whole list), so a huge folder never hides the rest, and the result says when a count is partial.
   - **Too-broad installs:** an install folder too broad to be the game's own, such as a shortcut started from `/` or the home folder, is not counted (`resolve.safe_base`).
2. **Clearing the shader cache** removes exactly `steamapps/shadercache/<appid>`. It needs a confirmation, never runs while the game runs, and never touches saves. Steam rebuilds the cache.
3. **"Reset prefix, keep saves"**, for a Steam game or shortcut in its own `compatdata/<appid>` prefix:
   1. It is refused while the game runs, or when the game is installed inside its prefix (the reset would move the game itself).
   2. **Keep a copy.** The save files are packed into a kept copy and verified (P3). The copy sits outside the rolling pre-restore list, so later restores cannot prune it. If packing or verification fails, nothing moves and no copy is left behind.
   3. **Move the prefix aside.** It is renamed to `compatdata/<appid>.keepsake-reset-<token>`: one rename on the same disk, with nothing deleted.
   4. **Rebuild.** The user starts the game once and quits. While the reset waits, the launch gate and exit save are skipped for that game, so the fresh, empty prefix is never pulled into or pushed from.
   5. **Put the saves back.** On that exit, once the game has stopped and Proton has built `pfx/drive_c`, the kept copy is restored into the fresh prefix. The usual pre-restore snapshot is taken first, so this can also be undone. This works whether or not the game syncs.
   6. **The old prefix stays** until the user deletes it. Before the saves go back, "Undo reset" puts it back exactly as it was. Any fresh prefix is moved aside, never deleted.
   7. **Deleting** only ever removes a folder named `<prefix>.keepsake-reset-<token>` for that game.
4. **Interface:** a Storage page in Gaming Mode. Prefixes are a handheld matter, so the PC interface does not show it.

## Consequences

- No new endpoint and no cloud change. The writes are the shader cache folder and the prefix rename, each after a confirmation.
- **Device checks:** whether Proton rebuilds a missing prefix at launch, and Steam a cleared shader cache, needs the device run (A186).
