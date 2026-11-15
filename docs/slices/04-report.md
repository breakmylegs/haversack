# Slice 4 report: manifest resolution and save preview

- Branch: `slice/04-manifest`, stacked on `slice/03-discovery` (PR 4, not merged)
- Target version: 0.4.0 (changelog section added; bumped by `pnpm release prepare`)
- Date: 14 November 2026
- Built without your input, at your request. Decisions are in ADR-0006.

## What changed

**Backend**
- `yamlsubset.py`: streaming parser for the manifest's block-YAML subset; unsupported constructs skip only their entry.
- `manifest.py`: download with ETag to a temporary file (`net.fetch_to_file`, streamed, 64 MB cap), weekly background refresh, compact JSON index, title normalisation, `game_key` slug, matching (manual, Steam ID, title and aliases, ambiguity reported), title search.
- `resolve.py`: logical roots per device (Proton and native), placeholder mapping, `when` handling, case-insensitive matching in prefixes, root confinement, escaping symlinks ignored, over-broad `base` refused, default exclusions, user exclusions and custom paths, preview with counts, sizes, samples and skipped paths.
- `gameconfig.py`: per-game settings (match override, aliases, config files, custom paths, exclusions), validated; file-picker folders converted to root plus relative path.
- `discovery.py`: games now carry their Steam root and default user (for `steamUserdata`).
- App methods: `manifest_status`, `refresh_manifest`, `match_games`, `search_titles`, `get_game`, `update_game_config`, `add_custom_path`, `preview_game`. Diagnostics export includes manifest status.

**Frontend**
- Games page: manifest status with attribution, "Update manifest", match per game, "Open" for each game.
- Game page: match and game key, "Change match" search, include config files, custom folders via the Decky file picker, exclusions, preview.

**Other**
- `THIRD_PARTY_NOTICES.md`, shipped in the zip: MIT notice for the bundled `qrcode-generator` (missed in slice 2) and attribution for the Ludusavi Manifest.

## Decisions made for you (ADR-0006)

1. Manifest from the `data` branch, because the README says `master` will stop being updated.
2. Own streaming subset parser instead of a vendored YAML library.
3. Store constraints ignored; OS constraints applied.
4. `<storeUserId>` as a whole segment becomes a wildcard.
5. Over-broad `base` folders refused (found by a test: a shortcut at `/g.exe` made the whole disk its base).

## Measurements (development laptop, Windows, Python 3.14)

- 53,541 manifest entries, 0 skipped, 15,082 games with save data, 1,129 aliases.
- Parse about 9 s; index build 22 s with memory tracing; peak traced memory 30 MB; index 5.6 MB; index load 0.24 s.
- 96.8% of Proton save paths resolve to logical roots. The rest are skipped with a reason.
- Spot check of ten well-known titles typed as shortcut names: nine matched (including a "Game of the Year Edition" name and different capitalisation); "Sonic Mania Plus" needs a manual pick ("Sonic Mania" is offered first).

The 120 second and 400 MB limits are measured on device in the checklist.

## Test results

Local, Windows, Python 3.14.3:

- New tests by name: `test_yamlsubset.py`, `test_manifest.py`, `test_resolve.py`, `test_gameconfig.py`; changed: `test_app.py`, `test_scripts.py`, `test_discovery_games.py`, `test_net.py`. All passed; skips are `posix` symlink tests.
- `pnpm run check`: see below.
- Mutation checks: 14 guards broken one at a time. 13 caught on Windows (traversal, unknown placeholders, broad base, default exclusions, case-insensitive matching, OS constraints, tag filter, ambiguous matches, empty-index protection, manual match validation, unsupported YAML, custom path validation, file-picker confinement). The scan's symlink escape check is guarded by a `posix` test that cannot run on Windows; it runs on the device (checklist step 1).

## Known gaps

- No device runs yet: parse time and memory on the handheld are unmeasured.
- Registry entries are indexed but not resolved (slice 11).
- Per-game settings are device-local until slice 7.
- Games with `base` inside `drive_c` directly (exe in `drive_c` itself) get no `base` root because of the safety rule.

## On-device checklist

1. `pnpm run test:device`: expect all `posix` tests to pass, including the symlink escape tests.
2. Install this build (once released as v0.4.0, update inside Keepsake).
3. Games, "Update manifest". Expect "Manifest is up to date" and a game count of about 15,000. Then Diagnostics, Export, and send me `manifest.parseSeconds` and `manifest.peakRssMb`. If either is over 120 s or 400 MB, I will stop and propose an alternative, as the build prompt requires.
4. For ten of your games on each device: open the game, check the match, press "Refresh preview", and confirm the files listed are your saves and the relative paths are the same on both devices.
5. Try "Change match" on one game, "Include config files" on another, add a custom folder with the file picker, and add an exclusion. Confirm the preview changes.
