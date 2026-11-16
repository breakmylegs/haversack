# Module: Advisor

Read-only tuning recommendations for the game being played or selected.

| | |
|---|---|
| Flag default | On |
| Spec | `docs/build-prompt-v2.md` sections 4 (P16, P18), 6.2, 8.1 and 9; research sections 6.3 and 6.4 |
| ADRs | 0012, 0013, 0014, 0019, 0028 |
| Code | `py_modules/keepsake/advisor/`, `src/pages/AdvisorPage.tsx`, `src/pages/AdvisorQam.tsx`. Device profiles in Core: `py_modules/keepsake/devices.py` |
| Origin | Port of Peter's Tuning Advisor, subject to the audit in `docs/advisor-port-audit.md` |
| Slices | 14 (Advisor I), 15 (Advisor II, minor release) |

## What it does

- Detects the device and selects a profile (Legion Go and Legion Go 2 at minimum, extensible). Profiles record panel resolution, refresh range, VRR, APU, GPU, RAM, USB4 and Wi-Fi generation, and live in Core.
- Detects the power and tuning stack (TDP tools, lsfg-vk, OptiScaler and others) read-only, with manual override.
- Shows recommendations for the running game (from the lifecycle bus) or any selected game: power in the selected tool's terms, display and frame cap, scaling and upscaler (in-game upscaler first, then the gamescope filter), frame generation (lsfg-vk only where the base frame rate supports it), in-game preset, Proton version and launch options.
- Maps non-Steam shortcuts to a Steam app ID through the Ludusavi manifest's Steam ID, with manual override.
- Proton signal order: the tool configured and working on the paired peer for the same `gameKey` (when Replication is on), then data sources, then the latest installed GE-Proton for non-Steam titles.
- Every recommendation shows its source and confidence. Launch options offer "Copy" only.
- Optional AI explanations with the user's own Anthropic, OpenAI or Gemini key, with an offline rule-based fallback.

## What it writes

Nothing outside its own cache and settings in Keepsake's folders (P16). Never Steam settings, other plugins' files, game files, prefixes or config files. Never the Lossless Scaling DLL. A test guards this.

## Network (each only when its source or provider is enabled)

| Endpoint | Use |
|---|---|
| `deckverified.games` | Deck Verified community reports (GPL-3.0 data, shown with attribution and a link per report) |
| Steam store endpoints | Exact hosts to verify in slice 14 |
| `www.pcgamingwiki.com` | Cargo API with the user's bot password (CC BY-NC-SA, attributed) |
| `raw.githubusercontent.com` | Are We Anti-Cheat Yet `games.json` (MIT) |
| GitHub release asset downloads | ProtonDB index (ODbL), if adopted (c0-report Q4) |
| `www.protondb.com` | Allowlisted by the spec. Not used unless Peter decides otherwise (Q4) |
| `api.anthropic.com`, `api.openai.com`, `generativelanguage.googleapis.com` | Only for the configured provider, from a button press |

## Data source credits

Deck Verified by DeckSettings (GPL-3.0 report data). ProtonDB data under the ODbL 1.0 and DbCL 1.0. PCGamingWiki under CC BY-NC-SA. Anti-cheat status from Are We Anti-Cheat Yet, MIT licence, copyright Starz0r and Curve. SteamDeckHQ and ShareDeck are link-out only.

## AI payloads (P18)

Game title, hardware profile, installed tool versions and the settings being discussed. Never save data, paths, account identifiers, device names or tokens. A test inspects every payload.

## Health checks

Device detected or generic, each source reachable or cached, AI provider key present and last error.
