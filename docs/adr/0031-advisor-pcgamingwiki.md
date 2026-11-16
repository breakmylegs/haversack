# ADR-0031: PCGamingWiki as an optional Advisor source

- Status: accepted (decided under Peter's delegation, completing ADR-0029 point 7)
- Date: 16 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` section 8.1 and research 6.4 ("PCGamingWiki for upscaler and frame generation support"); `docs/advisor-port-audit.md` section 4; Tuning Advisor's `pcgw.py` (ADR-0013)

## Decision

1. **Optional, off by default.** "PCGamingWiki (optional)" on the Advisor page turns it on. Until the user saves their own PCGamingWiki bot login, nothing is sent.
   - Since August 2026 the Cargo API needs a bot password from Special:BotPasswords, with the Cargo grant.
   - The login is a backend secret (`pcgw.json`, mode 0600). Only "set or not" reaches the page.
2. **What it adds.**
   - The game's listed upscalers and frame generation, with a link to the page and the CC BY-NC-SA credit.
   - A flag on any report recommending an upscaler the wiki does not list for that game.
   - Each game costs two Cargo queries, then the answer is cached for 7 days. A stale copy is kept when the wiki cannot be reached or rate-limits (a 429 blocks the IP for a minute).
3. **Ported onto Keepsake's `net`.**
   - Requests go to one host (`www.pcgamingwiki.com`, already allowlisted, used only while the source is on), with no redirects.
   - Session cookies are held in memory for the client only.
   - `net.request` now keeps repeated `Set-Cookie` headers, joined by newlines, so a session can be held. Every other header is unchanged.
   - Game names containing quotes or backslashes are never put in a query.
4. **ProtonDB index stays in the backlog** (c0-report Q4, option a). It needs its own release-asset pipeline under the ODbL.

## Consequences

- PCGamingWiki needs a one-off account and bot password from the user. Advice works fully without it.
