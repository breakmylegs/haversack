# Changelog

All notable changes to Keepsake are listed here. Versions follow [Semantic Versioning](https://semver.org/). Each release uses its section below as release notes.

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
