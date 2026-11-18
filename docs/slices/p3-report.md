# P3 report: the desktop interface

P3 of the multi-device re-plan (ADR-0038). The interface is plain TypeScript with no framework (ADR-0040). It was built in three steps:
- the first screens (#49 and before);
- the Cloud and Updates pages (#52 and #53);
- this second pass.

## What changed in the second pass

- **Games.** Every discovered game, with a "Sync this game" switch, its sync state and how its save data was matched. Also:
  - a name filter;
  - a save-data picker (candidates plus a search) for games with several matches or none;
  - "Same game" and "A different game" when another device proposes a link.

  These are the same calls Gaming Mode uses: `match_games`, `update_game_config`, `approve_match`, `reject_match` and `search_titles`.
- **Settings.**
  - **This device:** the device name.
  - **Syncing:** the idle sync interval and the sync notification.
  - **Updates:** the update channel.
  - **Safety checks:** the limits, shown read-only. They can only be tightened, which stays in Gaming Mode.
- **Import.** Ludusavi backups: find them in a folder, see each game's backups, import the latest or every backup, with progress and Stop.
- **Navigation:** Overview, Conflicts, Games, Cloud, Import, History, Health, Modules, Updates, Settings.
- **Advisor** has no page on PCs. It is off by default and hidden there (ADR-0038), and stays reachable from Modules for anyone who turns it on.

## Test results

- `pnpm run build:desktop` (tsc) and eslint on `desktop/src`: clean.
- Render smoke test: the real host ran against scratch folders, and headless Edge captured Games, Settings, Import and Cloud. All four rendered with live data from the host. One wording fix followed: Cloud no longer promises a sign-in page when no client is set up.
- No backend code changed. Every call is one the Gaming Mode screens already use, and those calls are covered by their existing tests.

## Known gaps

- The games list was empty in the smoke run, because the scratch folders have no Steam library. Game cards are first seen on a real PC run, or in D1's screenshot harness with sample data.
- Per-game details (custom paths, exclusions, the registry option, history per game) stay in Gaming Mode for now.

## Threat model and assumptions

No change: the pages use only existing allowlisted calls through the token-protected loopback API (T97), and all text goes in through `textContent`.

## On-device checklist (PC run)

On a Windows PC with Steam:
1. Open Games and check that the Steam games and non-Steam shortcuts are listed.
2. Turn sync on for one game.
3. In Settings, change the device name and confirm it shows on the Overview.
4. Import a Ludusavi backup folder, if you have one.
