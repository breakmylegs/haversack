# Tandem: Non-Steam Game Replication for Legion Go Devices

Research findings and design recommendations. Version 0.1, 15 November 2026.
"Tandem" is a working name only. See Decision D1.

---

## 1. Situation

- Two devices. Legion Go (Gen 1) and Legion Go 2, running SteamOS or Bazzite with Decky Loader.
- Every non-Steam game is installed and configured twice today. Configuration covers install location, Proton prefix, shortcut target and start directory, launch options, compatibility tool, artwork, controller layout and saves.
- Steam Local Network Game Transfers only covers Steam-licensed titles. It does not move non-Steam shortcuts, prefixes, artwork or compatibility tool selections.
- Objective. Configure a non-Steam game once on either device, replicate it to the other on request, then keep game files and saves in sync, manually or automatically.

---

## 2. Feasibility Verdict

Feasible with current tooling. Every required primitive exists.

The hard problems are not the file copy. They are:

1. Identity mapping. Steam assigns a different AppID to the same game on each device.
2. Prefix portability. Wine prefixes embed absolute paths and device-specific caches.
3. Save conflict handling. Both devices can be played offline and diverge.
4. Transfer robustness on handheld power, suspend cycles and Wi-Fi.
5. Steam-side registration. Shortcut, artwork and compatibility tool changes can only be applied cleanly from inside the Steam client UI context.

### 2.1 Key Findings

| Area | Finding | Design implication |
|---|---|---|
| Shortcut creation | `SteamClient.Apps.AddShortcut` returns the real AppID immediately, no Steam restart. It ignores start dir and launch options. `SetShortcutName`, `SetShortcutExe`, `SetShortcutStartDir` and `SetAppLaunchOptions` must follow after roughly 500 ms or they silently fail. Pre-quoted exe paths cause double quoting. Bulk creation needs a short delay between calls. | All Steam-side writes go through the Decky frontend. Wrap with delays, retries and read-back verification. |
| AppID generation | Shortcut AppIDs are random on current Steam clients. The widely documented CRC32 of exe plus name does not match live entries. Steam accepts any AppID written to `shortcuts.vdf` in the correct signed 32-bit format. | Same game, different AppID per device. `compatdata/<appid>` and `grid/<appid>*` must be re-keyed on the target. |
| VDF writes | Direct `shortcuts.vdf` edits only take effect after a Steam restart. Steam has had a bug where Desktop Mode and Gaming Mode read `shortcuts.vdf` from different `userdata` folders (`0` versus the account ID). | Read `shortcuts.vdf` for inventory only. Write via `SteamClient` APIs. VDF write plus Steam restart is an explicit, consented fallback only. |
| Artwork | `SteamClient.Apps.SetCustomArtworkForApp()` applies artwork in Gaming Mode. Grid files are `<appid>p.png`, `<appid>_hero.png`, `<appid>_logo.png`, `<appid>.png`, `<appid>_icon.png` under `userdata/<id>/config/grid/`. | Transfer artwork as files. Apply via API on target. File copy as fallback. |
| Decky runtime | Python backend with `_main`, `_unload`, `_uninstall`, `_migration` lifecycle. Frontend calls backend via `callable()` and receives events via `addEventListener()`. Root is available via `"flags": ["root"]`. Decky is a systemd service and can spawn custom backends. Callables must be `async`. | Keep `main.py` thin and stdlib-only. Do not request root. |
| Decky UI scope | Decky UI exists in Gaming Mode and Big Picture only. Plugins do not appear in Desktop Mode. Bazzite docs warn Decky can break or uninstall after OS updates. | The sync engine must not live inside Decky. A standalone user daemon serves the Decky UI, a desktop UI and a CLI. |
| Lifecycle events | `RegisterForAppLifetimeNotifications` has been observed firing within seconds of launch rather than at true exit. | Use a launch wrapper (`tandem-run %command%`) for reliable pre-launch and post-exit hooks. |
| Hardware | Both devices have 2x USB4 and Wi-Fi 6E. Gen 1 has a 2560x1600 144 Hz IPS panel and Z1 Extreme. Gen 2 has a 1920x1200 144 Hz OLED with VRR, and Z2 Extreme (Radeon 890M) or Z2 (Radeon 780M). | Graphics configs and shader caches are device-specific. Never synced by default. |
| Direct cable | Linux `thunderbolt_net` creates a network interface over a USB4 cable. Users report roughly 10 to 11 Gbps in practice. A raw USB4STREAM character device is targeted for Linux 7.2. | Offer a USB4 direct link as a fast path. No protocol change, it is another interface. |
| Firewall | Bazzite ships an active firewall that blocks inbound ports for services such as KDE Connect by default. | First-run reachability check plus guided port opening on Bazzite. |
| Port conflicts | Decky uses CEF remote debugging on port 8080. Steam LAN transfer uses TCP 27040. | Avoid 8080, 8384 (Syncthing), 27040 and 1714 to 1764 (KDE Connect). |
| Ludusavi | Detects Proton saves for non-Steam shortcuts only when the shortcut name matches the PCGamingWiki title. Supports Rclone cloud remotes (Google Drive, OneDrive, Dropbox, SMB, WebDAV and others). `decky-ludusavi` exists but needs Ludusavi installed separately. | Provide a title-mapping step. Use Ludusavi manifest data for save path discovery and cloud import. |
| Frame generation | `decky-lsfg-vk` installs lsfg-vk, writes `~/.config/lsfg-vk/conf.toml`, requires a purchased copy of Lossless Scaling and `~/lsfg %command%` in launch options. lsfg-vk 2.0.0 shipped September 2026 and the plugin has adopted it. | Integrate, do not reimplement. Detect, advise, manage launch option chaining. Never copy the Lossless Scaling DLL between devices. |
| Proton data | ProtonDB summary endpoint `api/v1/reports/summaries/<appid>.json` returns tier, trending tier, best reported tier, score, confidence and report count. It is unofficial and can change. | Advisory input only. Cache. Fail gracefully. |
| Installer flow | Established community method. Add `setup.exe` as a shortcut, force a Proton version, install, then retarget the same shortcut to the game exe and start dir so the prefix is retained. Recreating the shortcut creates a different prefix. `STEAM_COMPAT_MOUNTS` exposes paths outside the defaults to Proton. | Automate exactly this flow with an exe-retarget assistant. |
| ISO mounting | `udisksctl loop-setup -r -f image.iso` maps an ISO read-only without root, subject to polkit. | udisks first. Root helper only as a fallback. |

---

## 3. Prior Art and Gap

| Project | What it does | Relevance |
|---|---|---|
| Steam Local Network Game Transfers | Copies Steam game installs between PCs and Decks on the LAN. | Steam titles only. Confirms the gap. |
| CapyDeploy (AGPL-3.0) | PC hub to handheld agent. mDNS discovery, 6-digit pairing with stored token, 1 MB chunked uploads with resume, shortcut creation via `AddShortcut`, artwork via `SetCustomArtworkForApp`. Decky agent for Gaming Mode, Wails agent for Desktop Mode. | Closest prior art. One-way PC to handheld only. No prefix sync, no save sync, no peer-to-peer. Reference design only. Do not copy code unless the project accepts AGPL. |
| decky-romm-sync | Syncs a RomM library into Steam as shortcuts. | Best public documentation of `AddShortcut` quirks. |
| SyncDeck | Syncthing-based save sync for Steam games via Decky. | Security lessons. It leaked an API key into logs and now blocks credential folders as sync targets. |
| decky-ludusavi | Decky adapter for Ludusavi with bi-directional cloud sync. | Save backup reference. Requires separate Ludusavi install. |
| decky-lsfg-vk | Installs and configures lsfg-vk. | Integration target for frame generation advice. |
| SteamGridDB Decky plugin | Artwork browsing and apply for Steam and non-Steam shortcuts, context menu entry on game pages. | Reference for artwork API usage and game page context menu patching. |
| decky-proton-pulse | ProtonDB badge and reports inside Decky. | Reference for ProtonDB API field handling. |

Gap. No existing tool replicates a non-Steam game device-to-device with its prefix, shortcut, artwork and compatibility tool, then keeps files and saves in sync with conflict handling.

---

## 4. Recommended Architecture

### 4.1 Process Model

| Option | Description | Verdict |
|---|---|---|
| A. All in Decky backend | Python `main.py` does discovery, transfer and sync. | Rejected. Dies with Decky restarts and Bazzite updates. No Desktop Mode presence. Python dependencies must be vendored into Decky's PyInstaller environment. |
| B. Standalone user daemon plus thin clients | `tandemd` runs as a systemd user service. Decky plugin, desktop web UI, tray icon and CLI are clients. | Recommended. Survives Decky failures, works in both modes, testable in isolation. |

Components:

- **`tandemd`** (user systemd service). Discovery, pairing, inventory, manifests, transfer engine, sync scheduler, save engine, snapshot store, audit log, local control API, embedded desktop web UI.
- **Decky plugin.** QAM panel, full-page library view, game page context menu entries, toasts. Executes Steam-side operations. `main.py` proxies calls to the daemon over a Unix socket and relays daemon events with `decky.emit`.
- **Desktop UI.** Single-page app served by `tandemd` on loopback. Tray icon via StatusNotifierItem (KDE Plasma on both SteamOS and Bazzite desktop).
- **`tandem-run`** launch wrapper. Pre-launch save pull, post-exit save push and change scan.
- **`tandem` CLI.** Scripting, diagnostics, recovery.

### 4.2 Steam Operations Executor

Steam-side changes (create shortcut, set exe and start dir, launch options, compatibility tool, artwork, icon, collections) are separated from file transfer.

- Received games land as files plus a **pending Steam registration** record.
- Primary executor. Decky frontend, using `SteamClient` APIs, applies pending operations when Gaming Mode is active.
- Desktop Mode. Operations queue and the UI shows "Registration completes in Gaming Mode".
- Fallback executor (Phase 3, consented). Stop Steam, write `shortcuts.vdf` and `config.vdf`, restart Steam.
- Spike (Phase 3). CEF DevTools Protocol executor against the desktop Steam client.

### 4.3 Language and Stack

| Component | Recommendation | Rationale |
|---|---|---|
| Daemon | Go | Single static binary with no runtime dependencies on an immutable OS. Strong concurrency and file I/O. Pure-Go TLS, mDNS, BLAKE3 and SQLite options. Systray library supports the Linux StatusNotifierItem protocol. |
| Decky frontend | TypeScript, React, `@decky/ui`, `@decky/api` | Current Decky standard. `decky-frontend-lib` is deprecated. |
| Decky backend | Python, stdlib only | Supervisor and proxy only. |
| Desktop UI | React SPA embedded in the daemon binary | One build, no webkit2gtk dependency, opens in the default browser or a browser app window. |
| State | SQLite (pure-Go driver) | Durable job journal, resumable transfers, audit log. |

### 4.4 Transfer Engine

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| rsync over SSH | Proven delta and resume. | Needs sshd enabled (root), key management, coarse progress, pause by process kill, no game-aware policy. | Rejected |
| Embedded Syncthing | Mature, TLS, discovery, block-level delta. | Continuous scanning of 50 to 150 GB game trees costs battery. Weak save semantics (`.sync-conflict` files). Poor fit for one-shot transfer UX, staged atomic apply and game-running awareness. | Rejected |
| Custom manifest engine | Full control of staging, atomicity, policy, pause, resume, conflict rules and UX. | More code to build and test. | **Recommended** |

Custom engine design:

- **Receiver-driven pull.** Sender publishes an offer. Receiver fetches the manifest, computes what it is missing and pulls chunks. Resume is trivial because the receiver always knows what it already holds.
- **Manifest.** Per file: relative path, size, mode, mtime, symlink target, BLAKE3 file hash, ordered chunk hashes. Manifest root hash identifies a version.
- **Chunks.** Content-addressed fixed 4 MiB chunks in Phase 1. FastCDC content-defined chunking in Phase 2 for better reuse when patches insert data.
- **Transport.** HTTP/2 over mutual TLS 1.3 with pinned peer certificates. Parallel chunk streams (default 4).
- **Staging.** New installs write to a staging directory, verify against the manifest root hash, then promote by atomic rename. Updates replace files atomically with the replaced originals held until the job completes, enabling rollback.
- **Controls.** Pause and resume per job and globally. Bandwidth cap. Persistent job journal in SQLite. Automatic resume after suspend, Wi-Fi loss or peer restart.
- **Integrity.** BLAKE3 per chunk on receipt, per file on completion, manifest root before promote. Any mismatch aborts the promote and keeps staging for retry.
- **Preflight.** Free space with margin, root mapping valid, compatibility tool present or obtainable, game not running on either device.

### 4.5 Identity and AppID Mapping

- Each replicated game gets a global `game_uuid` that never changes.
- Each device holds its own instance record: AppID, library root key, relative install path, exe, start dir, launch options, compatibility tool, prefix location, sync policies.
- Target flow. Create shortcut, apply `Set*` calls, read back and verify, move staged prefix into `compatdata/<new_appid>`, apply artwork, set compatibility tool.
- Alternative rejected for MVP. Forcing identical AppIDs by writing `shortcuts.vdf` with Steam stopped. Needs a Steam restart and is exposed to the `userdata/0` bug.

### 4.6 Path Translation

- **Library roots.** Named roots per device, for example `internal-games` mapped to `~/Games` and `sd-games` mapped to `/run/media/<user>/<label>/Games`. Manifests store paths relative to a root key.
- **Shortcut fields.** Exe, start dir and any absolute paths inside launch options (for example `STEAM_COMPAT_MOUNTS`) are rewritten using the root map.
- **Prefix contents.** Wine registry files reference absolute Linux paths via the `Z:` drive. Same Linux username and same root layout on both devices avoids rewriting. Phase 2 adds optional `.reg` path rewriting with correct Wine escaping.
- **Symlinks.** Preserved as symlinks, never followed. `dosdevices` links stay intact.
- **Case sensitivity.** Linux is case-sensitive, Wine is not. Detect case-only collisions in manifests and refuse rather than silently merge.

### 4.7 Sync Scopes

| Scope | Initial replication | Ongoing sync | Notes |
|---|---|---|---|
| Game install directory | Yes | Yes. Manual or Auto per game | Patches installed on either device propagate. Authoritative source per update. |
| Prefix (`compatdata/<appid>`) | Yes, filtered | Save paths only by default | Carries redistributables, registry and licence state. |
| Saves | Yes | Bidirectional, conflict-aware | See 4.8. |
| Device configs (graphics, resolution) | Optional, off by default | Never by default | Ludusavi manifest tags paths as save or config. Config paths are device-local. |
| Shortcut metadata | Yes | Yes | Name, exe, start dir, launch options, compat tool, icon, artwork, hidden flag. |
| Steam Input layout | Optional | Optional | Phase 2. |
| Collections | Optional | Optional | Phase 2. |
| Custom compatibility tool | Offered if missing on target | No | Copy the GE-Proton build folder from peer, or download with checksum verification. |
| Always excluded | | | `steamapps/shadercache/<appid>`, DXVK and VKD3D caches, Temp folders, crash dumps, logs. User-extensible exclude rules. |

### 4.8 Save Sync Model

- **Three-way comparison.** Each save set stores the hash of the last synced state (the base). Only one side changed since base, propagate. Both changed, conflict.
- **Version vectors, not mtimes.** Clock skew between handhelds makes mtime-only logic unsafe. mtime is a tiebreak hint only.
- **Conflicts.** Never auto-overwrite. Keep both, prompt the user with device, last played time and size, default to no action.
- **Snapshots.** Every overwrite is preceded by a snapshot. Retention default 10 per game. Restore from UI and CLI.
- **Lease.** A running game holds a lease on its save set. The peer refuses writes to that save set until the lease is released or expires.
- **Triggers.** `tandem-run` pulls before launch (default 10 s timeout, then launch offline with a warning) and pushes after exit. Periodic sync while both devices are online. Manual "Sync now".
- **Save path discovery.** Ludusavi manifest entries tagged as saves, user overrides, then learn-by-diff. Snapshot prefix user folders before launch, diff after exit, propose detected paths for confirmation.

### 4.9 Discovery, Pairing and Security

- **Discovery.** mDNS / DNS-SD service `_tandem._tcp`. Manual address fallback. USB4 direct link appears as another reachable address.
- **Pairing.** Time-boxed pairing window. 6-digit code shown on one device, entered on the other. Each device generates a self-signed certificate and pins the peer fingerprint. All peer traffic is mutual TLS.
- **Unauthenticated surface.** Discovery TXT record and the rate-limited pairing handshake only.
- **Local control API.** Unix socket with user-only permissions. Loopback HTTP for the desktop UI with a one-time login token issued by the tray. Never bound to LAN interfaces.
- **Path safety on receive.** Reject absolute paths, `..` segments and symlinks that resolve outside the target root. Write only within configured roots, Steam `compatdata`, `grid` and staging.
- **Least privilege.** Daemon runs as the desktop user. No Decky root flag. Firewall and NFS mounts are guided one-time actions, `pkexec` in Desktop Mode, copyable commands in Gaming Mode.
- **Secrets.** SteamGridDB key, SMB credentials and Rclone config stored with 0600 permissions. Redacted from logs and diagnostic bundles.
- **Audit log.** Append-only, hash-chained record of transfers, overwrites, snapshots, restores, pairings and policy changes.

### 4.10 Power and Network Policy

- Sleep inhibitor held during active transfers via logind.
- Pause below a battery threshold unless charging (default 30 percent).
- Pause or throttle while a game is running on either device (default pause).
- Bandwidth cap, default unlimited.
- Expected throughput (assumption, validate on the home network). Wi-Fi 6E device to device via one access point typically 40 to 120 MB/s. USB4 direct link limited by storage. microSD write speed is often the bottleneck for SD-hosted libraries.

---

## 5. Feature Set

### 5.1 Phase 1 (MVP)

1. Daemon with systemd user unit, SQLite state, local control API, CLI.
2. Steam inventory. Detect Steam root (native and Flatpak), account folders, `shortcuts.vdf` (read-only parse), `config.vdf` compat tool mapping, `compatdata`, grid artwork, library roots.
3. Discovery and pairing with pinned mutual TLS.
4. Manifest builder and receiver-driven chunk transfer with pause, resume, verification, staging and atomic promote.
5. "Send to peer" for one non-Steam game. Install dir, filtered prefix, artwork, shortcut metadata.
6. Target registration via Decky Steam Operations Executor with AppID re-keying.
7. Compatibility tool presence check, copy from peer if missing.
8. Decky QAM panel. Peers, queue, progress, pause, resume, cancel. Library page with per-game state.
9. Error taxonomy with clear, actionable messages.
10. Bazzite firewall check with guided fix.

### 5.2 Phase 2

1. Ongoing game file sync. Manual and Auto modes per game. Change scan triggered by `tandem-run` exit and periodic schedule.
2. Save sync with three-way logic, leases, snapshots and conflict UI.
3. Launch wrapper with pre-launch pull and post-exit push.
4. Save path discovery. Ludusavi manifest, overrides, learn-by-diff.
5. Desktop web UI and tray icon.
6. Game page context menu entries. Send, Sync now, Sync settings, Resolve conflict.
7. Path rewriting in `.reg` files for differing usernames or roots.
8. FastCDC chunking.
9. Steam Input layout and collection replication.
10. USB4 direct link detection and preference.

### 5.3 Phase 3

1. Installer assistant. Mount SMB via Rclone FUSE (no root) and NFS via guided one-time setup. Loop-mount ISO read-only with udisks. Map the mounted ISO as a CD drive letter in the prefix. Run the installer through a temporary shortcut with the chosen Proton. Exe-retarget assistant. See 6.2.
2. Ludusavi cloud import. Configure Rclone remote, list backups, map titles, restore into the target prefix using Ludusavi restore redirects.
3. Proton advisor and provisioning. See 6.3.
4. Graphics advisor with lsfg-vk integration. See 6.4.
5. Home lab hub peer. Headless `tandemd` in Docker on Proxmox acting as store-and-forward peer and backup target, so both handhelds need not be online together.
6. Offload and rehydrate. Remove local game files, keep shortcut stub, saves and prefix. Rehydrate from peer or hub on demand.
7. Verify and repair a game against a peer or hub.
8. Offline bundle export and import to USB storage.
9. Consented VDF fallback executor and CDP executor spike.
10. Optional uninstall propagation, off by default, explicit confirmation per game.

---

## 6. Evaluation of Requested Extras

### 6.1 Desktop Interface and Tray

- Feasible. Daemon-served SPA on loopback, tray icon via StatusNotifierItem.
- Tray menu. Open UI, pause all, resume all, peers online, active transfer progress, quit.
- Autostart via `~/.config/autostart` desktop entry.
- Steam-side registration from Desktop Mode queues until Gaming Mode. The UI states this clearly.

### 6.2 Remote ISO Install, Prefix Install and Exe Retarget

- **SMB.** Rclone `smb` backend mounted via FUSE as the user. No root. Rclone is also needed for Ludusavi cloud.
- **NFS.** Kernel NFS mounts need root. Provide a one-time guided systemd automount setup. Spike userspace NFS options.
- **ISO.** `udisksctl loop-setup -r` then mount. Fallback to extraction to a local temp folder if polkit refuses. UDF and ISO9660 both expected.
- **Proton visibility.** Add mount paths to `STEAM_COMPAT_MOUNTS` on the installer shortcut.
- **CD drive emulation.** Create `dosdevices/d:` pointing to the mount and set the Wine drive type to CD-ROM so installers expecting a disc drive behave.
- **Install target.** Recommend installing to a library root (for example `Z:\home\<user>\Games\<Title>`), not inside `drive_c`. Show the exact path to enter.
- **Exe retarget assistant.** Snapshot file lists before the installer runs. After exit, diff to find new executables. Rank candidates. Exclude uninstallers, redistributables, crash handlers and setup stubs. Weight by location, size and title similarity. User confirms. Same shortcut is retargeted so the prefix is retained.

### 6.3 Best Proton Version

Signal priority:

1. What already works on the source device. Replicate the exact compatibility tool to the target.
2. Steam store match for the title, then ProtonDB summary and recent Deck reports for commonly reported working versions.
3. Default to the latest installed GE-Proton for non-Steam titles.
4. Spike. GE-Proton protonfixes for non-Steam titles via umu database identifiers. Unverified, investigate before committing.

Provisioning. If the selected tool is missing, copy it from the peer or download from the official release with checksum verification.

### 6.4 Graphics Advice

- Advisory engine with per-device profiles. Panel resolution, refresh range, VRR, APU, RAM.
- Gen 1 profile. 2560x1600 IPS, no VRR, Z1 Extreme. Favour 1280x800 for clean integer scaling or 1920x1200 with upscaling.
- Gen 2 profile. 1920x1200 OLED, VRR, Z2 Extreme or Z2. Native or 1280x800 with upscaling, frame cap aligned to VRR range.
- Upscaling order. In-game upscaler first, gamescope scaling filter second.
- Frame generation. In-game frame generation if available. Otherwise lsfg-vk only when base frame rate is high enough to avoid visible artefacts (heuristic around 40 fps or more, tune with testing).
- Automated actions limited to what the plugin controls. Launch option chaining (for example `tandem-run ~/lsfg %command%`), per-game lsfg-vk profile. In-game settings are recommendations only.
- Data sources. PCGamingWiki for upscaler and frame generation support, ProtonDB notes. Optional LLM-generated advice is a later enhancement with an offline rule-based fallback.

---

## 7. Risks, Assumptions, Dependencies

### 7.1 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `SteamClient` APIs are undocumented and change with Steam updates | Registration breaks | Single adapter module, runtime feature probes, read-back verification, queued retries, VDF fallback |
| Decky breaks after Bazzite or SteamOS updates | Gaming Mode UI lost | Daemon is independent. Desktop UI and CLI remain usable |
| Save data loss from wrong overwrite | High user impact | Three-way logic, version vectors, mandatory snapshots, conflicts never auto-resolved |
| Prefix not portable across differing usernames or roots | Game fails on target | Strong recommendation for identical usernames and layouts, preflight check, Phase 2 `.reg` rewriting |
| Shader cache and DXVK cache mismatch between Z1E and Z2E | Stutter or corruption | Always excluded |
| Battery drain and heat during large transfers | Poor handheld experience | Battery threshold, pause while gaming, sleep inhibitor only while transferring |
| Wi-Fi client isolation or mesh roaming | Peers not discovered | Manual address fallback, reachability diagnostics, USB4 direct link |
| Bazzite firewall blocks inbound port | Pairing fails | First-run check with guided fix |
| Case-only path collisions | Silent file loss | Detect and refuse |
| Partial transfer promoted | Broken install | Staging plus manifest root verification before promote |
| ProtonDB API changes | Advisor degrades | Cache, timeouts, advisory only |
| Licence contamination from AGPL prior art | Licensing obligations | Clean-room implementation, no CapyDeploy code |
| Lossless Scaling DLL redistribution | Licence breach | Never transfer it. Each device obtains it via Steam |

### 7.2 Assumptions

- Both devices use the same Steam account.
- Same Linux username on both devices (strongly recommended, not enforced).
- Decky Loader installed on both devices.
- Same home LAN with peer-to-peer traffic permitted.
- Games are owned by the user and DRM-free or otherwise legitimately portable.
- SteamOS and Bazzite can be mixed across the two devices.

### 7.3 Dependencies

- Decky Loader 3.x, `@decky/ui`, `@decky/api`, `@decky/rollup`.
- Go toolchain, Node LTS, pnpm.
- Optional. Ludusavi (MIT), Rclone, `decky-lsfg-vk`, SteamGridDB API key, GE-Proton.

---

## 8. Decisions Required

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Product name | Choose before Slice 0. "Tandem" is a placeholder |
| D2 | Daemon language | Go |
| D3 | Transfer engine | Custom manifest engine |
| D4 | Username and layout policy | Identical usernames and root layouts on both devices |
| D5 | Default sync policy | Manual for game files, Auto for saves once Phase 2 ships |
| D6 | Root policy | No root in the daemon or Decky plugin. Guided one-time actions only |
| D7 | Hub peer scope | Phase 3 |
| D8 | Distribution | Private ZIP install first. Decky store submission later |

---

## 9. Sources

- Decky plugin template: https://github.com/SteamDeckHomebrew/decky-plugin-template
- decky-romm-sync shortcut reference: https://danielcopper.github.io/decky-romm-sync/architecture/steam-non-steam-shortcuts/
- Random shortcut AppIDs: https://github.com/Bestfast/Playnite-SISR-Helper/releases
- SteamTinkerLaunch AppID format: https://github.com/sonic2kk/steamtinkerlaunch/pull/902
- Steam `shortcuts.vdf` userdata bug: https://www.github.com/ValveSoftware/steam-for-linux/issues/10891
- CapyDeploy: https://pkg.go.dev/github.com/lobinuxsoft/capydeploy@v0.6.0
- Steam Local Network Game Transfers: https://www.engadget.com/steam-now-allows-you-to-copy-games-to-steam-deck-and-other-pcs-over-a-local-network-174444502.html
- Steam LAN transfer port and conditions: https://steamcommunity.com/discussions/forum/1/601892024948386896
- Legion Go 2 specifications: https://www.tomshardware.com/video-games/handheld-gaming/lenovo-brings-handheld-favorite-steamos-to-the-flagship-legion-go-2-the-amd-z2-extreme-gets-official-steamos-support-for-the-first-time
- Legion Go 2 vs Gen 1 comparison: https://insider-gaming.com/lenovo-legion-go-2-releases-in-october-starting-at-1100/
- USB4 networking throughput: https://community.frame.work/t/how-come-no-one-seems-to-have-tried-using-thunderbolt-for-40gbps-networking/75470?page=2
- USB4STREAM: https://phoronix.com/news/intel-linux-usb4stream
- Ludusavi: https://github.com/go8n/ludusavi
- decky-ludusavi: https://github.com/GedasFX/decky-ludusavi
- decky-lsfg-vk: https://github.com/xXJSONDeruloXx/decky-lsfg-vk
- lsfg-vk 2.0.0: https://steamdeckhq.com/news/lsfg-vk-lossless-scaling-huge-2-0-0-release/
- ProtonDB API fields: https://github.com/mdeguzis/decky-proton-pulse/wiki/On-Device-Test-Plan
- Bazzite Decky and handheld docs: https://docs.bazzite.gg/Handheld_and_HTPC_edition/Handheld_Wiki/
- Bazzite firewall behaviour: https://lemmy.klein.ruhr/post/121901/572862
- SyncDeck security notes: https://github.com/infernokun/SyncDeck/releases
- Syncthing and CEF port 8080 conflict: https://redlib.hbubli.cc/r/SteamDeck/comments/vocyi5/start_syncthing_automatically_on_steamdeck_even
- Installer retarget method: https://redlib.andus.dev/r/gog/s/LaHrx972f2
- `udisksctl` loop mounts: https://linuxize.com/post/how-to-mount-iso-file-on-linux/
- Lifecycle notification behaviour: https://github.com/AG69075/steamOS_plugin_achievements/releases
- SteamGridDB Decky plugin: https://github.com/SteamGridDB/decky-steamgriddb
