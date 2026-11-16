# Slice 14 report: Advisor I

Branch `slice/14-advisor-1`, based on `main` after v0.22.0. v2 spec slice 14, unblocked by Peter's sign-off of the licence audit on 16 November 2026. Decisions: ADR-0028. The other C0 questions took their recommended answers: Q2 here, Q4 and Q5 in slice 15.

## What changed

- **Core device profiles** (`keepsake/devices.py`, `keepsake/data/devices.json`).
  - Detection from DMI strings, the CPU and the GPU vendor. The most specific profile wins, with a generic fallback and a manual choice. Serial numbers are never read.
  - Ported from Tuning Advisor with manufacturer and Valve sources only (Q2).
  - New fields: USB4, Wi-Fi and "captured".
- **Advisor module** (`keepsake/advisor/`).
  - Tool detection and conflicts (`stack.py` and `data/stacks.json`, read-only).
  - Sources: Deck Verified (`deckverified.py`) and Are We Anti-Cheat Yet (`anticheat.py`), on Keepsake's `net`.
  - A 7-day cache (`cache.py`).
  - Ranking, validation and translation into the selected tool's words (`recommend.py`), plus device-aware general advice.
  - The service (`service.py`) has its own settings file, shortcut mapping and health checks.
- **App.**
  - Advisor is a real module with start, stop, health and a `game_started` listener that never blocks the launch gate.
  - Core publishes `game_started` for games Saves does not sync.
  - Shortcuts map to Steam app IDs through the manifest.
  - Callables: `advisor_view`, `advisor_select_game`, `advisor_refresh`, `advisor_redetect` and `advisor_settings`.
- **Frontend.**
  - An Advisor tab: device and workload choice, tools and conflicts, game choice, a Steam app ID for shortcuts, recommendations with source, confidence, flags, Copy for launch options and "Open the report", anti-cheat status and credits.
  - An Advisor section in the Quick Access Menu with the top advice for the running game.
- **Docs.**
  - ADR-0028; ADR-0013 accepted; the audit marked signed off.
  - Threat model: T53 in place, new T80 to T82.
  - Assumptions A142 to A147.
  - `THIRD_PARTY_NOTICES.md`: Are We Anti-Cheat Yet (MIT, copyright line read from its licence file) and Deck Verified.
  - CHANGELOG `[Unreleased]` and the module document.

## Acceptance (v2 spec slice 14)

| Requirement | How it is shown |
|---|---|
| Recommendations for a Steam game and a non-Steam shortcut | `test_advice_for_a_steam_game_and_shortcuts_writes_nothing_else`: a Steam game; a shortcut mapped through the manifest's Steam ID (high confidence); a shortcut looked up by name (low); a manual Steam app ID. `test_the_app_maps_a_shortcut_through_the_manifest_steam_id` covers the real mapping in the app. |
| Advice differs correctly between the two devices | `test_general_advice_differs_between_legion_go_and_legion_go_2`, for a medium game. Legion Go: 36 fps (divides 144 Hz), 1280x800 with Integer scaling, 15 W, no VRR line. Legion Go 2: 45 fps with VRR on, native 1920x1200, 16 W. `test_a_report_is_validated_against_each_device`: the same Legion Go 2 report is "your device, high" on the Go 2, and "same family, medium" on the Go, with the VRR and frame pacing flags. |
| Advisor writes nothing | Every file outside the Advisor's own settings and cache is unchanged after a session. A static check finds no write, delete, move or process calls in the Advisor code and no Steam calls in its pages. |

## Tests

- New: `tests/test_advisor.py`, 17 tests, all synthetic.
- Re-run because they cover touched code: `test_modules` (Advisor is now available), `test_lifecycle`, `test_installer`, `test_app`, `test_app_ux` and `test_manifest`. 113 passed, 1 skipped (`posix`), with the Advisor tests.
- **Offline proof:** the app-level tests run with the real network fetchers replaced by a refusal made no Advisor calls. A game outside the Games list is never looked up.
- **Mutation checks:** 18 guards broken one at a time, all caught. Three of them were caught only after new tests:
  - registry order for equally specific profiles;
  - "high" confidence needing a recent report;
  - the guard that stops a slow answer for an earlier game replacing the current one.
- **Bugs found while testing:**
  - a Deck Verified report whose `data` is not a mapping crashed `report_device`;
  - the game-started handler would have held the launch gate while fetching;
  - an unknown app ID would have been sent to Deck Verified.

  All three are fixed.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan).

## Known gaps

- The Proton signal order, lsfg-vk detection advice, upscaling order, PCGamingWiki, the ProtonDB index and AI are slice 15.
- The Legion Go and Legion Go 2 profiles wait for `capture_device.sh` dumps (Q2). Until then they show as detected but not checked on the device.
- The clipboard in Gaming Mode is unverified (A142). The text is always shown.
- The MSI Claw handhelds get the generic profile, because their only source was GPL code (Q2).

## On-device checklist

1. Run `capture_device.sh` once on each device and send the output, so the two Legion profiles can be marked checked.
2. On each device, open Keepsake, Advisor.
   - The device shows as Legion Go or Legion Go 2 with the right chip.
   - The tools list matches your installed TDP plugins.
3. Start a Steam game. The Quick Access Menu shows an Advisor section for it within a few seconds, and the game starts without extra delay.
4. Start a non-Steam shortcut of a game that is also on Steam. Advisor says "matched to its Steam app through the save manifest".
5. Compare the same game on both devices.
   - Legion Go: a frame cap that divides 144 and 1280x800 Integer, for a medium game.
   - Legion Go 2: VRR on and native resolution.
6. Press "Copy launch options" on a report that has them. Note whether the copy works (A142).
7. Press "Open the report". The GitHub report opens.
8. Run `pnpm run test:device`.
