# ADR-0091: Looks, stage 1: boot and sleep animations, and the theme plugins read only

- Status: accepted (R29 stage 1; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

R29's research (`docs/research/decky-plugins.md`) recommends, for the "looks" area:
- **Boot and sleep animations,** from local files and synced between devices.
- **Sync of CSS Loader and Audio Loader packs** between devices.
- **Detecting CSS Loader and Audio Loader,** with no theme engine of Haversack's own.

Peter asked for each area to be a switchable module, with coexistence, own code only, and privacy rules.

**Facts** (read in source, not copied):
- **Animation Changer** (TheLogicMaster/SDH-AnimationChanger, BSD-3-Clause, `main.py`): Steam plays `deck_startup.webm`, `steam_os_suspend.webm` and `steam_os_suspend_from_throbber.webm` from `~/.steam/root/config/uioverrides/movies`. Animation Changer keeps its sets in its data folder, `animations/<set>/`.
- **Audio Loader** (DeckThemes/SDH-AudioLoader, `audio_utils.py`): sound packs are in `<homebrew>/sounds/<pack>/pack.json`.
- **CSS Loader:** themes are in `<homebrew>/themes/<theme>/theme.json`.
- **`plugin.json` names:** "CSS Loader", "Audio Loader" and "Animation Changer".

The movies folder is outside the write allowlist (build prompt v2 section 6.3), which is an escalation item.

## Decision

1. **A new module, Looks,** off by default because it writes outside the earlier allowlist. It is not available on Windows, where Steam has no boot videos. Its page is Device, Looks, in Gaming Mode and the desktop app.
2. **Write allowlist addendum.** Exactly the three file names in `<steam root>/config/uioverrides/movies`, plus Haversack's own `looks` folder in its data folder (its record, and kept originals). Nothing else.
3. **The rules for the videos:**
   - **Sources.** Only plain WebM files (the EBML header, at most 100 MB, no links) from Videos, Downloads, Animation Changer's sets and Haversack's own folder, one folder level deep. A choice is an index and a relative path, resolved and refused if it points outside its source folder.
   - **Writing.** Copied to a temporary name beside the target, checked by SHA-256, then renamed into place.
   - **Keeping the original.** A video already there that Haversack did not write is kept once, before the first change. **Use Steam's own** puts it back.
   - **Never another tool's file.** Reset removes a file only if it still matches the hash Haversack recorded. A video another tool changed is left alone.
   - **Deferring.** While Animation Changer is installed, Haversack shows the videos and changes nothing.
   - **Running games.** The videos are Steam's interface, not a game's files, so they are not under a game lock (P6, P19 do not apply).
4. **Themes and sounds are only read.** No theme engine: CSS Loader's engine is GPL-3.0, depends on DeckThemes' class translations, and two injectors would fight (the research, section 3.1.1). The page lists their themes and sound packs, with size limits on every file and field, and points to the plugins in Decky's store.
5. **No network.** Stage 1 adds no endpoint. Browsing steamdeckrepo.com would need its own decision.
6. **Next, stage 1b:** sending themes, sound packs and animations to the other handheld over Replication, as a new offer kind like emulator games (ADR-0087), with its own protocol addendum.

## Consequences

- One more module and page. Nothing changes until the user switches Looks on and picks a video.
- **Threat model:** T163.
- **Assumptions:** A246.
- **Device run:** step 52.
