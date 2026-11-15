# ADR-0019: Advisor read-only rule and AI policy

- Status: proposed (slice C0, awaiting Peter's approval)
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 4 (P16, P18), 6.2 and 8.1; Tuning Advisor brief sections 8.1, 8.5 and 8.11

## Context

Advisor recommends power, display, upscaling, frame generation and compatibility settings. It draws on community data sources and, optionally, AI providers with the user's own key. Tuning Advisor already ran under a strict read-only rule with a build guard against Steam setters, and sent AI providers only the game, device profile, stack and report excerpts.

## Decision

1. **Read-only (P16).** Advisor never writes Steam settings, other plugins' files, game files or config files. It displays recommendations and can copy text to the clipboard. Launch option suggestions offer "Copy" only. Any "apply" capability is an escalation item. A test guards the Advisor sources against `SteamClient` setters and against writes outside its own cache, as Tuning Advisor's `check_readonly.py` did.
2. **AI is opt-in (P18).** AI calls happen only with a user-supplied key and an explicit per-provider opt-in, from a button press. Providers: Anthropic (`api.anthropic.com`), OpenAI (`api.openai.com`) and Google Gemini (`generativelanguage.googleapis.com`), each called only when configured. No SDKs: stdlib HTTP through Keepsake's allowlisted `net`.
3. **Minimal payloads.** Requests contain only the game title, hardware profile, installed tool versions and the settings being discussed. Never save data, paths, account identifiers, device names or tokens. Tuning Advisor also sent the app ID and community report excerpts. Under P18 the app ID is a game identifier and stays out unless Peter allows it (c0-report Q5). Report excerpts count as "settings being discussed" only after paths and user names are stripped. A test inspects every provider payload.
4. **Display-only output.** AI output is labelled "AI generated, unverified", validated against the device profile (clamped or discarded fields shown), and can never trigger an action. An offline rule-based fallback always works.
5. **Keys.** Stored with mode `0600`, never sent to the frontend, logs, diagnostics or events. Redaction tests cover them (T50).
6. **Data sources.** Each source is shown with its name, link, date and confidence. Link-out-only sources (SteamDeckHQ, ShareDeck) are never scraped or cached. Licence terms per source follow ADR-0013.

## Consequences

- Advisor adds network endpoints only under its own module flag and per-source toggles (spec section 6.2). Exact hosts for the Steam store and Deck Verified are verified in slice 14.
- The Tuning Advisor owner override "AI replaces the cards, with a way back" is a UI choice that P18 allows. It is carried into slice 15 unless Peter says otherwise.
