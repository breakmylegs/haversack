# Changelog

All notable changes to Keepsake are listed here. Versions follow [Semantic Versioning](https://semver.org/). Each release uses its section below as release notes.

## [0.8.0]

Slice 8: lifecycle integration. Saves now sync on their own when you start and quit a game.

### Added

- When a synced game starts, Keepsake pauses it for a moment, loads a newer cloud save if there is one, and lets it continue. A watchdog always releases the game within 30 seconds.
- When the game quits, its saves go to the cloud, with a message you can switch off in Settings.
- If the cloud is slow, the game starts with the local save after the launch check timeout (Settings, 5 to 60 seconds) and the check is finished later.
- Optional strict launch gate per game: the game waits for the check before it starts. Your own launch options are kept and restored exactly when you turn it off.
- A warning when a game was played while Keepsake was not running; its saves are uploaded at the next idle pass.

## [0.7.0]

Slice 7: sync engine. Automatic sync on game launch and exit comes in slice 8; until then the game page has "Check before play" and "Save after play".

### Added

- "Sync this game" per game, and the sync rules: a newer cloud save is restored before play, new progress is saved after play, and a device that has never synced a game adopts the cloud save when it matches.
- Conflicts when both sides changed, when two devices saved from the same point, or when a device's unsynced files differ from the cloud. Choices: "Use cloud save", "Use this device's save" or "Decide later". Whichever side is not chosen is kept and pinned for at least 90 days.
- Offline play: the game always starts; checks and saves wait and are reconciled when the cloud is back.
- Every 30 minutes, for synced games: newer cloud saves are downloaded ahead of time so a restore at launch is local, changes made while Keepsake was not running are saved, and a missed exit save (for example after Steam was closed) is recovered with the message "Recovered missed exit backup".

## [0.6.0]

Slice 6: OneDrive sign-in and cloud store. Syncing on game launch and exit comes in slices 7 and 8.

### Added

- Sign in to OneDrive from Gaming Mode with your phone: Keepsake shows a code and a QR code; you finish on microsoft.com. Keepsake can only see its own folder, `Apps/Keepsake`.
- OneDrive client ID setting, with step-by-step setup in `docs/setup-entra.md`.
- Tokens refresh automatically and are stored privately on the device.
- Snapshots can go to OneDrive ("Use OneDrive for snapshots" in Settings). Uploads never overwrite anything, are checked against the hash OneDrive reports, and large files upload in resumable chunks.
- Each device registers itself once in the cloud.
- "Test connection" and "Sign out".

### Changed

- The cloud layout and snapshot format are now frozen (`docs/cloud-layout.md`).

## [0.5.0]

Slice 5: snapshot engine and safety rails. Snapshots go to a local test store on the device; the cloud comes in slice 6.

### Added

- Snapshots of a game's save files: hashed, packed into a zip and recorded with a complete file list.
- Restores are atomic: either all the new files are in place or none are, even if the device loses power mid-restore. The files present before every restore are saved first, verified, and can be put back with "Undo to this" (the last five per game).
- Safety gates: a snapshot that empties the save, removes more than half the files or shrinks by more than 70% is kept on the device as quarantined and never uploaded unless you release it. The limits can be made stricter in Settings.
- Pinning, and retention that keeps recent, daily and monthly snapshots and never removes pinned, current or manual ones.
- Game page "Snapshots (local test store)" panel to try all of this on the device.

### Security

- Snapshot zips are fully checked before anything is extracted: no unexpected paths, symlinks, oversized or encrypted entries, and every file's hash must match.

## [0.4.0]

Slice 4: manifest resolution and save preview. Still does not sync saves.

### Added

- Downloads the Ludusavi manifest of save locations, checks for changes weekly (using its ETag) and keeps a compact index on the device. "Update manifest" on the Games page refreshes it on demand.
- Each game is matched to a manifest entry by Steam ID or by title, ignoring case, punctuation, edition names such as "Game of the Year Edition" and roman numerals. Several matches are shown as a choice rather than guessed.
- Game page: matched title and game key, "Change match" with search, include config files (off by default), custom folders through the file picker, exclusions, and a preview of the files that would be synced with counts and sizes.
- Logs, crash dumps, shader and web caches and temporary files are excluded by default.
- Paths that cannot be resolved safely are skipped and listed with the reason.

### Security

- Every resolved path must stay inside its root; escaping symlinks are ignored; a game folder that is too broad (such as `/` or the home folder) is refused.

## [0.3.0]

Slice 3: discovery. Still does not sync saves.

### Added

- Games page listing non-Steam shortcuts for every Steam user (the most recent user first) and installed Steam games, with filters and a rescan button.
- Each shortcut's Proton prefix is found from its app ID in `shortcuts.vdf` (signed values converted to unsigned) across all Steam libraries, internal storage first, including SD cards.
- Steam runtimes and tools (Proton, Steam Linux Runtime, redistributables) are left out.
- "Check running prefix" compares a running game's actual prefix with the discovered one; a mismatch is remembered and will block sync for that game.
- Supports Steam in `~/.local/share/Steam`, `~/.steam` and the Flatpak location, and `/var/home` home folders as on Bazzite.

## [0.2.0]

Slice 2: release pipeline and in-plugin updater. Still does not sync saves.

### Added

- Updates page: check for updates, release notes, "Update now" and "Install this version" for any earlier release (rollback).
- "Update available" row in the Quick Access Menu and a toast when a new version is found, checked at most once a day.
- Updates are verified against the release's `SHA256SUMS` and handed to Decky Loader's own installer, which asks you to confirm and checks the hash. If this Decky version does not allow that, Keepsake shows the zip address as text and a QR code.
- "Updated to vX.Y.Z" toast after an update.
- Stable and Pre-release update channels in Settings.
- Updates are refused while a sync job runs, with an "Update when idle" option. Diagnostics has a "Simulate sync job" button to test this.
- Read-only safe mode when the settings file comes from a newer version, and settings unknown to an older version are preserved on rollback.
- `pnpm release prepare <version>` and `pnpm release publish` build, checksum, sign (with minisign when configured), tag and publish releases locally.

## [0.1.0]

Slice 1: skeleton, development loop and on-device diagnostics. Does not sync saves.

### Added

- Plugin skeleton from decky-plugin-template, with no root flag.
- Quick Access Menu panel and a full-screen Keepsake route with Diagnostics, Logs and Settings pages.
- Settings store with a device ID and an editable device name.
- Structured, redacted, rotated JSON-lines logging and a log viewer.
- Diagnostics page that records Python and module availability, Decky environment variables, Steam roots and libraries, `shortcuts.vdf` app IDs (signed and unsigned) with matching compatdata folders, the running game's process tree, Steam client lifetime, game action and suspend events, and which Decky install routes are visible.
- Freeze test that pauses the running game for 5 seconds behind a 30 second watchdog.
- Diagnostics export to the settings folder.
- `LocalFolderStore` with create-only writes.
- Local quality gate `pnpm run check` (lint, type checks, build, version consistency, packaging, ruff, mypy, secret scan) and `pnpm run test:device` to run Linux-only tests on a device over SSH. No GitHub Actions.
