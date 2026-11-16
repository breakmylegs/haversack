# Security review before v1.0.0

Slice 12, 16 November 2026. A review of every v1 entry in `docs/threat-model.md` (T1 to T41 and T56 to T69). Entries T42 to T55 belong to Keepsake v2 modules that do not exist yet and are reviewed in slice 25.

The v1.0.0 acceptance needs every entry to have a mitigation in place or an accepted risk signed off by Peter. All entries have a mitigation in place except those below, which need his decision.

## Needs Peter's sign-off (accepted risks)

| ID | Risk | Why it is acceptable | Recommendation |
|---|---|---|---|
| T5 | Cloud snapshot metadata is unsigned: someone with write access to the cloud folder could publish a consistent but malicious snapshot | Every path is confined to the game's logical roots (T3, T8); every restore takes a verified pre-restore snapshot and can be undone; access to the folder needs the owner's cloud account | Accept for v1; client-side signing or encryption stays out of scope (build prompt section 20) |
| T10 | Until a release key is pinned, a compromised GitHub account could publish a malicious release with a matching `SHA256SUMS` | Verification is built (ADR-0023); `main` and tags are protected (ADR-0005); every release can be rebuilt and compared | Create the minisign key and pin it before v1.0.0 (steps in `docs/releasing.md`). Accept only if v1.0.0 must ship first |
| T17 | The development deploy script runs `sudo` on the device | Development only, password typed each time, never stored; the plugin has no root flag | Accept |
| T19 | Decky's installer extracts zips with `extractall` | Decky's own code; Keepsake's zips are deterministic with safe names | Accept |
| T20 | The device test runner runs repository code on the device | Run only by the owner on his own device, in a temporary folder, as the user | Accept |
| T27 | The Ludusavi manifest is unsigned | HTTPS to an allowlisted host; size cap; paths confined to roots, so the worst case is wrong or missing files in a preview or snapshot, never writes elsewhere | Accept |
| T60 | Health checks and the diagnostics export list game names | Both stay on the device; the export is only copied off by the owner | Accept |
| T63 | Google Drive duplicate names: if Drive's listings lag, two racing writers could both believe they won | Keys are device-specific, so collisions come only from retries; readers resolve duplicates the same way; snapshot content is verified by hash | Accept |
| T69 | The Steam Cloud rule (A118) may mislabel a game | Labels and offers only; double syncing is still guarded by conflicts and pre-restore snapshots | Accept, confirm on device |

## Checked and in place

T1 to T4, T6 to T9, T11 to T16, T18, T21 to T26, T28 to T41, T56 to T59, T61, T62, T64 to T68. Each row in the threat model names the code and the tests that cover it. During this review:

- T15 (registry merge) moved to in place with slice 11's guarded merge and fault-injection tests.
- T34 (refresh token revoked) moved to in place: health check, toast and pending pushes.
- T10 moved from a missing control to built but awaiting the owner's key.

## Process checks

- No GitHub Actions (ADR-0004); the local gate (`scripts/check.py`) and the in-repo secret scan run before every pull request and release. The scan caught two synthetic test values during slices 11 and 12; both were changed.
- No root flag, no bundled binaries, no network endpoints outside the allowlist (`keepsake.net` enforces it per host).
- Secrets: tokens, passwords and client secrets are stored mode 0600, redacted from logs and never returned to the frontend.
