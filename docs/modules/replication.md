# Module: Replication

Device-to-device replication of non-Steam games, then ongoing install sync. Bytes go only between the user's own devices (ADR-0045).

| | |
|---|---|
| Flag default | Off. The listener is a separate switch, also off |
| Spec | `docs/build-prompt-v2.md` sections 4 (P10, P14, P15, P17, P19), 6, 7.4 and 8.2; research sections 2, 4.2, 4.4, 4.6, 4.7 and 4.10 with the supersessions in spec section 11 |
| ADRs | 0012, 0014, 0015, 0016, 0018, 0045 (hard requirements), 0054 (link and pairing), 0056 (discovery, addresses, Wake-on-LAN, pages) |
| Code | `py_modules/keepsake/replication/`: `policy.py`, `link.py`, `peers.py`, `service.py`, `discovery.py`, `netinfo.py`; `src/pages/ReplicationPage.tsx`; the desktop Devices page; `docs/protocol.md` (planned) |
| Slices | 17a (link and pairing, built), 17b (discovery, Wake-on-LAN, pages, built), 18 (transfer engine, protocol frozen), 19 (send a game), 20 (ongoing sync, minor release), then R7 (direct save sync). Slice 16's measurements are tuning input, not a gate |

## Hard requirements (Peter, 17 November 2026; ADR-0045)

1. **Never through cloud storage.**
   - **What stays off the cloud:** install, prefix and chunk bytes, and their manifests, never go to any cloud store, Keepsake server or relay. `tests/test_replication_rules.py` fails if Replication code imports a store, the sync engine or cloud sign-in.
   - **How devices connect:** directly on the same LAN, or to a manual address.
   - **Remote devices:** only through the user's own VPN or overlay address (WireGuard, Tailscale, ZeroTier).
   - **Speed shown:** the measured speed is always shown, and a slow link (under 10 MB/s or over 50 ms) is called slow, or possibly relayed when it is a VPN.
2. **No compression at any layer.**
   - **Bytes as they are:** nothing is compressed, and TLS compression is off (`policy.require_no_compression`, plus `compression() is None` checked on each connection).
   - **What is preserved:** exact bytes, sizes, modes, mtimes and symlinks.
   - **Sparse files** travel as data ranges plus hole ranges, and are rebuilt by seeking.
3. **Pause and resume.**
   - **Pause** keeps staging and the journal. Resume continues from the last verified chunk.
   - **Automatic recovery** from errors, network loss, the peer leaving, a reload, suspend, and a reboot or power loss, with retries from 1 to 60 seconds.
   - **A durable journal:** write, `fsync`, rename, then `fsync` the parent directory.
   - **On resume:** only chunks that might be incomplete are hashed again.
   - **Before promote:** everything is verified against the root hash.
4. **"Stop and remove" cleans up.**
   - **Asks first:** it needs a confirmation.
   - **What it removes:** staging, partial files, the journal, and every shortcut, registration, `compatdata` folder or tool copy the job made, all recorded in the journal before creation.
   - **What it never touches:** the source, or the target's existing install. Promote is atomic, and a stop during promote rolls back.
   - **At startup:** leftovers of stopped jobs are removed. Paused jobs are kept, with their space shown.
5. **Size and endurance.**
   - **Space first:** free space must cover the size plus 5 percent or 2 GiB (`policy.space_needed`), and files are preallocated on Linux.
   - **No sleep while transferring:**
     - Linux: a logind delay lock through a minimal pure-Python D-Bus client, which checkpoints on `PrepareForSleep`.
     - Windows: `SetThreadExecutionState`.
   - **The battery rule** stays.
6. **Speed.**
   - **Design:** 4 MiB reads, hashing off the event loop, and optional parallel streams after slice 16 measures.
   - **Progress:** MB/s, ETA, per-file progress and state, in the Quick Access Menu and on the game page, with notifications.
   - **A bandwidth cap** is available.
7. **Cross-OS targets.** Windows long paths (`\\?\`), refused invalid names and case collisions, and executable bits kept across ext4 and NTFS.
8. **Tests.** Fault injection for a kill mid-chunk, power loss, a network drop, a peer restart, a full disk, a corrupt chunk, and a stop at every phase leaving no files. Plus the no-cloud and no-compression tests.

## What it does

- **Pairing (ADR-0054).** A user-started window of 120 seconds and 3 attempts. Both screens show the same 6-digit code, bound to the TLS session and to committed nonces, and the user confirms on both; then a random 256-bit link key is shared. Peers are listed with remove. mDNS discovery (17b), and a manual address always.
- **Transport (ADR-0054).** TLS 1.2 `ECDHE-PSK-CHACHA20-POLY1305` from stdlib `ssl`: forward secret, authenticated by the link key, compression off and checked. Length-prefixed JSON control frames over asyncio streams. Built for fast and slow links alike: streams added only while speed rises, 4 MiB verified pieces, resume, an optional cap.
- **Manifests** per scope (`install`, `prefix`, `meta`):
  - paths relative to logical roots;
  - size, mode, mtime and symlink target;
  - hole ranges for sparse files;
  - SHA-256 per file, the ordered SHA-256 of fixed 4 MiB chunks, and a root hash per version.
- **Transfer.**
  - **The pull:** receiver-driven, of content-addressed chunks, with a durable journal.
  - **Resume:** after a reload, restart, suspend, power loss or network loss.
  - **Promote:** staging, full verification against the root hash, then an atomic promote. Replaced files are held until the job completes, so a failure rolls back.
  - **Controls:** Pause, Resume, "Stop and remove" and a bandwidth cap.
- **Send a game.**
  1. A Saves source checkpoint.
  2. The offer, then the target preflight (space, names, case, lock, not running).
  3. A pull to staging.
  4. Steam registration through the Steam Operations Executor (ADR-0015).
  5. Promote: the prefix into `compatdata/<new appid>` and the install files into the mapped root.
  6. Discovery re-keys the `gameKey`, and Keepsake offers to copy a missing compatibility tool.
- **Ongoing sync.** A per-game policy of Off, Manual (the default) or Auto. Change scans run on `game_exited` and in the idle loop. When both sides have changed, Keepsake shows the user and does nothing until they choose.

## What it writes (spec section 6.3)

User-registered library roots; `compatdata/<appid>` for replicated games only; `grid` artwork as a fallback; `compatibilitytools.d/<tool>` after the user confirms; staging folders and job journals. Every write passes the central path validator. **Never** a Saves-managed path, or a manifest path tagged `save` after the initial copy (P14). Never anything in a cloud store (ADR-0045).

## Exclusions

- **Always:** `steamapps/shadercache/<appid>`, DXVK and VKD3D caches, Temp folders, crash dumps and logs.
- **Always, for ongoing sync:** every Saves-managed path.
- **By default:** paths tagged `config`, because the screens differ. Each game can opt in for the initial copy only.

## Safety

- **Path checks:** case-only path collisions, absolute paths, `..`, symlinks resolving outside the root, and names Windows forbids on a Windows target are all refused. Symlinks are preserved and never followed.
- **Preflight checks:**
  - free space with margin;
  - root mapping;
  - the compatibility tool;
  - the per-game lock;
  - that the game is not running on either device.
- **The sleep inhibitor** is held only while transferring.
- **Pauses:** below 30 percent battery unless charging, and while a game runs on either device.

## Network

The LAN peer port (default TCP 47110), or the user's own VPN or overlay address. mDNS `224.0.0.251` UDP 5353, only while the listener is on. Never a cloud store or relay.

## Health checks

- Listener state.
- Peers reachable.
- Firewall detected and port reachable.
- Active and paused jobs, with the space paused jobs hold.
- Journal recovery.
- Leftovers cleaned at startup.
- Whether a sleep lock is available.
