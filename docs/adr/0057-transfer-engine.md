# ADR-0057: The transfer engine: manifests, chunks, journal, promote (slice 18a)

- Status: accepted (decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0045 set Replication's hard requirements for moving game files, and ADR-0054 the link and its speed design:
- device to device only;
- exact bytes, sizes, modes, times and links, with no compression;
- pause and resume with a durable journal;
- re-verification of only the chunks that might be incomplete;
- verification against the root hash before promote, and an atomic promote;
- a "Stop and remove" that leaves nothing behind;
- a free-space check and preallocation;
- fault injection tests.

Slice 18 is large, so it is built in two parts, like slice 17:
- **18a (this ADR):** the engine.
- **18b:** the sleep inhibitor, the power rule, parallel and adaptive streams, pulling from several devices, the progress interface, and freezing the protocol.

## Decision

1. **Manifests** (`replication/manifest.py`).
   - **Each entry:**
     - a relative POSIX path;
     - its type (file, folder or link), mode and modification time in nanoseconds;
     - for links, the link text;
     - for files, the size, the SHA-256 of the whole file and of each 4 MiB chunk.
   - **Sorting and the root hash:** entries are sorted. The root hash is the SHA-256 of the canonical JSON, so one value pins every byte.
   - **What the receiver refuses:** absolute, `..` or drive paths; two entries that differ only by case; missing parent folders; entries under a link; links that point outside the folder; and, for a Windows target, names Windows forbids.
   - **Never copied or followed:** links are recorded, never followed. Sockets, devices and pipes are not copied.
2. **Sparse files, decided:**
   - **How zero chunks are handled:** a chunk whose hash is that of all zeros is neither requested nor written. The staged file is created at full size with `truncate`, so those chunks stay holes, and only data chunks are preallocated with `posix_fallocate`.
   - **What it costs:** sparseness is kept at 4 MiB granularity without `SEEK_HOLE` support on the sender, and every byte is still covered by the hashes.
3. **The sending side** (`replication/source.py`).
   - **What a share is:** a folder and its manifest, offered to named paired devices.
   - **What can be asked for:** only two things, the manifest and a single chunk by path and index from that manifest. There is no listing, and no path outside the manifest.
   - **Checks before a chunk is sent:**
     - the file is opened without following a final link, and must still be inside the folder;
     - each chunk is hashed again, so a file that changed since the offer is refused rather than sent wrong.
4. **Raw bytes on the link.**
   - **The frame:** a handler may answer with a frame `{"type": "blob", "size": n}` followed by exactly *n* raw bytes, at most 64 MiB (a manifest or one chunk).
   - **Refusals:** an `error` frame is a refusal (`Refused`), which fails a job. A dropped connection is retried.
5. **The receiving side** (`replication/transfer.py`).
   - **Staging:** everything a job writes is in `<target parent>/.keepsake-incoming-<job>/`, on the same file system as the target. It holds `journal.json`, `manifest.json`, `tree/`, and `previous/` once promote starts.
   - **The journal:**
     - it is written with write, `fsync`, rename and a folder `fsync` (`fsutil.atomic_write_json`);
     - a chunk counts as done only after its file is `fsync`ed and then the journal lists it, every 16 chunks or 2 seconds;
     - on resume, chunks the journal does not list are hashed from disk. A match is kept and anything else is fetched again, so only possibly incomplete chunks are re-checked.
   - **Before fetching:** free space must cover what is left plus the margin (`policy.space_needed`). Otherwise the job pauses and says how much is needed.
   - **Damage:** a chunk that arrives damaged is fetched again, up to 3 times, then the job fails.
   - **Verification and metadata:**
     - every file is checked against its whole-file hash, and failures are fetched again once;
     - then links, modes (POSIX) and times are applied, folders' times last and deepest first;
     - the root hash is checked once more before promote.
   - **Promote:** an existing target is renamed into `previous/`, then `tree/` is renamed to the target. A failure between the two renames puts the old target back. `previous/` is removed when the job completes.
   - **Recovery after errors:**
     - a lost or refused connection is retried with backoff from 1 to 60 seconds, indefinitely unless a limit is set;
     - a full disk pauses the job with the reason;
     - a refusal fails it.
   - **"Stop and remove":** first it puts back a target that a cut-short promote left aside. Then it deletes the staging folder, and only a folder whose name is a staging folder's.
   - **At startup** (`recover`):
     - stopped jobs are removed;
     - running, waiting and verifying jobs become paused;
     - a promote cut between its renames is rolled back;
     - a promote that finished but was not cleaned up is completed.
   - **Bandwidth cap:** an optional cap paces the average rate.
6. **Protocol status.** The manifest format and the `manifest` and `chunk` requests are written in `docs/protocol.md`. They freeze at the end of slice 18 (18b), as the plan says, so 18b may still add fields.

## Consequences

- **No new endpoint, binary or permission.** Writes go only into the user's chosen target folder and its staging sibling. Slice 19 wires this to Steam registration and the write allowlist checks.
- **T115 and A192:**
  - T115: a malicious or broken sender, and a crash during promote;
  - A192: rename atomicity, `posix_fallocate` and hole behaviour on the devices' file systems (ext4 and btrfs, and exFAT on SD cards).
- **Tests:** `tests/test_replication_transfer.py` covers:
  - a whole copy, in process and over real TLS;
  - a kill mid-chunk, and power loss with unsynced writes;
  - a damaged journaled chunk, a network drop and a device that stays away;
  - a corrupt chunk, a full disk and too little space;
  - a source that changed, a wrong manifest and a device not offered the folder;
  - a stop at every phase, and a crash between the promote renames;
  - recovery, the rate cap, manifests and the journal.

## Sources

- POSIX `rename` is atomic within one file system: [rename(2)](https://man7.org/linux/man-pages/man2/rename.2.html). Windows `MoveFileEx` with `MOVEFILE_REPLACE_EXISTING`, used by `os.replace`.
- [posix_fallocate(3)](https://man7.org/linux/man-pages/man3/posix_fallocate.3.html), and `truncate` leaving holes: [truncate(2)](https://man7.org/linux/man-pages/man2/truncate.2.html).
- Durable replace pattern (write, fsync, rename, fsync the folder): [fsync(2)](https://man7.org/linux/man-pages/man2/fsync.2.html), notes on folder entries.
