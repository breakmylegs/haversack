# ADR-0045: Replication goes device to device, uncompressed, resumable and clean

- Status: accepted (Peter's hard requirements for slices 16 to 20, 17 November 2026; the open details decided under ADR-0037)
- Date: 17 November 2026
- Deciders: Peter (owner)
- Amends: `docs/modules/replication.md`, the slice 16 to 20 plans, ADR-0016 (LAN exposure) and the transport question left to ADR-0025

## Context

Replication copies whole game installs and Proton prefixes between devices. These can be hundreds of GB. Peter set eight hard requirements. Each is checked below against primary sources, and the open details are decided.

## Primary sources checked

- **Tailscale, "Connection types".** Connections are direct, through a peer relay, or relayed through DERP. All are end to end encrypted with WireGuard; "the primary difference between them is performance, not security". DERP is "generally slower than direct connections and may offer lower maximum throughput". Connections start relayed and are upgraded when possible.
- **systemd, "Inhibitor Locks".**
  - The call is `org.freedesktop.login1.Manager.Inhibit(s what, s who, s why, s mode) -> h fd` on the system bus, and the lock lasts as long as the file descriptor is open.
  - Delay mode works only for sleep and shutdown, and lasts up to `InhibitDelayMaxSec` (5 seconds in the page's example).
  - `PrepareForSleep(true)` starts the preparation, and watching for it without a delay lock is racy.
  - Taking locks is governed by polkit.
- **Python `ssl`.**
  - `OP_NO_COMPRESSION` exists since 3.3 and is set by default since 3.6.
  - `SSLSocket.compression()` returns `None` when the connection is uncompressed.
  - TLS-PSK callbacks need `ssl.HAS_PSK` (added in 3.13).
- **Python `socket`.** `socket.recv_fds` and `send_fds` (stdlib since 3.9) carry `SCM_RIGHTS` file descriptors over a Unix socket. That is all a D-Bus client needs to receive the inhibitor lock.
- **Python `os`.** `os.posix_fallocate` exists on Linux. `SEEK_DATA` and `SEEK_HOLE` find a sparse file's data on Linux.
- **Windows.** `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` keeps the system awake until it is cleared. `\\?\` paths lift the `MAX_PATH` limit.

## Decision

1. **Never through cloud storage or a relay.**
   - **What stays off the cloud:** install, prefix and chunk bytes, and their manifests, never go to any cloud store or to any server or relay Keepsake runs.
   - **How devices connect:** directly on the same LAN, or to a manual address.
   - **Remote devices:** only through the user's own VPN or overlay address (WireGuard, Tailscale, ZeroTier).
   - **Speed shown:** Keepsake measures the link before and during a transfer and shows the speed. When a link is slower than 10 MB/s, or its round trip is over 50 ms, it says plainly that it looks slow or relayed. For Tailscale it adds that a relayed (DERP) path is the likely cause.
   - **Enforcement:** `tests/test_replication_rules.py` fails if any module under `keepsake/replication/` imports a cloud store, the sync engine, cloud sign-in or the app (`keepsake.store` and everything under it, `keepsake.sync`, `keepsake.auth`, `keepsake.loopback_auth`, `keepsake.app`), or imports anything dynamically. The checker itself is tested against synthetic code.
2. **No compression at any layer.**
   - **Bytes as they are:** no zlib, gzip, bz2, lzma or zstd, and no compressed zip members.
   - **TLS:** every TLS context Replication makes passes `keepsake.replication.policy.require_no_compression`, which sets `OP_NO_COMPRESSION` and fails if it is missing. Each connection also checks `compression() is None`.
   - **Enforcement:** the rules test forbids importing compression modules under `keepsake/replication/`.
   - **What is preserved:** exact bytes, sizes, modes, mtimes and symlinks (as links, never followed).
   - **Sparse files:**
     - A sparse source file is sent as its data ranges plus hole ranges in the manifest, found with `SEEK_DATA` and `SEEK_HOLE` on Linux.
     - The target recreates the holes by seeking, so the received bytes, size and hash are identical.
     - This is a description of the file, not compression: no byte is ever transformed.
     - A Windows target writes zeros for holes.
3. **Pause and resume, with automatic recovery.**
   - **Pause** keeps the staging folder and the journal. **Resume** continues from the last verified chunk.
   - **Automatic recovery** from errors, a lost network, the peer leaving and returning, a plugin reload, suspend and resume, and a reboot or power loss. Retries back off from 1 to 60 seconds and reconnect when the peer returns.
   - **The journal is durable:** write to a temporary file, `fsync` it, `rename` it, then `fsync` the parent directory.
   - **On resume:** only chunks after the last journalled verified chunk, and any chunk whose file is newer than the journal entry, are hashed again. Hundreds of GB are never rehashed.
   - **Before promoting:** everything is verified against the root hash.
4. **"Stop and remove" cleans up completely.**
   - **Separate from Pause:** it asks for confirmation first.
   - **What it deletes:** the staging data, partial files, the journal, and every shortcut, registration, `compatdata` folder or tool copy made for that job. Each is recorded in the journal before it is created, so the clean-up knows exactly what is Keepsake's.
   - **What it never touches:** the source, and the target's existing install.
   - **Promote is atomic:** a stop before promote leaves the target as it was, and a stop during promote rolls back.
   - **At startup:** leftovers of stopped jobs are removed. Paused jobs are kept, and the interface shows how much space they hold.
5. **Size and endurance.**
   - **Space first:** free space is checked before starting, with a margin of 5 percent or 2 GiB, whichever is larger. On Linux the files are preallocated with `os.posix_fallocate`, so a full disk fails early.
   - **No sleep while transferring:**
     - **Linux:** a logind `sleep` inhibitor in delay mode. Keepsake checkpoints the journal on `PrepareForSleep(true)`, then releases the lock.
     - **The D-Bus client:** a minimal pure-Python one (a Unix socket, `AUTH EXTERNAL`, `Hello`, `AddMatch`, `Inhibit`, with the file descriptor received through `socket.recv_fds`). This was chosen over a System Binary Register entry for `systemd-inhibit`, because:
       - it keeps P9 (stdlib first) with no binary;
       - it receives the `PrepareForSleep` signal, which `systemd-inhibit` cannot pass back;
       - it is small enough to test against a fake bus.
     - **If the lock is refused:** if polkit refuses it, the transfer still runs, and a resume after sleep recovers it (requirement 3).
     - **Windows:** `SetThreadExecutionState`.
     - **The battery rule** is unchanged: pause below 30 percent unless charging.
6. **Speed.**
   - **Measure first:** slice 16 measures throughput with TLS. With TLS, `asyncio` `sendfile` falls back to reads, so there is no zero-copy.
   - **The design:**
     - reads of 4 MiB chunks;
     - hashing in a worker thread, off the event loop;
     - one stream, plus optional parallel streams (up to 4) if slice 16 shows a single stream is CPU or latency bound.
   - **Progress shown:** MB/s, ETA, per-file progress, and the state (transferring, paused, waiting for device, verifying, installing). It appears in the Quick Access Menu and on the game page, with a notification on finish or failure.
   - **A bandwidth cap** (token bucket) is available.
7. **Cross-OS targets.**
   - **Windows:** long paths use `\\?\`. Characters Windows forbids (`<>:"|?*` and trailing dots or spaces) are refused in preflight with the file named, never silently renamed.
   - **Case:** case-only collisions are refused on case-insensitive targets.
   - **Executable bits:** carried in the manifest and applied on ext4. On NTFS they are kept in the journal so a copy back restores them.
8. **Tests.** Fault injection for:
   - a kill mid-chunk;
   - a simulated power loss (the process killed with unsynced writes, then only the `fsync`ed state kept);
   - a network drop;
   - the peer restarting;
   - a full disk;
   - a corrupt chunk;
   - a stop at every phase, leaving zero leftover files.

   Plus the no-cloud and no-compression tests. These belong to slice 18. The rules test and the TLS policy check land now (`keepsake/replication/policy.py`, `tests/test_replication_rules.py`), with a real TLS-PSK handshake on this laptop showing `compression()` is `None` on both ends.

## Consequences

- **Slice 16** adds the measurements listed in its plan (throughput with and without TLS, hashing speed, Tailscale direct and relayed, the logind inhibitor under the `deck` user). Peter's device steps are in `docs/slices/s2-report.md`.
- **Slices 17 to 20** carry these requirements as acceptance criteria (`docs/plan.md`).
- **Threat model:** T102 covers bytes or manifests leaving the device pair and compression side channels. T103 covers leftovers after a stop, and a clean-up that strays outside its own records.
- **No new endpoint, binary or permission.** The D-Bus client talks only to the local system bus socket.
