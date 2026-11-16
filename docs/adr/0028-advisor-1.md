# ADR-0028: Advisor I implementation

- Status: accepted (slice 14, decided under Peter's delegation after his sign-off of the licence audit on 16 November 2026)
- Date: 16 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 4 (P13, P16), 8.1, 9 and 12 (slice 14); `docs/advisor-port-audit.md`; ADR-0013, ADR-0019; c0-report Q1 to Q5

## Decision

1. **Port under the signed-off audit.** Tuning Advisor's device detection, tool registry and stack detection, Deck Verified and Are We Anti-Cheat Yet parsing, cache, ranking, validation and translation are ported from Peter's `decky-plugins` repository (read-only, never modified) under BSD-3-Clause. Its HTTP, settings and secrets layer (`plugin_core`) is dropped. The sources are rewritten on Keepsake's `net`, with its host allowlist, size caps and no credentials. All test fixtures are new and synthetic: the captured Deck Verified and Are We Anti-Cheat Yet files are not copied (principle 12, audit section 3).
2. **Device profiles live in Core** (`keepsake/devices.py`, `keepsake/data/devices.json`), so Replication preflight and Desktop can share them (spec section 9). Each profile gains `usb4_ports`, `wifi` and `captured`.
3. **Q2, taken as recommended.**
   - Sources are manufacturer and Valve pages only. Every reference to InputPlumber, Handheld Daemon and the vanished LeGoTDP repository is removed.
   - The MSI Claw entries, whose match strings came only from InputPlumber, are dropped. Those devices get the generic profile.
   - The Legion Go and Legion Go 2 keep Lenovo's published machine types (83E1, and 83N0 and 83N1), and are marked `verified: false` and `captured: false` until Peter's `capture_device.sh` dumps confirm them.
   - The Legion Go 2's PSREF page link is not yet known, so it points at the PSREF index.
4. **Running game.**
   - Core now publishes `game_started` (with `gameKey` null) for games Saves does not sync, as it already did for `game_exited`. Advisor listens.
   - Saves publishes `game_started` inside its launch gate, while the game is paused. So the Advisor's handler only starts a background task and returns, and advice never delays a launch (tested with a fetch that blocks).
   - Any game in the Games list can also be chosen by hand.
5. **Shortcut to Steam app ID mapping.**
   - The shortcut's manifest entry, as Saves matches it, gives the Steam ID kept in the compact index (`s`; field verified in slice 4's `build_index`).
   - A manual override per shortcut is stored in the Advisor's own settings.
   - With neither, Deck Verified is asked by name and every recommendation is low confidence.
   - A game not in the Games list, even after one fresh scan, gets general advice only and nothing is looked up (fail closed).
6. **Device-aware general advice (Keepsake addition to the fallback).**
   - A VRR screen gets the target frame rate, kept within its VRR range. A screen without VRR gets a cap that divides its refresh rate evenly.
   - A 2560x1600 panel gets exactly half resolution, 1280x800, with integer scaling for medium and heavy games. A 1920x1200 panel stays native until heavy, then 1280x800 with FSR.
   - So the Legion Go gets 36 fps and 1280x800 Integer for a medium game, and the Legion Go 2 gets 45 fps with VRR at native 1920x1200. That is the spec's acceptance example.
7. **Sources in slice 14:** Deck Verified (on by default, 7-day cache, stale cache kept when offline) and Are We Anti-Cheat Yet (whole list weekly from `raw.githubusercontent.com`, so no game is ever named to anyone). PCGamingWiki, the ProtonDB index (Q4), the Proton signal order, lsfg-vk, upscaling advice and AI (Q5) are slice 15. `www.protondb.com` stays unused (Q4).
8. **Read-only (P16), tested twice.**
   - Every file outside the Advisor's own `advisor.json` and `advisor-cache` stays byte for byte unchanged through a full session.
   - A static check finds no process launching, deleting, moving or raw writes in `keepsake/advisor`.
   - The Advisor pages contain no `SteamClient` or Steam Operations calls.
   - Report links open only GitHub report pages. Launch options are offered through a Copy button only.
9. **Network in tests.** The Advisor's sources use the app's injected fetcher. A run of the app-level tests with the network refused made no Advisor calls.

## Consequences

- The Legion Go and Legion Go 2 profiles show "waiting for a check on this device" until the capture dumps arrive.
- The clipboard is unverified in Gaming Mode (A142). The text is always shown as well.
