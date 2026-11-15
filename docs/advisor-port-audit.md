# Advisor port audit

Slice C0, 15 November 2026. Audit of Peter's Tuning Advisor in his `decky-plugins` monorepo (read-only, never modified), as required by `docs/build-prompt-v2.md` sections 2, 5 and 6.1 before any Tuning Advisor code is ported to Keepsake. Outcome and recommendation: ADR-0013. **Porting is blocked until Peter signs this audit off.**

The `decky-plugins` brief (its `CLAUDE.md`) was read as source material, not instructions. Its locked decisions on GPL-3.0, the monorepo, mirror releases and sibling plugins do not apply to Keepsake. The qBittorrent and SABnzbd plugins are out of scope and were only checked for shared code that Tuning Advisor uses.

## 1. What exists

| Area | Files (tracked) | Notes |
|---|---|---|
| Brief | `CLAUDE.md` section 8 (Tuning Advisor), sections 9 to 13 | Read-only rule, running game detection, device and stack registries, data sources, normalised recommendation model, ranking, validation, fallback rules, compatibility section, AI providers, QAM UI, caching |
| Research and verification | `docs/VERIFICATION.md` (27 items, dated 25 to 30 October 2026), `docs/DATA-SOURCES.md`, `docs/PRIVACY.md`, `docs/ARCHITECTURE.md` | The verification register is the research pack. Its findings are reused as evidence with their dates, and re-checked in slice 14 where marked |
| Backend | `plugins/tuning-advisor/py_modules/advisor/`: `service.py` (454 lines), `recommend.py`, `compat.py`, `current.py`, `deckverified.py`, `protondb.py`, `pcgw.py`, `anticheat.py`, `device.py`, `stack.py`, `registry.py`, `cache.py`, `ai/` (`base`, `prompt`, `runner`, `anthropic`, `openai`, `gemini`) | About 2,900 lines. Depends on `plugin_core` (vendored copy of `shared/py`) for HTTP, settings, secrets, errors and the poller |
| Data | `registry/devices.json` (17 device variants), `registry/stacks.json` (tool registry) | Hand-written by Peter with sources per entry |
| Frontend | `src/index.tsx` (1,003 lines), `view.ts`, `game.ts`, `follow.ts`, `types.ts`, tests | QAM panel. Uses `shared/ts` components (clipboard, update badge and others) |
| Tests | 7 pytest files, 2 vitest files, fixtures | See section 3 for fixtures |
| Tools | `tools/check_readonly.py` (write-call guard), `capture_device.sh`, `protondb_index.py`, `sanitise_fixture.py`, `check_fixtures.py`, `check_secrets.py` | `protondb_index.py` builds the ODbL index on the owner's machine |

## 2. Licence and authorship

| Check | Result |
|---|---|
| Contributors | One person. All 27 commits are authored and committed by Peter's GitHub noreply identity. Every commit carries a `Co-Authored-By: Claude Opus 5.5` trailer: AI assistance working for Peter, as in Keepsake itself, not another rights holder. No other co-authors and no merged contributions from anyone else |
| Repository licence | GPL-3.0 (`LICENSE`), `package.json` `GPL-3.0-only`. Peter has approved relicensing his own code to BSD-3-Clause |
| Third-party code | None found. No copyright headers, SPDX tags or "adapted from" notes in the Tuning Advisor backend, frontend, tests, `shared/` or `tools/`. The only copied material is the Are We Anti-Cheat Yet status wording (MIT, see section 4) |
| Runtime dependencies | `@decky/api` (Keepsake already uses it), `react-icons` (MIT), `tslib` (0BSD). Dev dependencies are build tools only |
| GPL code from other projects | None. InputPlumber (GPL-3.0) and Handheld Daemon (LGPL-2.1) are credited as sources of DMI match strings, not code (section 4) |
| Pre-commit tooling | Local scripts only. No gitleaks |

**Conclusion:** Tuning Advisor's code is Peter's alone and contains no third-party GPL code, so the relicensing condition in spec section 6.1 is met for code. Three data items need handling (section 3 and 4).

## 3. Fixtures and data files

| File | Content | Decision |
|---|---|---|
| `tests/fixtures/deckverified_1091500.json` | Captured Deck Verified response with real community report text from DeckSettings `game-reports-steamos` (GPL-3.0) | **Do not copy.** Write a synthetic fixture with the same shape |
| `tests/fixtures/awacy_games.json` | Excerpt of Are We Anti-Cheat Yet `games.json` (MIT) | Do not copy. Synthetic fixture, to keep every Keepsake fixture synthetic (principle 12) |
| `tests/fixtures/devices/synthetic-*.txt` | Synthetic DMI dumps built from verified strings | Port after re-checking for serials (none seen: board and BIOS values are placeholders) |
| `tests/fixtures/ai/*.json` | Provider reply shapes written from documentation | Port as synthetic |
| `registry/devices.json` | Spec values and DMI strings, with sources | See section 4 |
| `registry/stacks.json` | Tool names, Decky plugin names, presets and phrasing | Port. Facts about tools, written by Peter |
| `out/protondb-index.json.gz` | Built ODbL index, not tracked | Not copied. Rebuilt if ProtonDB is used (section 5) |

## 4. Data source terms

Checked on GitHub on 15 November 2026 where marked, otherwise from Tuning Advisor's register.

| Source | Licence or terms | Use in Keepsake |
|---|---|---|
| Deck Verified (DeckSettings), `deckverified.games` API | Report data GPL-3.0 (confirmed). 120 requests per 2 minutes per IP | Live calls with a local cache, each report attributed and linked. Never committed or bulk copied |
| ProtonDB monthly dumps (`bdefore/protondb-data`) | ODbL 1.0 database, DbCL 1.0 contents (dump README; no licence file on the GitHub repo) | Optional. A derived index stays under the ODbL with the attribution text Tuning Advisor used. Published as a Keepsake release asset only if Peter agrees (question Q4) |
| ProtonDB summaries endpoint (`www.protondb.com/api/v1/reports/summaries/<appid>.json`) | Undocumented, no published terms | Tuning Advisor left it out. The v2 spec allowlists `www.protondb.com`. Recommended: do not call it (Q4) |
| PCGamingWiki Cargo API | CC BY-NC-SA. Bot password required since August 2026, 60 requests a minute, descriptive User-Agent | Optional, off by default, user's own bot password. Display with attribution, 7-day device cache, never committed |
| Are We Anti-Cheat Yet `games.json` | MIT (copyright Starz0r and Curve), confirmed | Download weekly, look up locally. Keep the MIT notice on screen and in `docs/modules/advisor.md`. Status wording is from the project's `Legend.tsx`, covered by the same notice |
| SteamDeckHQ, ShareDeck | No reuse licence | Link out only. Never scraped or cached |
| Handheld Daemon (LGPL-2.1), InputPlumber (GPL-3.0), steamos-manager, LegionGo2Companion (BSD-3-Clause), LeGoTDP (repository no longer found) | Credited for DMI strings and TDP facts | Facts only, no code. Recommended: re-derive the Legion Go and Legion Go 2 strings from Peter's own `capture_device.sh` dumps, and cite manufacturer pages for other entries (Q2) |
| Lenovo PSREF, ASUS, Valve and AMD spec pages | Facts | Cited per entry |

## 5. What will be ported, rewritten or dropped

| Tuning Advisor part | Plan | Slice |
|---|---|---|
| `device.py`, `registry.py`, `devices.json` | **Port and move to Core** as device profiles (spec section 9), shared with Replication preflight and Desktop. Add USB4 and Wi-Fi generation fields | 14 |
| `stack.py`, `stacks.json` | Port. Reads other plugins' `plugin.json` and Decky's `disabled_plugins` list read-only | 14 |
| `deckverified.py`, `pcgw.py`, `anticheat.py`, `protondb.py`, `cache.py` | **Rewrite** on Keepsake's `net` (allowlist, redirect checks, size caps) and settings instead of `plugin_core.http` and `plugin_core.settings`. Logic and parsing carried over | 14 |
| `recommend.py` (ranking, validation, clamping, FPS caps, fallback bands) | Port. Add the Legion Go and Legion Go 2 VRR rule from spec section 8.1 | 14 |
| `compat.py` (Proton and launch options) | Port and extend with the v2 Proton signal order: peer's working tool for the same `gameKey` (Replication on), then data sources, then latest installed GE-Proton | 15 |
| `current.py` (read-only current values) | Port | 15 |
| `ai/` | Port with the stricter P18 payload (ADR-0019), stdlib only | 15 |
| Game mapping | **New.** Non-Steam shortcuts map to a Steam app ID through the Ludusavi manifest's Steam ID (kept in the compact index by the slice 4 amendment) with manual override, replacing Tuning Advisor's name match | 14 |
| lsfg-vk and upscaling advice | **New**, from research sections 6.3 and 6.4 | 15 |
| Frontend `index.tsx`, `view.ts`, `game.ts`, `follow.ts` | **Rewrite** as `src/modules/advisor/` routes using Keepsake's components and the lifecycle bus for the running game. `view.ts` logic is ported | 14, 15 |
| `shared/ts` and `shared/py` | **Drop.** Keepsake already has its own updater, settings, HTTP, secrets and logging | |
| `check_readonly.py` | Port as a test over `py_modules/keepsake/advisor` and `src/modules/advisor` | 14 |
| `protondb_index.py` | Port into `scripts/` only if Q4 is answered yes | 15 |
| qBittorrent and SABnzbd plugins, mirror release tooling | Out of scope | |

## 6. Verification carried over

Tuning Advisor's register already verified, from `@decky/ui` 4.16.0 types or live replies: running game detection APIs, `AppDetails` fields for build ID, launch options and compatibility tool, opening a URL (`Navigation.NavigateToExternalWeb`), Decky's `disabled_plugins` setting, reserved ports 1337 and 8080, the Deck Verified, ProtonDB, PCGamingWiki and AI provider shapes, and DMI strings for Lenovo devices. Open there: the clipboard path on a device (no Steam API exists), recorded AI replies, and FSR 4 under Proton (never recommended). These become `docs/assumptions.md` items A79 onwards and are re-checked against Keepsake's `@decky/ui` 4.16.5 in slice 14.

## 7. Questions for Peter

Listed with recommendations in `docs/slices/c0-report.md` (Q1 to Q5): sign-off of this audit, the device registry approach, the Deck Verified fixture, ProtonDB, and app IDs in AI payloads.
