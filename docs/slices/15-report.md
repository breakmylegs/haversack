# Slice 15 report: Advisor II

Branch `slice/15-advisor-2`, stacked on `slice/14-advisor-1` (#25). v2 spec slice 15. Decisions: ADR-0029. c0-report Q3 and Q5 were taken as recommended. Q4's ProtonDB index is deferred to the backlog together with PCGamingWiki: neither is in the plan's slice 15 row, and the index needs its own release-asset pipeline.

## What changed

- `advisor/compat.py`:
  - Proton advice in the spec's signal order (the peer once Replication exists, then reports, then the newest installed GE-Proton for non-Steam titles, sorted by number);
  - launch option parsing, merging and flags, ported from Tuning Advisor.
- `advisor/current.py`: read-only current values from SimpleDeckyTDP, PowerControl, LeGoTDP, Legion Go 2 Companion and lsfg-vk, ported.
- `advisor/recommend.py`:
  - frame generation only from a base of 40 fps, with the game's own first;
  - the game's own upscaler listed before Steam's filter;
  - a flag on reports that use lsfg-vk from a low base.
- `advisor/ai.py`: Anthropic, OpenAI and Gemini on Keepsake's `net`, one host each with no redirects; the P18 payload; reply checking; a daily-use counter. Ported from Tuning Advisor, with a stricter payload.
- `advisor/service.py`: the new settings (`aiProvider`, `aiModel`, `aiDailyCap`), the game's current launch options and tool from discovery, the Proton and current values in the view, and `generate_ai` and `list_models`.
- `backends.py`: AI keys as `CredentialStore` secrets (mode 0600, never returned to the page).
- App and frontend:
  - the callables `advisor_ai_models` and `advisor_ai_generate`;
  - Advisor page cards for Proton, current values, launch options with Copy and Copy combined, and AI with provider, key, model and an "Ask" button.
- Docs:
  - ADR-0029;
  - threat model: T49 and T50 in place, new T83 and T84;
  - assumptions A148 to A151;
  - CHANGELOG and the plan backlog.

## Acceptance (v2 spec slice 15)

| Requirement | How it is shown |
|---|---|
| AI payloads hold only P18 fields | `test_ai_payload_holds_only_what_p18_allows`. The keys are exactly game title, hardware, tools and settings discussed. None of these appear: the app ID, `/home` paths, a user name, the reporter's device name, a link, a date or report text. `test_ai_advice_from_a_button_press_with_checks` also checks the text actually sent to the provider. |
| Offline rule-based advice | Everything except AI works with no provider. AI is off by default and the rest of the page does not depend on it. The slice 14 offline tests still pass. |

## Tests

- New: `tests/test_advisor_2.py`, 11 tests, all synthetic.
- Re-run because they cover touched code: `test_advisor` (one expectation updated for the new mapping fields), `test_backends`, `test_modules`, `test_lifecycle` and `test_app`. 86 passed, 1 skipped (`posix`).
- **Read-only:** a session with Proton, current values and AI leaves every file outside the Advisor's own settings and cache unchanged.
- **Mutation checks:** 17 guards broken one at a time, all caught.
  - Three were caught only after new tests: a tool's per-game switch, an older lsfg-vk format, and the AI host lock.
  - One error of mine was found and fixed. In the second round a test was failing for an unrelated reason, so "caught" meant nothing. I fixed the test and re-checked those mutations against a passing baseline first.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan).

## Known gaps

- PCGamingWiki and the ProtonDB index: backlog (ADR-0029).
- The Proton peer signal waits for Replication.
- Provider reply shapes are unverified from Keepsake until a real key is used (A148).
- The clipboard in Gaming Mode is unverified (A142).

## On-device checklist

1. A non-Steam game with no report: Advisor, Proton names the newest GE-Proton you have installed and shows the one the shortcut uses now.
2. A Steam game whose report has launch options: "Copy launch options" and "Copy combined" copy text, and nothing changes in Steam.
3. With lsfg-vk installed, choose a heavy workload. Frame generation says not advised below 40 fps. A light workload offers it.
4. With SimpleDeckyTDP or Legion Go 2 Companion, Advisor shows "Your ... setting" with the game's TDP.
5. Optional, with your own key:
   - choose a provider, save the key, press Load models and pick one;
   - press Ask. Advice appears labelled "AI generated, unverified", and the daily count goes up.
6. Run `pnpm run test:device`.
