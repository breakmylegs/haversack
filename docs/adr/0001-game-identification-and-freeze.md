# ADR-0001: Game identification and freeze approach

- Status: **draft**, waiting for slice 1 on-device results
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

Keepsake must know which game is launching, find its processes, pause them while the launch pull runs and always release them (build prompt section 10, principles 6 and 11). Non-Steam shortcuts have per-device app IDs. Open questions the slice 1 Diagnostics page answers on both devices:

1. Does `RegisterForAppLifetimeNotifications` report a shortcut's real app ID in `unAppID`, or 0?
2. What does `RegisterForGameActionStart` pass as `appId` for a shortcut: the 32-bit app ID, the 64-bit game ID, or something else? Does it fire before the game's processes exist?
3. Does `SteamUIStore.MainRunningApp` identify the shortcut while it runs?
4. Which environment variables do the game's processes carry: `SteamGameId` as the 64-bit game ID `(appid << 32) | 0x02000000`, `SteamAppId`, `STEAM_COMPAT_DATA_PATH`?
5. Does `SIGSTOP` on the matched tree pause the game cleanly, and does `SIGCONT` resume it without audio, controller or Gamescope problems?

## Options

**Identification**

- A. Lifetime notification `unAppID`, if it is the real shortcut ID.
- B. Game action start `appId`, converted from the 64-bit game ID if needed. Fires earliest, so best for the launch gate.
- C. `SteamUIStore.MainRunningAppID` polled after launch. Fallback.

**Process matching (backend)**

Match on `STEAM_COMPAT_DATA_PATH` equal to the resolved prefix (primary), then `SteamGameId` or `SteamAppId` (secondary), plus all descendants, owned by the plugin user, never the plugin or its ancestors. Implemented in `procs.find_game_processes` in slice 1.

**Freeze**

`SIGSTOP` to every matched process, PIDs and start times persisted first, a 30 second watchdog thread, `SIGCONT` in `finally`, resume on backend start. Implemented in `freeze.Freezer` in slice 1.

## Results

To be filled from the slice 1 diagnostics exports, one column per device.

| Question | Legion Go 2 (SteamOS) | Legion Go (SteamOS) |
|---|---|---|
| 1. Lifetime `unAppID` for a shortcut | | |
| 2. Game action `appId` for a shortcut, and timing | | |
| 3. `MainRunningApp` for a shortcut | | |
| 4. Process environment and match reason | | |
| 5. Freeze test outcome | | |
| Steam app (control): lifetime and game action IDs | | |

## Decision

Pending results. Provisional choice: B for the launch gate, with A as confirmation of exit and C as fallback; process matching and freeze as implemented.

## Consequences

To be written with the decision.
