# R18 report: library badges and streaming-tile artwork (v0.39.0)

The last item in Peter's queue of 21 November 2026. The decisions are in ADR-0081.

## What changed

- **The library badge** (`src/libraryBadges.tsx`): a defensive route patch on `/library/app/:appid`.
  - It adds a "Keepsake · …" label from `library_badge(appid)`.
  - Its states are in step, newer elsewhere, conflict, waiting, quarantined, not synced, or streams from a device.
  - It is wrapped in an ErrorBoundary. If Steam's page is not shaped as expected, it does nothing.
  - A new setting, **Badges in Steam's library** (on by default), sits in Settings, General.
- **Artwork for streaming tiles, in the Installer module:**
  - the list comes from Steam's streaming report, for non-Steam app IDs only (`installer_stream_tiles`);
  - SteamGridDB search (`installer_stream_art_search`);
  - after the user picks the game, the top images are queued as `set-artwork` operations for the tile (`installer_stream_art_apply` and `Installer.queue_stream_art`).

  It shows as a new section on the Install page.

## Not done, and why

- **The badge's look and position on Steam's page are unverified** (A223). If Steam's structure differs, the badge simply does not appear.
- **Artwork for Steam games' streaming tiles is not added.** Steam already shows store artwork for those.

## Tests

- **New:** `tests/test_badges_and_stream_art.py`, 7 tests:
  - badges for saves and streaming, including off, unknown and switched off;
  - a conflict on the badge;
  - a newer save elsewhere on the badge;
  - only non-Steam streaming tiles are offered;
  - stream art queued for Steam, and Steam app IDs refused;
  - the app refuses an app that is not a streaming tile;
  - the setting is checked.
- **Regression:** these pass, with 2 skipped on Windows:
  - `tests/test_installer.py`
  - the remote copies tests
  - `tests/test_settings.py`
- **Mutation tests:** 8 mutations. One survived (the "newer" badge), which led to a new test. Now all 8 are caught.

## Threat model and assumptions

- **Threat model:** T146.
- **Assumptions:** A223 (unverified).

## On-device checklist

`docs/device-run.md` part 4, step 29.
