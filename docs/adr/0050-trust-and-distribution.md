# ADR-0050: Trust and distribution (R3)

- Status: accepted (slice R3 of ADR-0047; decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0047 accepted these items for R3:
- a cloud integrity check (item 5);
- an export with no lock-in (item 6, plain zips);
- getting ready for the Decky Plugin Store (item 30);
- an SBOM, key runbooks and SECURITY.md (item 31);
- a performance budget in the gate (item 32).

## Decision

1. **Cloud integrity check.**
   - **How it works:** `SnapshotEngine.scrub` downloads snapshot blobs and verifies each against its metadata. It changes nothing.
   - **Weekly:** the idle pass runs it once a week over heads, pins and every device's base, which are the snapshots restores rely on.
   - **On demand:** Diagnostics, or Health on a PC, checks every kept snapshot.
   - **Results:** they go to `integrity.json`, a "Cloud integrity" health check, and a damaged list in each game's History.
   - **Repair:**
     - write-once objects are never fixed in place (P2);
     - instead, Repair saves a fresh snapshot of this device's files under a new id, flagged `repair`, which becomes the base;
     - the damaged object stays, and retention removes it in time.
2. **Export.**
   - **What it writes:** `export_snapshots(folder, scope)` writes a new `Keepsake export <date>` folder, numbered if one already exists, inside a folder the user chose. It holds:
     - one folder per game, with names safe on FAT, exFAT, NTFS and ext4;
     - each zip, verified;
     - an `index.json` (game, snapshot, time, device, files);
     - a `README.txt` explaining the neutral folder names.
   - **Scope:** the latest snapshot of each game, or every snapshot.
   - **Never overwrites:** every file is opened exclusively.
   - **A new write location:** the folder must be absolute, existing and writable, and is used only after an explicit user action. ADR-0047 decided this is allowed.
   - **Deferred:** the Ludusavi layout stays deferred.
3. **Decky Plugin Store.**
   - **Keepsake already meets the published rules:**
     - a licence with the template notice at the bottom;
     - pnpm 9;
     - `plugin.json` with no flags;
     - no compiled binaries.
   - **The checklist and steps** are in `docs/store-submission.md`.
   - **Submission is Peter's:** it is a pull request from his GitHub account to the plugin database.
4. **Supply chain.**
   - **A CycloneDX 1.5 SBOM** (`scripts/sbom.py`) lists:
     - the frontend packages Rollup bundles (from `package.json` and the lockfile; `@decky/ui`, React and ReactDOM come from Decky and Steam, so they are left out);
     - the vendored Python libraries, with their wheel hashes.
   - **Reproducible:** it has no timestamp, and its serial number is derived from the version, so a tag always rebuilds the same file.
   - **Signed:** it is a release asset, `Keepsake-v<version>.sbom.cdx.json`, listed in the signed `SHA256SUMS`.
   - **Runbooks:** `docs/releasing.md` gains key rotation and compromise runbooks (planned rotation, lost key, exposed key).
   - **SECURITY.md** describes the signature, the SBOM and the runbooks.
   - **Private vulnerability reporting was off,** although SECURITY.md pointed people at it. It was switched on (a reversible repository setting, under ADR-0037).
5. **Performance budget.**
   - **What it covers:** `scripts/perf_budget.py` times the hot paths on synthetic data:
     - a manifest index of 5,000 titles;
     - matching and ordering 500 games;
     - a retention plan over 10,000 snapshots;
     - hashing a 10,000-file list.
   - **The limits:** about four times this laptop's times.
   - **In the gate:** it is the `perf` step in `scripts/check.py`.
   - **It found one problem:** retention parsed each snapshot's time with `strptime` about three times. Parsing it once per snapshot made the plan about four times faster, with identical results (`tests/test_gates_retention.py`).

## Consequences

- **No new endpoint and no new cloud object.** The scrub and export only read the cloud.
- **Store installs** will update through the store once listed, and GitHub installs through Keepsake's own signed updater.
