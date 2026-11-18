# R3 report: trust and distribution

Slice R3 of the post-v2 roadmap (ADR-0047), recorded in ADR-0050.

## What changed

- **Cloud integrity.**
  - `SnapshotEngine.scrub` verifies blobs against their metadata.
  - `scrub_cloud(full)` runs weekly from the idle pass (heads, pins and bases), or in full on demand.
  - Results go to `integrity.json`, a "Cloud integrity" health check and a damaged list in History.
  - `repair_snapshot` saves a fresh snapshot under a new id.
  - Interfaces: Gaming Mode Diagnostics and History, and the PC Health page.
- **Export.**
  - `export_snapshots(folder, scope)` writes a new folder with verified zips per game, `index.json` and `README.txt`. Nothing is ever overwritten.
  - Interfaces: Gaming Mode Settings (folder picker) and the PC Settings page.
- **Supply chain.**
  - `scripts/sbom.py` builds a deterministic CycloneDX SBOM, which becomes a release asset in the signed `SHA256SUMS`.
  - Key rotation and compromise runbooks are added to `docs/releasing.md`, and `SECURITY.md` is updated.
  - Private vulnerability reporting is switched on for the repository.
- **Decky store.** `docs/store-submission.md`: the requirements, where Keepsake stands, and Peter's submission steps.
- **Performance budget.** `scripts/perf_budget.py` is the gate's `perf` step. Retention planning is about four times faster after parsing each time once.
- **Docs:** ADR-0050, T107, T108, A182, A183, the user guide, the changelog and the plan.

## Test results

- `tests/test_trust_distribution.py` (12 new): passed.
- Covering tests: `test_engine`, `test_release`, `test_scripts`, `test_host`, `test_app_ux`, `test_save_safety`, `test_health` (updated for the new check) and `test_gates_retention`, all passing.
- Mutation checks: 19 mutations, all killed after three tests were added for the first-round survivors.
- `tsc` and eslint clean.

## Known gaps

- The Ludusavi-layout export stays deferred (ADR-0047).
- The store submission needs Peter's GitHub account.

## Checks for Peter

1. **Handheld export.** In Settings, choose **Export the latest of each game** and pick a folder on the SD card. Check that the folder holds one zip per game, `index.json` and `README.txt`.
2. **Handheld integrity check.** In Diagnostics, choose **Check cloud integrity**. Every game should show no damage.
3. **Store submission (optional):** follow `docs/store-submission.md`.
