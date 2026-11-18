# ADR-0051: Games from other launchers, and emulator saves (R4)

- Status: accepted (slice R4 of ADR-0047; decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0047 accepted two coverage items for R4:
- emulator saves (RetroArch and the EmuDeck standalones), with save states optional;
- games from Heroic, Lutris and Bottles, with Heroic's own GOG and Epic cloud sync handled like Steam Cloud.

## Primary sources

- **Ludusavi's launcher readers** (MIT; `src/scan/launchers/heroic*.rs` and `lutris.rs` in 0.31.0, read on docs.rs):
  - **Heroic GOG:** games come from `gog_store/installed.json` (`installed[].appName`, `platform`, `install_path`), with titles from `store_cache/gog_library.json` or the older `gog_store/library.json` (`games[].app_name`, `title`).
  - **Heroic Epic:** Legendary's `installed.json` (`title`, `platform`, `install_path`).
  - **Heroic prefixes:** `GamesConfig/<appName>.json`, keyed by app name, with `winePrefix` and `wineVersion.type`. Only `wine` and `proton` count.
  - **Lutris:** `games/*.yml` (`game.prefix`, `game.exe`, `game.working_dir`, `name`) and `pga.db` (`SELECT name, configpath FROM games`). The spec's prefix wins over the database.
- **Bottles:** the Flatpak data folder is `~/.var/app/com.usebottles.bottles/data/bottles` (Bottles docs, "Migrate directories to Flatpak"). Each bottle's `bottle.yml` lists `External_Programs` with a `name` and a `path`.
- **EmuDeck's RetroArch page:** on SteamOS, `Emulation/saves/retroarch` holds symlinks into the Flatpak's `~/.var/app/org.libretro.RetroArch/config/retroarch/saves` and `states`.
- **Heroic:** GOG cloud saves are off by default per game, and the setting's key is not documented.

## Decision

1. **Launcher games are read, never written.**
   - **What `keepsake/launchers.py` reads:**
     - Heroic, native and Flatpak (GOG and Epic, Windows games only);
     - Lutris Wine games;
     - Bottles programs.
   - **What each game becomes:** a game with its install folder and its prefix.
     - A Proton prefix (holding `pfx`) is resolved exactly like Steam's.
     - A plain Wine prefix (holding `drive_c`) becomes `wine_prefix`, with the Windows user folder found inside: `steamuser`, else the only other user.
     - With several users, the user folders stay unavailable (fail closed).
   - **Matching:** saves are matched through the Ludusavi manifest by title, like any shortcut.
2. **Emulators are one entry each, with one game key on every device.**
   - **Profiles:** `data/emulators.json` lists the save folders of the builds EmuDeck installs: RetroArch, Dolphin, PCSX2, DuckStation and PPSSPP (Flatpak), and RPCS3 and Cemu (AppImage).
   - **Folders:** they are relative to the home folder. These are the real folders, not EmuDeck's symlinks, which Keepsake never follows. Using the home folder also keeps out SD card labels (P10).
   - **When found:** the first time an emulator is found, its config gets the folders as custom paths and the game key `emulator-<id>`. It is off by default, and the user's later changes are never reset.
   - **Save states:** a toggle on the game page, off by default.
3. **Running checks.** A Wine game counts as running while any process has its prefix in `WINEPREFIX` or `STEAM_COMPAT_DATA_PATH`. A prefix shared by several games counts for all of them (fail closed, P6). An emulator counts as running while a process has its `FLATPAK_ID` or one of its program names. The process scan keeps `WINEPREFIX` and `FLATPAK_ID` for this.
4. **Syncing games whose launch Keepsake cannot see.**
   - **Pushing:** Heroic, Lutris, Bottles and emulator games push from the idle pass, as before.
   - **Pulling:** the idle pass also brings in a newer save from another device, or the first copy on a device that never synced the game, using the launch decision table: only when nothing changed here and the game is not running. Anything else becomes a conflict for the user.
   - **The launch gate** (freeze and strict) stays for Steam games and shortcuts.
5. **One fix in the sync engine.** A never-synced device with no save files no longer raises an "adoption" conflict when it pushes. Nothing there needs protecting, and the next pull brings the cloud save in. This applies to every kind of game.
6. **Heroic's own cloud sync.** Its setting is not documented, so it cannot be detected reliably. Each Heroic game carries a note: "Heroic can also sync this game's saves with GOG or Epic; use one or the other".
7. **A setting.** `otherLaunchers` (on by default) shows these games on Linux devices. They never appear on Windows.

## Consequences

- No new endpoint, root or cloud object. Emulator saves use the existing `home` root and custom paths.
- **Device checks:** the emulator folders and the launcher formats need a device run (A184, A185).
- Windows Heroic and Playnite stay out of scope (ADR-0047).
