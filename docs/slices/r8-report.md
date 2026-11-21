# R8 report: Steam games sync like non-Steam games

Recorded in ADR-0063 (Peter's request of 21 November 2026).

## What changed

- **Audit.** Every save path (matching, roots, launch and exit, freeze, snapshots, History, restore, conflicts, retention, direct device sync) was checked for kind-specific code. None treats Steam games differently, so no save path changed. The findings are in ADR-0063.
- **Automatic switching on.**
  - `app._auto_sync_candidate` decides; `match_games` switches on played Steam games with no Steam Cloud saves and known save locations, and sends one message naming them.
  - It only acts on games that nobody has switched before (`enabledSource` is null).
- **Game settings:** new field `enabledSource` (null, `user` or `auto`). Any change to `enabled` through `update_game_config` records `user`.
- **Settings:** new `steamAutoSync`, default on. `showSteamApps` is no longer read.
- **Interface:**
  - The Games list always shows Steam games and opens on All, with a "Steam games can sync too" note and labels on each row.
  - The setup wizard lists Steam games.
  - The Settings toggle is now **Sync Steam games that Steam Cloud does not back up**.
  - The game page has new wording.
- **Docs:** ADR-0063, T121, A198, user guide (FAQ and getting started), CHANGELOG, device run part 4 step 1.

## Tests

- New in `tests/test_slice11.py`:
  - `test_played_steam_games_without_cloud_sync_automatically_once`;
  - `test_automatic_steam_sync_has_a_switch_and_needs_saves_and_detection`.
- Changed: the bulk-enable test now turns the automatic option off, so it still covers the manual button.
- Regression, chosen because they call `match_games` or touch game settings: `test_slice11.py`, `test_gameconfig.py`, `test_settings.py`, `test_app_ux.py`, `test_everyday_polish.py`, `test_identity.py`, `test_ordering.py`. All pass (one POSIX-only test skipped on Windows).
- **Mutation:** 9 mutants of the decision, the source recording, the message and validation.
  - All are killed after one test was added: a Steam game with its own key but no known save locations.
  - The kind check was removed as redundant: `_steam_cloud` only answers for Steam games.

## Known gaps

- If Steam Cloud detection misses a cloud game (A198), both keep its saves. Disagreements become conflicts, never overwrites.

## On-device checklist

- `docs/device-run.md` part 4, step 1.
