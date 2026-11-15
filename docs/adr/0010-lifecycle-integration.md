# ADR-0010: Lifecycle integration

- Status: accepted (decided in slice 8 under the owner's delegation, 15 November 2026); the event source is still provisional until ADR-0001 has device results
- Date: 15 November 2026
- Deciders: Peter (owner)

## Decisions

1. **Events.** The frontend forwards Steam app lifetime notifications (start and exit) and game action starts to the backend unchanged. The backend normalises any ID shape (signed or unsigned 32-bit, or the 64-bit shortcut game ID `(appid << 32) | 0x02000000`) to the unsigned app ID and ignores games without "Sync this game". Repeated start events for a launch already being handled are ignored. This is ADR-0001's provisional option B with A as confirmation; device results may change it.
2. **Freeze mode (default)** follows build prompt section 10: poll 100 ms up to 5 s for the processes, freeze, pull with the configurable timeout (default 20 s, 5 to 60), release in `finally`; the freezer's 30 second watchdog and start-up recovery remain the backstop.
3. **While frozen the game counts as not running**, so a restore is allowed (principle 6). If the processes are not found in time, the game counts as running and a newer cloud save is not restored ("Cloud has a newer save. Quit the game to load it.").
4. **Timeout.** On timeout the game is released, marked pending, and the toast "Cloud check timed out. Playing the local save." is shown. The abandoned pull keeps running in its worker thread but from then on treats the game as running, so it can never start a restore under the released game.
5. **Strict mode** (per game, confirmed by the user): the launch options gain `<plugin dir>/bin/keepsake-gate` in front of `%command%` (or `<gate> %command% <options>` when the user's options had no `%command%`). The original string is saved before any change and restored exactly when strict mode is turned off. `keepsake-gate` is a shell script: it writes a request with a one-off token and waits for a ready file with the same token (so a stale file from an earlier launch never releases it), for the launch timeout plus 5 seconds, then starts the game whatever happens.
6. **Launch options are read** from `appDetailsStore.GetAppDetails(appid).strLaunchOptions` and set with `SteamClient.Apps.SetAppLaunchOptions` (verified in `@decky/ui`, assumption A65). `GetLaunchOptionsForApp` is not used: it returns the game's launch menu, not the user's options.
7. **"Off" mode** checks the cloud at launch but never restores at launch.
8. **Exit**: wait up to 30 s for the processes to end, then push; if they do not end, the idle pass saves later. Toasts: "Saved <game> to the cloud." (can be switched off in Settings), conflict and quarantine messages.
9. **Played without Keepsake**: Steam's last-played time later than Keepsake's last recorded session start (plus 2 minutes) raises a one-off toast; the same idle pass saves the changes.
10. **Packaging** normalises `bin/` scripts to LF line endings, so a script edited on Windows still runs.

## Consequences

- An abandoned pull may still download in the background after the game starts; it will not restore.
- Strict mode edits a Steam setting, which is allowed only as this explicit per-game opt-in (build prompt section 4).
