# ADR-0013: Licence and Tuning Advisor audit outcome

- Status: accepted. Peter signed off the audit on 16 November 2026. The other C0 questions took their recommended answers: Q2 manufacturer sources only, Q4 the ProtonDB dump index, Q5 no app ID in AI requests. See ADR-0028.
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 2, 5 and 6.1; `docs/advisor-port-audit.md`

## Context

The Advisor module ports Peter's Tuning Advisor plugin, which lives in his `decky-plugins` monorepo under GPL-3.0. Keepsake is BSD-3-Clause. Peter has approved relicensing his own Tuning Advisor code to BSD-3-Clause, on condition that an audit finds no third-party GPL code or data and no contributor other than him. Until he signs the audit off, porting any of that code is an escalation item.

## Findings (detail in `docs/advisor-port-audit.md`)

1. **Authorship.** All 27 commits in the monorepo have one author and committer, Peter's GitHub noreply identity. Each carries a Claude co-author trailer (AI assistance for Peter, as in Keepsake). No other human contributor.
2. **Code.** No third-party code found in the Tuning Advisor backend, frontend, tests, `shared/` or `tools/`: no copyright headers, SPDX tags or "adapted from" notes other than the MIT notice for Are We Anti-Cheat Yet status wording. Runtime dependencies are `@decky/api` and `react-icons` (MIT) and `tslib` (0BSD), all compatible with BSD-3-Clause.
3. **Data that cannot be relicensed.** The test fixture `deckverified_1091500.json` is a captured response of community reports from DeckSettings `game-reports-steamos` (GPL-3.0, confirmed on GitHub), including real report text. It must not be copied. Keepsake uses synthetic fixtures instead (principle 12 requires that anyway).
4. **Data with share-alike or attribution terms.**
   - ProtonDB dumps are ODbL 1.0 (database) and DbCL 1.0 (contents). A derived index stays under the ODbL and needs attribution. It is separate data, not code, so it does not affect the code licence.
   - PCGamingWiki content is CC BY-NC-SA. Keepsake only displays it live with attribution and a link, and caches it on the device. It is never committed or redistributed.
   - Are We Anti-Cheat Yet `games.json` and its status wording are MIT. Keep the notice on screen and in the module document.
5. **Device registry facts.** `registry/devices.json` was written by Peter from manufacturer spec pages, with DMI match strings credited to Handheld Daemon (LGPL-2.1), InputPlumber (GPL-3.0), steamos-manager and LegionGo2Companion (BSD-3-Clause). The entries are short factual identifiers (vendor and product strings) and spec values, not code. Facts are not normally protected by copyright, but a GPL project is credited as a source, so this is recorded as a decision rather than assumed.

## Decision (recommended, pending sign-off)

1. Relicense and port Peter's own Tuning Advisor code to BSD-3-Clause in slices 14 and 15, rewriting it to Keepsake's structure (Core services, module registry, Keepsake's `net`, settings and logging) rather than vendoring `plugin_core`.
2. Do not copy any Tuning Advisor fixture that holds third-party content. Write synthetic fixtures.
3. Device registry: ship the Legion Go and Legion Go 2 profiles from Peter's own `capture_device.sh` dumps and the Lenovo PSREF spec sheets. Keep the other handheld entries as facts cited to manufacturer pages, re-verified rather than copied from InputPlumber or Handheld Daemon files. Credit sources per entry as Tuning Advisor did.
4. Keep data under its own terms: the ProtonDB index ships under the ODbL with attribution if it is used at all (see ADR-0019 and the network question in `docs/advisor-port-audit.md`). PCGamingWiki and Deck Verified data are shown live with attribution and never committed.
5. Record each data source and its terms in `docs/modules/advisor.md` and in the Advisor screen, as Tuning Advisor's `DATA-SOURCES.md` did.

## Consequences

- Porting stays blocked until Peter signs off this ADR and the audit (escalation rule, spec section 5).
- The Tuning Advisor plugin itself is unaffected. Its GPL-3.0 copy remains in `decky-plugins`, which Keepsake never modifies.
- The `README.md` licence section gains the data source credits when Advisor ships.
