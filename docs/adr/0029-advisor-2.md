# ADR-0029: Advisor II implementation

- Status: accepted (slice 15, decided under Peter's delegation; c0-report Q3, Q4 and Q5 taken as recommended)
- Date: 16 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 4 (P16, P18), 6.2 and 8.1; research sections 6.3 and 6.4; ADR-0019, ADR-0028

## Decision

1. **Proton, in the spec's signal order.**
   - First, what works on the paired peer for the same game. Replication is not built yet, so the page says this is not checked.
   - Then the top community report's tool.
   - Then, for non-Steam titles only, the newest GE-Proton installed in a Steam root's `compatibilitytools.d`, sorted by number (`GE-Proton10-10` before `GE-Proton9-27`). This is read-only.
   - A Steam game with no report keeps Steam's own choice.
   - The page says which signal gave the advice. It shows the game's current tool (read by discovery from `config.vdf`) and where to change it.
   - GE-Proton's install hint is shown only when it is not installed.
2. **Launch options.** Tuning Advisor's parser, merge and flags are ported:
   - shell operators, unknown wrappers, a missing `%command%`, and FSR 4 variables, which are removed.
   - Each report's options are shown with a merge against the game's current options.
   - Both have Copy buttons only (P16). Keepsake never sets them.
3. **Current values.** Tuning Advisor's read-only readers for SimpleDeckyTDP, PowerControl, LeGoTDP, Legion Go 2 Companion and the lsfg-vk `conf.toml` (version 2 only) are ported. Each respects the tool's own switches, for example per-game profiles being off.
4. **Frame generation (research 6.4).**
   - The game's own frame generation comes first.
   - lsfg-vk is suggested only when it is installed and selected, and only from a base of 40 fps or more.
   - Below that the advice says no, and why. A report that uses lsfg-vk from under 40 fps is flagged.
5. **Upscaling order (spec 8.1).** The game's own upscaler is listed before Steam's scaling filter. General advice that lowers the resolution says to try the game's upscaler first.
6. **AI (P18, ADR-0019; Q3 and Q5).**
   - Opt-in per provider (Anthropic, OpenAI, Google Gemini) with the user's own key, from a button press only, with a daily limit (default 20).
   - Results are labelled "AI generated, unverified" and shown beside the reports, as Tuning Advisor did (Q3).
   - The payload is the game's **title only** (no app ID, Q5), the hardware profile, the selected tools and the settings from reports, each labelled by how close its device is to yours. Report text, the reporters' device names, dates and links are never sent. A test inspects the payload for each of these.
   - Keys are backend secrets (`ai-<provider>.json`, mode 0600, never returned to the page or logged).
   - Each provider is called on its own host only, with no redirects.
   - Replies are checked locally: wrong types, TDP outside the device's range, impossible frame rates and FSR 4 are discarded and listed.
7. **Deferred.**
   - PCGamingWiki (optional, needs the user's bot password) and the ProtonDB dump index (Q4 option a, which needs a release-asset pipeline) are not in the plan's slice 15 row. They go to the backlog as their own item.
   - `www.protondb.com` is not called (Q4).

## Consequences

- The Proton advice gains the peer signal when Replication (slices 17 to 20) lands. The page already says it is not checked yet.
- Recorded provider reply shapes come from Tuning Advisor's register and are unverified from Keepsake until a real key is tried (A148).
