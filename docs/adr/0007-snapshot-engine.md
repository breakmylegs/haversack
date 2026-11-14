# ADR-0007: Snapshot engine, restore journal, pins and retention

- Status: accepted (decided in slice 5 under the owner's delegation, 14 November 2026)
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

Slice 5 builds the parts that change save files: snapshots, atomic restore, pre-restore snapshots, safety gates, quarantine, pinning and retention (build prompt sections 3 and 9). The build prompt leaves some details open.

## Decisions

1. **Content hash.** SHA-256 over one line per file, sorted by root and path: `root NUL rel NUL size NUL sha256 LF`. `snapId` is `<deviceSeq:06>-<first 6 hex of deviceId>-<first 8 hex of contentHash>`.
2. **Blob.** A zip with entries `<root>/<rel>`, fixed timestamps and modes. Files are re-hashed while packing; a file that changed since it was scanned aborts the snapshot.
3. **Zip safety (T4).** Before extraction every entry must be in the metadata, be a regular file (no symlinks or folders), unencrypted, of the stated size, below a compression ratio of 1000, and the snapshot below 16 GB; every file's SHA-256 is checked as it is written.
4. **Atomic restore with a journal.** New files are staged in `<root>/.keepsake-stage-<token>` and hash-checked. The journal is written, then files to replace or delete are moved to `<root>/.keepsake-backup-<token>`, then staged files are moved into place. Moves aside come first and creations last, so a file can become a folder and back. An ordinary error rolls back immediately; a crash is rolled back by `restore.recover()` on the next start or restore unless the journal reached `committed`. A folder still holding files the restore does not manage is never moved; the restore is refused instead. A file on disk that the scan did not see (for example hidden by an exclusion) is moved aside, never overwritten.
5. **Pre-restore snapshots** are packed, verified and kept locally, five per game, and can themselves be restored ("Undo").
6. **Pins (new cloud object, layout change before slice 6 freezes it).** `games/<gameKey>/pins/<snapId>.json`, write-once, with an optional `until`. Pins cannot be removed in v1; they only ever keep data.
7. **Retention.** Blobs only; a `pruned/<snapId>` marker is written before the blob is deleted. Protected: pinned, heads, every device's base, the newest snapshot that passed the gates, anything younger than 7 days, and every `manual`, `merge` and `import` snapshot (conservative: the build prompt only names automatic snapshots in the keep policy). Otherwise the last 10 automatic, one per day for 30 days, one per month for 12 months.
8. **Orphan blobs** (a blob without metadata, from an interrupted upload) are deleted only after being seen for 24 hours.
9. **Gates.** Defaults as in the build prompt. User settings are limited to the range from 5% to the default, so gates can be tightened but never loosened or disabled; the zero-files gate is fixed.
10. **Device sequence** lives in the settings folder, so updates never reset it.
11. **Newer schema.** If any snapshot metadata for a game has a newer `schemaVersion`, nothing is written for that game (section 12).

## Consequences

- Restores need free space for the staged copy plus the pre-restore snapshot.
- Hidden `.keepsake-` folders can appear briefly beside save folders during a restore; scans always skip them.
- Pins accumulate; retention cost is only the pinned blobs.
