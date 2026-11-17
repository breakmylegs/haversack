# ADR-0035: ProtonDB reports through Keepsake's own index

- Status: accepted (c0-report Q4, option a, Peter's recommended answer from 16 November 2026; the backlog item from ADR-0029)
- Date: 17 November 2026
- Deciders: Peter (owner)

## Context

ProtonDB publishes its reports as monthly dumps in `bdefore/protondb-data`:
- the database is under the ODbL 1.0, and its contents under the DbCL 1.0;
- there is no licence file in the repository, so the licence comes from the dump README (A96).

Its summaries endpoint on `www.protondb.com` is undocumented, with no published terms. Tuning Advisor left it out, and so did Q4.

Q4 chose option a: build an index from the dump and publish it as a Keepsake release asset under the ODbL. ADR-0029 deferred this to the backlog because it needs its own release-asset pipeline.

## Decision

1. **Builder.** `scripts/protondb_index.py` is ported from Tuning Advisor's `tools/protondb_index.py`; the licence audit is signed off (ADR-0013). It runs on the laptop only (ADR-0004).
   - **Input:** it streams `reports_piiremoved.json` from the dump's `.tar.gz` without extracting it.
   - **What it keeps:** apps with at least one report from a handheld chip, up to 5 newest such reports each, plus report counts.
   - **Text clean-up:** report text is cut to one line, home folders become `~`, links become `[link]`, and each field is capped.
   - **A cut-off dump is refused.** The reader requires the closing bracket. Tuning Advisor's reader accepted a dump cut off between records; this port fixes that.
   - **Size:** an index over 30 MB is refused.
2. **Published** as the rolling release `protondb-index` of `breakmylegs/keepsake`, with ODbL and DbCL notes:
   - It is never marked latest, so `releases/latest/download/Keepsake.zip` still serves the plugin.
   - It is not a `v*` tag, so both the current updater and the v0.2.0 updater skip it. Both skip any tag that is not `v<version>`, checked on 17 November 2026.
   - Re-publishing replaces the asset in the same release, so Advisor's address never changes.
   - The `v*` tag protection (ADR-0005) is untouched.
3. **Advisor source `sourceProtonDb`, off by default.**
   - **Download:** when turned on, it downloads the index from GitHub release asset downloads, which is allowlisted and already used by the updater. The download is held in memory, capped at 30 MB, and checked before it is written to the Advisor's cache folder with `atomic_write_bytes`.
   - **Refresh:** after 31 days. A failed refresh keeps the old copy, and after a failure it waits an hour unless the user forces it.
   - **Lookup:** one game is found by Steam app ID, by reading the gzipped lines on the device. No game is ever named to anyone, and `www.protondb.com` is never called.
   - **Turning it off** empties the cache file. Advisor code never deletes, renames or runs anything (P16: `tests/test_advisor.py` checks this statically and by a full session).
4. **How the reports are used.**
   - **Shape:** reports join Deck Verified's in the same format.
   - **Device match:** each report's chip, for example "AMD Ryzen Z2 Extreme", is matched against the device's own chip, so a Legion Go 2 sees Z2 Extreme reports as "same chip".
   - **What they feed:** ProtonDB has no TDP or frame-rate fields, so the reports feed the Proton advice, launch options and notes, not power settings.
   - **Summary:** the page shows the share of reports that say the game works, with the dump name, a link to the game on ProtonDB (opened by the user in the browser) and the ODbL attribution.
   - **AI:** AI requests gain nothing from this. Their payload takes settings fields only (P18).
5. **Monthly refresh, by hand.** Peter or Claude downloads the new dump, runs `build`, then `publish` (see `docs/releasing.md`). It is independent of plugin releases.

## Consequences

- Advisor gains handheld ProtonDB reports without a new endpoint and without telling anyone which games are installed.
- The index is public data, derived from ProtonDB under the ODbL. The release notes, the index header and `THIRD_PARTY_NOTICES.md` carry the attribution, and the builder is public, as the ODbL asks.
- About 70 MB has to be downloaded on the laptop each month. The device downloads only the index (a few MB), and only when the source is on.
