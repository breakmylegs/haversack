# ADR-0063: Steam games sync like non-Steam games, and switch on by themselves without Steam Cloud

- Status: accepted (Peter's request of 21 November 2026, decided under ADR-0037)
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

Build prompt section 14 hid Steam games by default because Steam Cloud usually covers them. The `showSteamApps` setting kept them out of the Games list and the setup wizard. Steam games without Steam Cloud saves could still be synced, but only after finding a setting, then **Sync them all** (slice 11). Peter wants:
- Steam games treated the same as non-Steam games throughout save sync and backup;
- the Games list to make it obvious that they can be turned on;
- a played Steam game with no Steam Cloud saves turned on automatically, with Steam Cloud games left off.

## Audit: does any save path treat Steam games differently?

Every path was read for `kind` checks:
- **Matching:** Steam games match by Steam app ID first (`manifest._match_manifest`), and their game key comes from the manifest title, so it is the same on every device. Identity matching (ADR-0011) is only for shortcuts, because Steam app IDs are already the same everywhere.
- **Roots:** `resolve.logical_roots` gives a Steam game its install folder as `base` and `compatdata/<appid>` as its prefix, the same as a shortcut.
- **Launch and exit:** `_games_for_appid` selects by app ID whatever the kind. `procs.find_game_processes` finds Steam games by `SteamAppId`, `SteamGameId` or `STEAM_COMPAT_DATA_PATH`. Freeze, the launch gate and the exit push are the same code.
- **Snapshots, History, restore, conflicts, retention and direct device sync (ADR-0061):** keyed by game key only, with no kind check.
- **Different by design:**
  - Send to and Replication handle non-Steam games only. Steam installs its own games.
  - Steam Cloud detection applies to Steam games only.

No save path needed a code change. The differences were in the interface (hidden list, wording) and the default.

## Decision

1. **Always listed.** The Games list always shows Steam games, opens on **All**, and keeps the **Steam games** filter. A note at the top says Steam games can sync too, with the number synced automatically and the number left to Steam Cloud. Each row says "no Steam Cloud, synced automatically", "uses Steam Cloud, off until you turn it on" or "Steam game, can be synced". The setup wizard lists Steam games as well. `showSteamApps` is no longer read. It stays in the settings file, so an older version still finds it after a rollback.
2. **Switched on automatically**, when every one of these holds:
   - it is a Steam game whose Steam Cloud state is `no-cloud`: played, with no `remotecache.vdf` and nothing in `remote/` (slice 11);
   - it matches the manifest by Steam ID, title or the user's choice, so its save locations are known;
   - it has a game key and no open match proposal;
   - the Saves module, Steam Cloud detection and the new setting **Sync Steam games that Steam Cloud does not back up** (`steamAutoSync`, default on) are all on;
   - nobody has ever switched it.

   Steam Cloud games (`cloud`) and games never played (`unknown`) stay off.
3. **The user's choice wins for good.** Game settings gain `enabledSource` (`null`, `user` or `auto`). Any change to `enabled` through the normal path records `user`. Automatic switching on records `auto`, and only acts on games whose source is `null`. A Steam game the user turns off therefore stays off, and so does one they never turned on after switching off the setting.
4. **Said out loud.** When games are switched on automatically, Keepsake logs it and shows one message naming them ("Steam does not back up their saves. Turn any off in Keepsake's Games list").
5. **Where it runs.** The check runs in `match_games`, which every Games list scan and the idle pass already call. There is no separate scan.

## Consequences

- After updating, every played Steam game without Steam Cloud saves on a device starts syncing, once. The message lists them.
- If detection misses a Steam Cloud game (for example, Steam Cloud on but nothing synced yet), Steam and Keepsake both keep its saves. Keepsake never overwrites silently: if the two disagree it raises a conflict (P1). See T121.
- The game page now says that Steam games sync exactly like non-Steam games, and that when Steam Cloud keeps a copy too, Keepsake asks whenever the two disagree.
