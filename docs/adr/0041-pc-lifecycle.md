# ADR-0041: Game lifecycle on PCs: watch, never pull under a running game

- Status: accepted (decided under ADR-0037; P4 of ADR-0038)
- Date: 17 November 2026
- Deciders: Peter (owner)

## Context

On Decky, Steam's frontend reports a launch before the game runs. Keepsake then freezes the game, pulls the cloud save and thaws it (the launch gate, P6, P11). A PC host has no such hook: it only sees a game once its process exists. The Windows host also cannot freeze processes (ADR-0038).

The existing running checks (`find_game_processes`) read Linux `/proc`. On Windows they would always answer "not running", which would let a restore write saves under a running game.

## Decision

1. **The watcher.** `keepsake/pcwatch.py` lists the user's own processes every 5 seconds:
   - Windows: `EnumProcesses` and `QueryFullProcessImageNameW`, with `PROCESS_QUERY_LIMITED_INFORMATION` only;
   - Linux without Decky: `/proc/<pid>/exe`.

   It sends `start` and `exit` to the app's lifecycle. A process belongs to a game when:
   - it is the shortcut's program; or
   - it sits inside the Steam game's install folder; or
   - it sits inside the shortcut program's folder, if that folder is at least three levels deep and not the home folder.

   A shortcut at a drive root can never make every program look like a game.
2. **A start on a PC only records the session.** The game is already running, so the launch gate (freeze, pull, thaw) never runs on a PC host. It publishes `game_started` for the other modules.
3. **An exit pushes, as on Decky.**
4. **Pulls happen only while nothing runs:** through Sync now, the idle pass and the desktop interface. Conflict detection still guards every pull (P1).
5. **One running check for every write.** `KeepsakeApp._game_running` covers the sync engine's restore guard, the registry guard and the exit wait:
   - on Decky it reads `/proc` as before;
   - on a PC it lists the processes at that moment, not the watcher's last look, so a stale poll can never let a write through (P6).
6. **Logging.** Process paths are never logged; a failed look logs only the error class.

## Consequences

- Saves on a PC are pushed within seconds of a game exiting, and are never restored under it.
- A save changed on another device is pulled the next time Keepsake syncs while the game is closed, not at the moment of launch. That is slower than on a handheld, but never unsafe.
- An opt-in launch wrapper for pull-before-launch on PCs can come later, as its own decision.
