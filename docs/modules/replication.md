# Module: Replication

Device-to-device replication of non-Steam games over the LAN, then ongoing install sync.

| | |
|---|---|
| Flag default | Off. The listener is a separate switch, also off |
| Spec | `docs/build-prompt-v2.md` sections 4 (P10, P14, P15, P17, P19), 6, 7.4 and 8.2; research sections 2, 4.2, 4.4, 4.6, 4.7 and 4.10 with the supersessions in spec section 11 |
| ADRs | 0012, 0014, 0015, 0016, 0018; transport ADR in slice 16 |
| Code (planned) | `py_modules/keepsake/replication/`, `src/modules/replication/`, `docs/protocol.md` |
| Slices | 16 (spike), 17 (listener and pairing), 18 (transfer engine, protocol frozen), 19 (send a game), 20 (ongoing sync, minor release) |

## What it does

- **Pairing.** User-started window, 6-digit code, time-boxed and rate-limited. Peers listed with revoke. mDNS discovery if viable, manual address always.
- **Transport.** Authenticated encryption over stdlib `ssl` (mutual TLS with pinned self-signed certificates, or TLS-PSK), chosen by the slice 16 spike. Versioned framing over asyncio streams.
- **Manifests** per scope (`install`, `prefix`, `meta`): paths relative to logical roots, size, mode, mtime, symlink target, SHA-256 per file, ordered SHA-256 of fixed 4 MiB chunks, and a root hash per version.
- **Transfer.** Receiver-driven pull of content-addressed chunks, persistent journal, resume after reload, restart, suspend or network loss. Staging, full verification against the root hash, then atomic promote. Replaced files are held until the job completes so failure rolls back. Pause, resume and bandwidth cap.
- **Send a game.** Saves source checkpoint, offer, target preflight, pull to staging, Steam registration through the Steam Operations Executor (ADR-0015), promote prefix into `compatdata/<new appid>` and install files into the mapped root, discovery re-keys the `gameKey`, offer to copy a missing compatibility tool.
- **Ongoing sync.** Per-game policy Off, Manual (default) or Auto. Change scan on `game_exited` and in the idle loop. Both sides changed: show the user and do nothing until they choose.

## What it writes (spec section 6.3)

User-registered library roots; `compatdata/<appid>` for replicated games only; `grid` artwork as a fallback; `compatibilitytools.d/<tool>` after the user confirms; staging folders. Every write passes the central path validator. **Never** a Saves-managed path or a manifest path tagged `save` after the initial copy (P14).

## Exclusions

Always: `steamapps/shadercache/<appid>`, DXVK and VKD3D caches, Temp folders, crash dumps, logs. Always for ongoing sync: every Saves-managed path. Default: paths tagged `config` (the screens differ), per-game opt-in for the initial copy only.

## Safety

Refuse case-only path collisions, absolute paths, `..` and symlinks resolving outside the root. Preserve symlinks, never follow them. Preflight checks free space with margin, root mapping, compatibility tool, the per-game lock and that the game is not running on either device. Sleep inhibitor only while transferring. Pause below 30 percent battery unless charging, and while a game runs on either device.

## Network

LAN peer port (default TCP 47110) and mDNS `224.0.0.251` UDP 5353, only while the listener is on.

## Health checks

Listener state, peers reachable, firewall detected and port reachable, active and paused jobs, journal recovery.
