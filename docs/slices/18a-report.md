# Slice 18a report: the transfer engine

The first part of slice 18, recorded in ADR-0057. The protocol is written in `docs/protocol.md` and freezes at the end of 18b.

## What changed

- **`replication/manifest.py`:**
  - each entry records its path, type, size, mode and nanosecond time, plus the link text for links;
  - files carry the SHA-256 of each 4 MiB chunk and of the whole file, and the root hash covers the canonical JSON;
  - all-zero chunks are recognised;
  - validation refuses unsafe paths, case collisions, missing parents, entries under links, links leaving the folder, and names Windows forbids on a Windows target.
- **`replication/source.py`:**
  - shares are offered to named paired devices only;
  - they serve only the manifest and single chunks;
  - each chunk is hashed again before it is sent, and a final link is never followed.
- **`replication/link.py`:** raw-byte answers (`blob`, up to 64 MiB), `request_blob`, and `Refused` for `error` frames, so a refusal fails a job instead of being retried.
- **`replication/transfer.py`:**
  - one staging folder beside the target holds the journal, the manifest and the tree;
  - the journal is durable;
  - chunks are pulled, verified and recorded only after `fsync`;
  - zero chunks are skipped and stay holes, and data chunks are preallocated;
  - free space is checked first;
  - damaged chunks are fetched again;
  - each file is checked against its whole-file hash, then metadata is applied (links, modes, times), and the root is checked again;
  - promote is two renames, with rollback;
  - the job retries with backoff, pauses on a full disk, and fails on a refusal;
  - it has an optional rate cap;
  - "Stop and remove", and recovery at startup.
- **Docs:** ADR-0057, `docs/protocol.md`, T115, A192, the module document, the plan and the changelog.

## Test results

- `tests/test_replication_transfer.py`: 40 passed and 2 skipped on Windows. The 2 skipped tests (links, modes and holes) are POSIX-only and run on the device.
- The covering tests pass: `test_replication_rules.py`, `test_replication_link.py` and `test_replication_devices.py`.
- Mutation checks: 31 mutations across the engine, manifests, the sending side and refusals. All killed after four tests were added and one was extended.
- `python scripts/check.py`: all checks passed.

## Known gaps

- There is no sleep inhibitor, power rule, parallel or adaptive streaming, multi-source pulling or progress interface yet (18b).
- There is no user action yet that offers or receives a folder; slice 19 adds sending a game.

## On-device checklist

1. Run `python scripts/test_on_device.py tests/test_replication_transfer.py`. All tests should pass there, including the link, mode and hole tests.
2. Run the same tests with the device's SD card as the temporary folder: `TMPDIR=/run/media/<user>/<card>/tmp`. Check what A192 expects on exFAT: holes use full size and modes are not kept.
