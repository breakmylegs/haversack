# Slice C0 report: consolidation

Branch `slice/c0-consolidation`, stacked on `feat/cross-device-matching` (#8). Documentation only: no product code, tests, build files or dependencies changed.

## Gates and how they were handled

- The v2 session instructions run C0 after Peter confirms the merge of the slice in progress. Pull requests #4 to #8 are still open. Under Peter's standing instruction to continue the queue without asking, C0 was written now and stacked on #8, the same way slices 3 to 8 were stacked. Nothing merges without Peter.
- The inputs were expected in `C:\dev\keepsake-v2`, which does not exist on the development laptop. The spec, the session prompt and the research arrived as attachments in the session and were copied from there unchanged (Q7).
- `C:\dev\decky-plugins` was read only. Nothing in it was modified, staged or committed.

## What changed

| File | Content |
|---|---|
| `docs/build-prompt-v2.md` | The v2 spec, copied unchanged |
| `docs/research/replication-research.md` | The replication research, copied unchanged. Read with the supersession register in spec section 11 |
| `docs/adr/0012-module-model.md` | Core and modules, dependency rule, registry and flags, failure isolation, lifecycle bus, per-game lock, Saves owns save data, job scheduling |
| `docs/adr/0013-licence-and-advisor-audit.md` | Audit outcome and recommended porting rules |
| `docs/adr/0014-v2-principles-and-escalation.md` | Amended P7, P9, P10; new P13 to P19; escalation additions; v1 and v2 conflicts C1 to C8 |
| `docs/adr/0015-steam-write-policy.md` | `SteamClient`-only writes after a user action, store and read back, Steam Operations Executor |
| `docs/adr/0016-lan-exposure.md` | Listener off by default, narrow binding, paired peers only, pairing, firewall guidance |
| `docs/adr/0017-desktop-surface.md` | Loopback server, authentication, parity, tray |
| `docs/adr/0018-system-binary-register.md` | `udisksctl`, `systemd-inhibit`, `openssl`, `firewall-cmd`, `python3`, and the rules for using them |
| `docs/adr/0019-advisor-and-ai-policy.md` | Advisor read-only rule, AI opt-in, minimal payloads, keys, data sources |
| `docs/modules/` | One document per module: `saves.md`, `advisor.md`, `replication.md`, `installer.md`, `desktop.md` |
| `docs/advisor-port-audit.md` | Inventory of Tuning Advisor, licence and authorship findings, fixtures, data source terms, port or rewrite plan |
| `docs/plan.md` | Status of every slice and pull request, where each section 10 amendment lands, and the full queue to v2.0.0 |
| `docs/threat-model.md` | v2 threats as T42 to T55 (the spec's T16 to T29; v1 already uses T16 to T41) |
| `docs/assumptions.md` | A70 to A104: every unverified claim in the spec and research, with the slice that verifies it |
| `CLAUDE.md` | v2 summary, amended and new principles, escalation additions, network allowlist additions, links (143 lines) |
| `CHANGELOG.md` | Unreleased documentation note |

## Findings worth your attention

1. **Licence audit.** Tuning Advisor's code is yours alone: one author and committer on all 27 commits, each with a Claude co-author trailer, and no third-party code. The relicensing condition is met for code. One fixture holds GPL-3.0 community report text from DeckSettings and will not be copied. ProtonDB data stays under the ODbL.
2. **Source differs from the research.** `SteamClient.Apps.AddShortcut` in `@decky/ui` 4.16.5 takes `(appName, executablePath, directory, launchOptions)`. The research says it ignores start dir and launch options. The executor will still set every field and read it back (A70).
3. **Spec conflicts with Tuning Advisor's findings.** The spec allowlists `www.protondb.com`, but Tuning Advisor rejected that endpoint because it is undocumented with no published terms (Q4).
4. **Threat IDs renumbered.** v2 threats are T42 to T55 instead of T16 to T29, with a mapping table.
5. **Section 10 amendments for slices 3 and 8** move to slice 13 instead of reopening the open pull requests. The slice 4 amendment (Steam ID in the index) is already in the code.

## Tests

None run: no code changed. `python scripts/check.py`: all checks passed (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan). A dash check confirmed no em or en dashes in any new or changed file.

## Known gaps

- ADRs 0012 to 0019 are proposed, not accepted, until you approve them.
- The device-facing claims in the assumptions are unverified until their slices run on the devices.
- The slice 8 report does not carry the "Next: Slice C0" pointer line, because that commit was declined. C0 now exists, so the pointer is no longer needed.

## On-device checklist

None for C0. The pending checklists are in the reports for slices 3 to 8.

## Questions

Each blocks the slice named. The recommended answer is given, and is what will happen if you simply confirm.

| # | Question | Blocks | Recommendation |
|---|---|---|---|
| Q0 | Run the on-device checks and merge #4, #5, #6, #7, #8, then this C0 pull request | Slice 9 | Merge in that order after the checks in each slice report |
| Q1 | Do you sign off the audit (`docs/advisor-port-audit.md`) and ADR-0013, allowing your Tuning Advisor code to be ported under BSD-3-Clause? | Slice 14 | Yes, with the fixture and data rules in ADR-0013 |
| Q2 | Device registry: rebuild the Legion Go and Legion Go 2 entries from your own `capture_device.sh` dumps (run once on each device) and cite manufacturer pages for other handhelds, rather than carry over strings credited to InputPlumber (GPL-3.0) and Handheld Daemon (LGPL-2.1)? | Slice 14 | Yes. The strings are facts, but this removes any doubt at the cost of one capture per device |
| Q3 | Carry Tuning Advisor's "AI replaces the cards, with a way back" layout into Keepsake? | Slice 15 | Yes. P18 allows it and it was your choice for Tuning Advisor |
| Q4 | ProtonDB: (a) ODbL monthly-dump index published as a Keepsake release asset, (b) the `www.protondb.com` summaries endpoint the spec allowlists, or (c) neither? | Slice 15 | (a). Remove `www.protondb.com` from the allowlist. It has no published terms |
| Q5 | P18 does not list the Steam app ID. May AI requests include it (Tuning Advisor sent it)? | Slice 15 | No. Send the title only, which P18 already allows |
| Q6 | Deliver the slice 3 and slice 8 amendments in slice 13 instead of reopening #4 and #7? | Slice 13 | Yes, as planned in `docs/plan.md` |
| Q7 | `C:\dev\keepsake-v2` does not exist. Are the session attachments the final spec and research? | Nothing (already copied) | Confirm, or send the final files and I will update the copies |
| Q8 | Approve ADRs 0012 to 0019 and `docs/plan.md` | Slice 9 onwards | Approve |
