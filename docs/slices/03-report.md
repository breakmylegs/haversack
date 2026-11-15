# Slice 3 report: discovery

- Branch: `slice/03-discovery`
- Target version: 0.3.0 (changelog section added; `package.json` is bumped by `pnpm release prepare 0.3.0`)
- Date: 14 November 2026
- Built without your input, at your request: where I would have asked, I chose the recommended option (listed below).

## Context

Slices 1 and 2 were merged at your request and **v0.2.0 is published**: https://github.com/breakmylegs/keepsake/releases/download/v0.2.0/Keepsake-v0.2.0.zip (SHA-256 `63a5d6ea1e84bc4b0680a6eae020f03b3a3565609a8249b50c31f30dc82f36b6`, unsigned, release notes state that the device tests were not run). Publishing untested needed a new `--accept-untested` option on `scripts/release.py`, merged as PR #3, so `--device-tested` was never passed untruthfully.

## What changed

**Backend (`discovery.py`)**
- Default Steam user from `config/loginusers.vdf` (`MostRecent`, then `Timestamp`), only for users with a `userdata` folder; falls back to the newest `userdata` folder. Account and persona names are never read into results.
- `appmanifest_*.acf` reading per library; Steam runtimes and tools filtered by app ID and name prefix.
- `discover()`: every Steam root (native, `~/.steam`, Flatpak), every library, shortcuts for all users with the default user first, Steam apps once each. Each game has a device-local key, kind, unsigned app ID, prefix (`compatdata/<id>` with a `pfx`, base library first), library index, `base` folder (`StartDir`, else the exe's folder; `steamapps/common/<installdir>` for Steam apps), whether the exe sits inside the prefix, last played, and notes (`no-prefix`, `install-folder-missing`, `shortcuts-unreadable`).
- `cross_check()` compares a running game's `STEAM_COMPAT_DATA_PATH` values with the discovered prefix: `match` only when every observed path is the expected prefix.
- `record_cross_check()` and `sync_blocked()`: mismatches persist in the runtime folder until a later check matches; an unreadable file blocks every game and is never overwritten (fail closed).

**App**: `discover_games(refresh)` (cached scan, with mismatches) and `check_running_prefix(key)`.

**Frontend**: Games page (filters for shortcuts, Steam games and all; rescan; prefix location, last played, flags such as "other Steam user" and "PREFIX MISMATCH, sync blocked"; "Check running prefix" on the running game). "Open Keepsake" now opens Games.

## Decisions made for you

1. Default user from `loginusers.vdf`, falling back to folder times.
2. Tools filtered by a known app ID list plus name prefixes.
3. Shortcuts of non-default users are listed, marked "other Steam user", rather than hidden.
4. A mismatch is sticky until a matching check, and unreadable state blocks everything.

## Test results

Local, Windows, Python 3.14.3:

- Tests by name: `tests/test_discovery_games.py` (new), `tests/test_discovery.py`, `tests/test_app.py`, `tests/test_diagnostics.py`: 39 passed, 2 skipped (the skips are `posix` symlink tests, including the new `/var/home` discovery test).
- Synthetic fixtures cover signed and unsigned IDs, an ID beyond the signed range, three users (one without `shortcuts.vdf`), an SD card library, missing prefixes, a prefix folder without `pfx`, tools, a corrupt `shortcuts.vdf`, bad manifests, no Steam at all, and no account names in results.
- `pnpm run check`: all checks passed.
- Mutation checks: 10 guards broken one at a time, all caught. The first run found that the "default user first" test passed by luck (folder times happened to agree); the test now sets folder times the other way.

## Known gaps

- Nothing has been run on a device. All Steam file formats are as documented by the community (assumptions A37 to A40).
- Health warnings for mismatches appear on the Games page only; the health panel is slice 9.
- The cross-check runs when you press the button; automatic checks at launch come with slice 8.

## On-device checklist

1. Update from v0.2.0 to this build once it is released as v0.3.0 (Keepsake, Updates). This is also the first real test of the in-plugin updater.
2. Open Keepsake, Games. Confirm your non-Steam shortcuts are listed with "compatdata/<id> on the internal library" or "library N" for SD card games.
3. Pick the game known to have different compatdata IDs on the two devices. On each device, confirm the ID shown matches the folder you know it uses.
4. Switch to "Steam games" and confirm Proton and Steam Linux Runtime are not listed.
5. Launch a shortcut, open Games, press "Check running prefix" on it. Expect "uses the discovered prefix".
6. Report any shortcut with "No prefix found" that does have a prefix.
