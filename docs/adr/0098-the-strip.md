# ADR-0098: The strip: install games and move them, nothing else

- Status: accepted
- Date: 24 November 2026
- Deciders: Peter (owner)

## Context

By v0.60.0 Haversack had seven modules: Saves, Advisor, Replication, Installer, Desktop, Device and Looks, plus a PC host for Linux and Windows and a root helper plugin. The owner asked to strip it back: "All I want this plugin to do is be able to install non steam games (from iso, network etc.) with all the features we have built. I want it to sync installed games when the user wants that and with the features we have built. No save game sync. No other features." Learnings may later move into smaller plugins.

The owner chose four things (24 November 2026):
- delete the code, keeping a `full` branch at v0.60.0;
- drop the desktop app and PC support: handhelds only;
- keep sending emulator games between devices;
- saves are copied once with the first send of a game, then protected on every update.

## Decision

1. **What stays:** Core (discovery, the manifest, game settings, Steam operations, the module registry, updates, the rename from Keepsake, device checks, diagnostics, logs), the **Installer** module with all its sources (ISO, folder, mounted shares, SMB, WebDAV, web server, the SD card and network probes), artwork for installed games, any non-Steam game and streaming tiles, and the **Replication** module with pairing, sending, getting, keeping in step and emulators.
2. **What goes:** Saves (sync, snapshots, restore, conflicts, history, retention, freeze, the launch gate, playtime, identity, import and export, every cloud store and sign-in), Advisor, Desktop (the tray, the desktop app, the loopback host), the PC host and package, Device (power, fans, battery, controllers, reconnect help, storage, SD cards, uninstall, launch option presets, pause) and Looks, and the root helper. Their tests, docs and screenshots go with them. The `full` branch, pushed at v0.60.0 (commit 667e4e1), keeps every line.
3. **Save protection stays.** A game's first send copies its whole prefix, saves included. Every later update leaves out each save and config file the Ludusavi manifest lists for the game (`_replication_keep`, `replication/ongoing.keep_relative`), whether or not the game was ever synced. So the manifest download, `resolve.py` and the game settings stay, and Settings, General shows the manifest's credit (MIT) and status.
4. **Replication is on by default** (`DEFAULT_FLAGS = {"replication": True, "installer": True}`); it is now one of the two things the plugin does. **The listener stays off** until the user switches on "Let other devices reach this one" (P17 and ADR-0016 are unchanged).
5. **Game events reach every game.** Steam's start and exit events are passed to the bus for any app ID, with `gameKey: None`, so Replication's "checked after you quit" and Install's "installer finished" work without Saves. The same events open and close update sessions, so an update still waits while a game runs (build prompt section 12).
6. **The menu has four sections:** Install; Games and devices (Games, Moving games, Other devices, Emulators); Settings (General, Modules, Updates, Help); Diagnostics (Device checks, Tools, Logs). Games is new: the device's non-Steam games, each opening Send, Keep in step and Artwork. Old addresses of removed sections and pages open the nearest page left (`LEGACY`, `MOVED`).
7. **Releases ship one zip** under the four names (Haversack and Keepsake, versioned and stable), plus the SBOM and the signed `SHA256SUMS`. No PC package, no helper. The packager refuses to ship a stray `client_secrets.json`, and publishing no longer needs it.
8. **Upgrade behaviour:**
   - Settings, cloud tokens, game lists and every file the removed features wrote stay in the settings folder, untouched, and cloud snapshots stay in the cloud. Reinstalling v0.60.0 from Updates brings them all back.
   - Stored module flags are filtered to the two modules left.
   - The desktop entries v0.60.0 wrote (`~/.config/autostart/keepsake-tray.desktop`, `~/.local/share/applications/keepsake.desktop`) are removed on start, only when they carry Haversack's own `X-Keepsake-Version=` marker (`leftovers.py`), so the tray never starts a host that is gone.
   - Old quick menu shortcuts for removed pages are kept in the setting but not shown (`clean_choice` already keeps unknown IDs).
9. **Version 0.61.0**, a minor version: the project is before 1.0, and the release rule gives features a minor version.

## Consequences

- The principles about saves (P1 to P4, P6, P11, P14) no longer have code to govern beyond Replication's save protection; they stay in CLAUDE.md for the `full` branch and any later save plugin. P13 and P19 still apply to the two modules.
- **Known risk:** v0.60.0 recovered an interrupted restore and released a frozen game on start. Without that code, a device that crashed mid-restore or mid-freeze and then updated straight to 0.61.0 is not recovered. Both need a crash in a window of seconds followed by this update; the restore journal and frozen list stay on disk, and reinstalling v0.60.0 recovers them.
- PC installs of the Keepsake-desktop package stop receiving updates; the release notes say so.
- An older peer that offers a looks transfer now falls through to the game path and is refused there; acceptable, since both devices update together.
- Network endpoints shrink to GitHub (updates and the manifest), SteamGridDB with the user's key, user-typed Installer locations and paired peers. No endpoint, scope, binary or write location is added.
- The build prompts stay as the historical record; where they describe removed features, this ADR wins.
