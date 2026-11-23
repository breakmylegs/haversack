# ADR-0093: Library extras: artwork for any non-Steam game, and ProtonDB on the library badge

- Status: accepted (R29 stage 2; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

R29's research (`docs/research/decky-plugins.md`, section 3.2) recommends these library extras:

- **"Find artwork" for any non-Steam game,** using the SteamGridDB path Haversack already has for installed games and streaming tiles (ADR-0027, ADR-0081).
- **A ProtonDB badge on the game page,** from Advisor's ProtonDB index (ADR-0035). This is clean-room: ProtonDB Badges is GPL-3.0, and no code is used from it.
- **Lower-priority items:**
  - syncing TabMaster and SteamGridDB settings (their file names are unverified);
  - a one-off PlayTime import;
  - PCGamingWiki links.

Principle 15 requires that originals be stored before a Steam write, and the research's coexistence notes say: never overwrite artwork Haversack did not set without asking.

## Decision

1. **Artwork for any non-Steam game, only the kinds it lacks.** A non-Steam game's page shows **Artwork** when Steam's grid folder has no custom image for one or more of:
   - the cover;
   - the wide cover;
   - the background;
   - the logo.

   The user picks the game on SteamGridDB, and Haversack queues SteamGridDB's images for those kinds only, through Steam's own artwork call (P15, the existing `set-artwork` operation). It never replaces an image the user or another tool set, so there is no original to store, and P15's "originals first" is met by never overwriting.

   This reuses the Installer's SteamGridDB setup and key, with no new endpoint. It is off when the Installer module is off.
2. **ProtonDB on the library badge, read only.** While Advisor and its ProtonDB source are on, a Steam game's badge shows a second line, "ProtonDB: N% of M reports say it works".
   - **Source:** the line comes from the index already on the device.
   - **No requests:** the badge never downloads the index and never names a game to anyone.
   - **Caching:** each game is looked up once and cached in memory, at most 500 games.
   - **Layout:** a game with no saves badge shows the ProtonDB line alone, and non-Steam games show none.
   - **Advisor stays read-only:** this only displays data (P16).
3. **Deferred:**
   - syncing TabMaster and SteamGridDB settings, until their file names are verified on a device;
   - the PlayTime import, because Haversack's own playtime already covers it (ADR-0049);
   - a PCGamingWiki link, because Advisor already links each source.

## Consequences

- **Threat model:** T165.
- **Device run:** step 54.
- **Desktop app:** the artwork section is in Gaming Mode only. Steam's artwork calls run in the Gaming Mode frontend, so the desktop app would only queue them.
