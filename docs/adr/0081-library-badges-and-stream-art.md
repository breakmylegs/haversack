# ADR-0081: Keepsake's badge in Steam's library, and artwork for streaming tiles

- Status: accepted (R18 in Peter's queue of 21 November 2026, decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

R18 has two parts, the last item in the queue:

- **Library badges:** a game's Keepsake state, shown in Steam's own library.
- **Artwork for streaming tiles:** Steam Remote Play lists non-Steam games installed on another device (ADR-0064) with no artwork.

Two facts shape the design:

- **Steam's library pages are Steam's.** Decky's `routerHook.addPatch` with `@decky/ui`'s `afterPatch`, `findInReactTree` and `appDetailsClasses` is how plugins add to them. These names are verified in this repository's `node_modules`. Steam's page structure is not a stable interface, though.
- **Setting a tile's artwork is a Steam write** (principle 15). The Installer already does this for its own shortcuts: it stages SteamGridDB images with the user's key (ADR-0027) and sets them through the Steam Operations Executor (ADR-0015).

## Decision

1. **A badge on each game's page in Steam's library** (`src/libraryBadges.tsx`). It is a small "Keepsake · …" label at the top right, with one of:
   - "Saves: in step";
   - "Saves: newer on Legion Go 2";
   - "Saves: conflict, open Keepsake";
   - "Saves: waiting to upload";
   - "Saves: not synced by Keepsake";
   - "Streams from Legion Go 2", for a streaming tile.

   The text comes from the backend's `library_badge(appid)`, which reads Saves' state and Steam's streaming report.
2. **The patch is defensive.**
   - It only adds an element.
   - It does nothing if the page does not look as expected.
   - It catches every error and leaves Steam's page as Steam drew it.
   - The badge is wrapped in `ErrorBoundary` and ignores pointer input.
3. **Badges can be switched off.** The setting is **Badges in Steam's library** (`libraryBadges`, on by default), under Settings, General. It hides the badge without a restart.
4. **Artwork for streaming tiles lives in the Installer module** (P13). The Installer already owns SteamGridDB and the artwork route.
   - Install lists each streaming tile for a non-Steam game, with the device it streams from.
   - **Find artwork** searches SteamGridDB by the tile's name.
   - The user picks the game, and the top images are staged and queued as `set-artwork` operations for that tile's app ID, exactly as for an installed game.
   - Steam tiles are refused, because Steam's store artwork already covers them. So is anything that is not in Steam's streaming report.
5. **No new endpoint, scope or binary.** SteamGridDB and its image host are already approved (ADR-0027), with the user's own key.

## Consequences

- **Badge behaviour on a device is unverified** (A223). If Steam's page changes shape, the badge simply does not appear. Device run step 29 checks it.
- **Threat model:** T146.
- **Device run:** part 4, step 29.
