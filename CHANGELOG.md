# Changelog

All notable changes to Keepsake are listed here. Versions follow [Semantic Versioning](https://semver.org/). Each release uses its section below as release notes.

## [Unreleased]

### Added

- Every release also carries `Keepsake.zip`, a byte-identical copy of `Keepsake-v<version>.zip`, so a first install always uses the same URL: `https://github.com/breakmylegs/keepsake/releases/latest/download/Keepsake.zip`. `SHA256SUMS` lists both names. The in-plugin updater still uses the versioned zip.

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
