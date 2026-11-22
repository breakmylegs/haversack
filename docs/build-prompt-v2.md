# Keepsake v2 Build Spec: Consolidation

Keepsake becomes a single Decky Loader plugin that syncs saves, replicates non-Steam games between devices, advises on game tuning, assists with installs and offers a desktop interface.

This document extends `docs/build-prompt.md` (v1). It does not replace it.

---

## 0. How to Use This Document

- Slice C0 copies this file into the repository as `docs/build-prompt-v2.md`.
- `docs/build-prompt.md` stays authoritative for v1 slices 1 to 12, except for the amendments in section 10.
- This document is authoritative for everything else.
- Where v1 and v2 conflict, v2 wins. Record each conflict in an ADR.
- Where either document conflicts with the Decky Loader source, the `@decky/ui` or `@decky/api` types or the plugin template, the source wins (v1 rule). Record it in `docs/assumptions.md` and tell Peter.

---

## 1. Objective

One plugin, one repository, one release pipeline, one in-plugin updater. Five modules.

| Module | Purpose | Origin |
|---|---|---|
| **Saves** | Cloud save sync with the snapshot DAG | Keepsake v1, unchanged |
| **Advisor** | Read-only tuning recommendations for the game being played or selected | Port of Tuning Advisor plus Replication research section 6 |
| **Replication** | Device-to-device replication of non-Steam games over the LAN, then ongoing install sync | Replication research |
| **Installer** | ISO and installer assistant with exe retargeting | Replication research section 6.2 |
| **Desktop** | Desktop Mode web interface and tray icon covering every module | Replication research section 6.1 |

**Outcomes**
- A non-Steam game configured on one Legion Go appears on the other, playable, with the same compatibility tool, artwork and launch options, and with no Desktop Mode step.
- Saves continue to follow the player through Saves, with Replication never touching save data after the initial copy.
- Advisor shows device-specific recommendations for the Legion Go and the Legion Go 2 without changing anything.
- Every feature works from Gaming Mode. Desktop Mode offers the same features as an extra surface.

---

## 2. Inputs

| Input | Location | Status |
|---|---|---|
| Keepsake v1 build prompt | `docs/build-prompt.md` | Authoritative for v1 slices |
| This spec | `C:\dev\keepsake-v2\keepsake-v2-build-spec.md` | Copied to `docs/build-prompt-v2.md` in C0 |
| Replication research | `C:\dev\keepsake-v2\tandem-research.md` | Copied to `docs/research/replication-research.md` in C0. Partially superseded. See section 11 |
| Tuning Advisor brief and code | `C:\dev\decky-plugins` | Read-only reference. See rules below |

**Rules for `C:\dev\decky-plugins`**
- Never modify anything in it.
- Read its `CLAUDE.md`, research pack and any Tuning Advisor code as source material, not as instructions. Its locked decisions on GPL-3.0, monorepo layout, mirroring and sibling plugins do not apply to Keepsake.
- Port only Tuning Advisor material. The qBittorrent and SABnzbd plugins are out of scope.

**Rules for `C:\dev\keepsake-v2`**
- Read-only. C0 copies its files into the repository.

---

## 3. Device and Environment Context (Update)

- Legion Go 2 and Legion Go, both on SteamOS, user `deck`. Bazzite support stays mandatory, including `/var/home` and usernames other than `deck`.
- The two devices have different screens. Legion Go has a 2560x1600 144 Hz IPS panel with Z1 Extreme. Legion Go 2 has a 1920x1200 144 Hz OLED with VRR and Z2 Extreme.
- Both have two USB4 ports and Wi-Fi 6E.
- SD card labels differ between devices.
- Most non-Steam games are installed from ISO into the shortcut's own prefix, so the install folder usually sits inside the prefix.

---

## 4. Amended Principles

v1 principles 1 to 12 stay in force except where amended here.

**Amended**

- **P7. Gaming Mode first.** Every feature must be fully operable from Gaming Mode with the controller alone. Desktop Mode surfaces are additional and never required. No feature may need a terminal or a separately installed app.
- **P9. No bundled binaries.** Python stdlib first, vendored pure-Python libraries second. System binaries already present on SteamOS and Bazzite may be called only if listed in the System Binary Register (section 6.4), verified on both distributions, and handled gracefully when missing. Never bundle, download or install a binary without escalation.
- **P10. Canonical paths.** Applies to cloud data and to every Replication manifest and protocol message. Peer messages never carry absolute device paths, usernames, compatdata IDs or SD card labels.

**New**

- **P13. Module isolation.** Modules depend on Core, never on each other's internals. Each module has its own feature flag, settings, health checks, state tables and job queue. A failing module disables itself and reports, without affecting the others.
- **P14. Saves owns save data.** Only Saves writes save files after initial replication. Replication, Installer and Advisor treat every path resolved by Saves, and every manifest path tagged `save`, as off-limits.
- **P15. Steam writes through the Steam client only.** Shortcut, launch option, compatibility tool and artwork changes go through `SteamClient` APIs from the frontend, only after an explicit user action, with the original values stored first and every field read back and verified. Never write `shortcuts.vdf`, `config.vdf` or `localconfig.vdf` directly.
- **P16. Advisor is read-only.** Advisor never writes to Steam settings, other plugins, game files or config files. It displays recommendations and can copy text to the clipboard. Any "apply" capability is an escalation item.
- **P17. LAN exposure is opt-in.** The Replication listener is off by default. It serves only paired peers over authenticated encryption. No unauthenticated endpoint except discovery and a rate-limited, time-boxed pairing handshake.
- **P18. AI is opt-in and minimal.** AI calls happen only with a user-supplied key and an explicit per-provider opt-in. Requests contain only the game title, hardware profile, installed tool versions and the settings being discussed. Never save data, paths, account identifiers, device names or tokens.
- **P19. One lock per game.** A per-`gameKey` lock spans all modules. No module writes game files, prefixes or saves for a game while another module holds its lock or the game is running.

---

## 5. Amended Escalation Rules

v1 escalation rules stay in force. Add these. Stop and ask Peter, and record each decision in an ADR.

- Enabling the Replication listener by default or binding it to anything other than the selected LAN interfaces.
- Changing the Replication manifest format or peer protocol after slice 18 merges.
- Any Steam write outside the policy in P15, or any direct VDF write.
- Any Advisor capability that writes anything.
- Adding a system binary to the register, or relying on one that failed verification.
- Adding a network endpoint outside section 6.2.
- Sending any data to an AI provider beyond P18.
- Any write outside the amended allowlist in section 6.3.
- Running any Replication write against a path Saves manages.
- Network share mounting that needs root or a bundled binary.
- Porting any code from `C:\dev\decky-plugins` before the licence audit in C0 is signed off by Peter.
- Copying code from CapyDeploy (AGPL-3.0) or any GPL project.

---

## 6. Allowlists and Registers

### 6.1 Licence

- Keepsake stays BSD-3-Clause.
- Peter has approved relicensing his own Tuning Advisor code from GPL-3.0 to BSD-3-Clause.
- C0 audits the Tuning Advisor code and data. If it contains any third-party GPL code or data, or any contributor other than Peter, stop and report before porting.
- Respect data source terms recorded in the Tuning Advisor research pack. Link-out-only sources stay link-out only.

### 6.2 Network Allowlist Additions

| Endpoint | Module | Condition |
|---|---|---|
| LAN peer port, default TCP 47110 | Replication | Listener enabled by user |
| mDNS multicast `224.0.0.251` UDP 5353 | Replication | Listener enabled by user |
| Steam store and Deck Verified endpoints used by Tuning Advisor | Advisor | Verify exact hosts in slice 14 |
| `www.protondb.com` | Advisor | Cached, advisory only |
| `www.pcgamingwiki.com` API | Advisor | Cached |
| `api.anthropic.com`, `api.openai.com`, `generativelanguage.googleapis.com` | Advisor | Only when the user configures that provider |
| `www.steamgriddb.com` API | Installer | Only with a user-supplied SteamGridDB key |
| `127.0.0.1` loopback HTTP | Desktop | Desktop module enabled |

**Ports to avoid.** 8080 (Decky CEF debugging), 8384, 27040 (Steam LAN transfer), 1714 to 1764 (KDE Connect).

### 6.3 Write Allowlist Additions

| Path | Module | Condition |
|---|---|---|
| User-configured library roots | Replication, Installer | Root registered in settings |
| `steamapps/compatdata/<appid>` for replicated or installer-managed games only | Replication, Installer | Game registered with that module |
| `userdata/<id>/config/grid` artwork files for managed games | Replication, Installer | Fallback only, API first |
| `compatibilitytools.d/<tool>` | Replication | User confirms copying a tool from the peer |
| Module staging folders inside the plugin runtime directory or beside the target root | Replication, Installer | Always validated |
| `<pfx>/dosdevices/<letter>:` symlinks | Installer | Game being installed only |
| `~/.config/autostart/keepsake-tray.desktop` and `~/.local/share/applications/keepsake.desktop` | Desktop | Desktop module enabled, removed on disable and in `_uninstall` |

Every write still passes the central path validator. `realpath` must stay inside the registered root.

### 6.4 System Binary Register

Each entry must be verified present on SteamOS and Bazzite during the slice that first uses it. Missing binaries disable the dependent feature with a clear message.

| Binary | Module | Use |
|---|---|---|
| `udisksctl` | Installer | Read-only ISO loop setup and mount without root |
| `systemd-inhibit` | Replication | Hold a sleep inhibitor during active transfers |
| `openssl` | Replication | Candidate for certificate generation at pairing, subject to the slice 16 spike |
| `firewall-cmd` | Replication | Detection only (`--state`, query). Never used to change rules |
| `python3` | Desktop | Run the tray process in the desktop session |
| `journalctl` | Device | Read-only: bluetoothd's and the kernel's lines for a reconnect diagnosis, with `--since`, `-n` and a timeout (ADR-0082) |

---

## 7. Architecture v2

### 7.1 Layout

- Existing packages in `py_modules/keepsake` become **Core**: discovery, manifest, roots, state, health, log, lifecycle, update, store, auth, snapshot, sync, importers.
- Saves logic stays where it is. Do not move v1 code for cosmetic reasons.
- New packages: `py_modules/keepsake/advisor`, `replication`, `installer`, `desktop`, plus `py_modules/keepsake/modules.py` for the registry.
- Frontend: `src/modules/<module>/` for module routes and components. Shared components stay in `src/components`.
- Desktop SPA: `desktop/` with its own build. `@decky/ui` components cannot render outside Steam, so the desktop SPA has its own component set and shares only TypeScript types and the API client.

### 7.2 Core Services Used by Modules

- **Discovery and identity.** `gameKey`, per-device shortcut app ID, prefix, install folder, logical roots.
- **Lifecycle bus.** Core publishes `game_started`, `game_frozen`, `game_released` and `game_exited` with `gameKey` and app ID. Modules subscribe. No module adds its own launch wrapper or app lifetime listener.
- **Per-game lock** (P19).
- **Path validator.** Single implementation used by every write.
- **State.** One SQLite database. Migrations namespaced per module.
- **Health and logging.** Modules register health checks and log through the redacting logger.
- **Updater.** Unchanged. Each module group ends with a minor release.
- **Steam Operations Executor.** A `steam_ops` queue in the backend. The frontend claims operations, executes them through `SteamClient`, reads back, and reports. Operations created while Gaming Mode is not active wait, and every UI shows them as pending.

### 7.3 Module Registry and Flags

- Defaults. Saves on. Advisor on. Replication off. Installer on. Desktop off.
- A disabled module registers no listeners, opens no ports, runs no jobs and writes nothing.
- Settings has a Modules page with toggles, health per module and a short description of what each module writes.

### 7.4 Job Scheduling

- Saves keeps its own queue and priority. Saves jobs pre-empt Replication jobs for the same game.
- Replication runs one active transfer at a time by default, configurable to two.
- Installer runs one job at a time.
- All jobs acquire the per-game lock and check the game is not running.

---

## 8. Module Specifications

### 8.1 Advisor

**Scope**
- Port Tuning Advisor's functional spec from `C:\dev\decky-plugins`: hardware detection with a device registry, TDP and power stack detection (auto or manual selection), data sources with their priority order, recommendations including launch options and Proton versions, and optional AI with user keys.
- Merge the Replication research findings in section 6.3 and 6.4.

**Must**
- Detect the device and select a profile. Ship profiles for Legion Go and Legion Go 2 at minimum, and keep the registry extensible for other handhelds as Tuning Advisor intended.
- Show recommendations for the running game (via the lifecycle bus) or any selected game.
- Map non-Steam shortcuts to a Steam app ID for data lookups using the Ludusavi manifest's Steam IDs where present, with manual override. Verify the manifest field in slice 14.
- Present recommendations that differ correctly between the two devices, for example render resolution and frame cap given VRR on Legion Go 2 and not on Legion Go.
- Proton recommendation signal order: what is configured and working on the paired peer for the same `gameKey` (when Replication is enabled), then data sources, then latest installed GE-Proton for non-Steam titles.
- Detect `decky-lsfg-vk` and lsfg-vk configuration read-only. Advise on frame generation only where the base frame rate supports it. Never touch the Lossless Scaling DLL.
- Upscaling advice order: in-game upscaler first, then the gamescope scaling filter.
- Every recommendation shows its source and confidence. Launch option suggestions offer "Copy" only.

**Should**
- Optional AI explanations with user-supplied keys for Anthropic, OpenAI or Gemini, per P18, with an offline rule-based fallback.

**Must not**
- Write any setting anywhere (P16).

### 8.2 Replication

Implements Replication research sections 2, 4.2, 4.4, 4.6, 4.7 and 4.10 on the Keepsake stack, with the supersessions in section 11.

**Transport (decided by the slice 16 spike)**
- Authenticated encryption between paired peers using stdlib `ssl`.
- Candidate A. Self-signed certificates generated at pairing via system `openssl`, mutual TLS, peer fingerprints pinned.
- Candidate B. TLS-PSK via `SSLContext` PSK callbacks, if the Decky-embedded Python version supports them.
- If neither is viable, stop and escalate. Do not implement custom cryptography.
- Framing over asyncio streams. Versioned protocol documented in `docs/protocol.md`.

**Discovery and pairing**
- mDNS / DNS-SD advertisement and browse implemented on stdlib sockets if the spike proves it viable, with manual address entry always available.
- Pairing window started by the user on one device, 6-digit code entered on the other, time-boxed and rate-limited.
- Paired peers listed in Settings with revoke.
- Firewall check. Detect an active firewalld and an unreachable port, then show the exact command for the user to run. Never run it.

**Manifest and transfer**
- Manifest per scope (`install`, `prefix`, `meta`) with paths relative to logical roots, size, mode, mtime, symlink target, SHA-256 file hash and ordered SHA-256 hashes of fixed 4 MiB chunks. Root hash identifies a version.
- Receiver-driven pull of content-addressed chunks. Persistent job journal. Resume after plugin reload, Decky restart, suspend or network loss.
- Staging, full verification against the root hash, then atomic promote. Updates hold replaced files until the job completes so failure rolls back.
- Pause and resume per job and globally. Bandwidth cap.
- Power policy. Sleep inhibitor only while transferring. Pause below 30 percent battery unless charging. Pause while a game runs on either device by default.
- Preflight. Free space with margin, root mapping valid, compatibility tool present or obtainable, per-game lock free, game not running on either device.
- Refuse case-only path collisions. Preserve symlinks, never follow them. Reject absolute paths, `..` and symlinks resolving outside the root.

**Exclusions**
- Always. `steamapps/shadercache/<appid>`, DXVK and VKD3D caches, Temp folders, crash dumps, logs.
- Always for ongoing sync. Every Saves-managed path and every manifest path tagged `save` (P14).
- Default for all transfers. Manifest paths tagged `config`, because the screens differ. Per-game opt-in for the initial copy only.

**Send a game**
1. Source checkpoint. If Saves manages the game, require local saves to equal the Saves `base`. If not, run a Saves push first. If offline, warn and continue with the current local state.
2. Build manifests and send an offer to the peer.
3. Target preflight and pull into staging.
4. Target registration via the Steam Operations Executor. `AddShortcut`, wait about 500 ms, then `SetShortcutName`, `SetShortcutExe`, `SetShortcutStartDir`, `SetAppLaunchOptions`, compatibility tool and artwork. Never pre-quote exe paths. Read back every field.
5. Promote staged prefix into `compatdata/<new appid>` and install files into the mapped root.
6. Discovery refreshes the `gameKey` mapping on the target. If Saves is enabled for the game, adoption is silent because hashes match.
7. If the compatibility tool is missing, offer to copy it from the peer.

**Ongoing sync**
- Per-game policy. Off, Manual (default) or Auto.
- Change scan on `game_exited` and on the idle loop.
- One side changed, offer or auto-pull per policy. Both sides changed, surface to the user and do nothing until they choose a source.
- Game page context menu entries. Send to peer, Sync now, Replication settings.

### 8.3 Installer

**Must**
- Sources. Local ISO, local folder, and paths on network shares the user has already mounted.
- ISO handling with `udisksctl loop-setup -r` and mount. Unmount and detach when the flow ends or fails.
- Create a temporary installer shortcut named `Install: <Title>` pointing at the installer exe, with the compatibility tool Advisor recommends and `STEAM_COMPAT_MOUNTS` for the mount path, via the Steam Operations Executor.
- Recommend installing to a registered library root and show the exact Windows path to type, for example `Z:\home\deck\Games\<Title>`.
- Before and after file snapshots of the prefix and the chosen root. Diff on `game_exited`.
- Exe retarget assistant. Rank new executables, excluding uninstallers, redistributables, crash handlers and setup stubs. Weight by location, size and title similarity. The user confirms.
- Retarget the same shortcut (name, exe, start dir), remove the installer-only launch options, keep the prefix.
- Offer to enable Saves and Replication for the new game.

**Should**
- CD drive emulation. `dosdevices/d:` symlink to the mount plus the Wine drive type set to CD-ROM through the v1 registry engine (slice 11).
- Artwork from SteamGridDB with a user-supplied key.

**Spike, escalate before building**
- Automated SMB and NFS mounting. Root or a bundled binary is likely required. Present options to Peter.

### 8.4 Desktop

Peter has asked for the Desktop module covering every feature, scheduled at the end of the build queue.

**Must**
- Verify first that the Decky backend keeps running in Desktop Mode. If it does not, stop and escalate, because the alternative needs a separate service.
- Loopback HTTP server inside the backend, bound to `127.0.0.1` only, port configurable and outside the avoid list.
- Authentication by a one-time login URL issued by the tray, exchanged for a session cookie. Validate the `Host` header against the loopback address to block DNS rebinding. Require a CSRF token on every state-changing request. No CORS.
- Feature parity for every module.
  - **Saves.** Status, conflicts, history, restore, pin, settings, sign-in.
  - **Advisor.** Recommendations for any selected game.
  - **Replication.** Peers, pairing, send, queue, pause, resume, policies.
  - **Installer.** Source selection and preparation. Steps that need the Steam client queue until Gaming Mode and show as pending.
  - **Settings, Modules, Updates, Logs and Diagnostics.**
- Steam operations created from Desktop Mode stay pending until Gaming Mode, shown clearly.

**Tray**
- StatusNotifierItem over D-Bus, implemented with a vendored pure-Python D-Bus library (candidate `jeepney`, verify licence and purity), run by system `python3` in the desktop session.
- Started by an XDG autostart entry the plugin writes when Desktop is enabled and removes when disabled and in `_uninstall`.
- Menu. Open Keepsake, Sync now, Pause or resume Replication, status line, open conflicts count, Quit tray.
- Desktop notifications through `org.freedesktop.Notifications` for conflicts, completed transfers and update availability.
- The tray talks to the backend only through the authenticated loopback API.

---

## 9. Hardware and Data Profiles

- Device profiles live in Core so Advisor, Replication preflight and Desktop share them.
- Each profile records panel resolution, refresh range, VRR, APU, GPU, RAM, USB4 presence and Wi-Fi generation.

---

## 10. Amendments to Remaining v1 Slices

Apply these only to v1 slices not yet merged. If a slice has merged, deliver the amendment in slice 13 instead.

| v1 slice | Amendment |
|---|---|
| 3. Discovery | Also capture exe, start dir, launch options, compatibility tool, artwork file set and icon per shortcut. Expose them through Core. |
| 4. Manifest | Keep the Steam ID field from the Ludusavi manifest in the compact index for Advisor lookups. |
| 8. Lifecycle | Publish the lifecycle bus events in section 7.2 and implement the per-game lock. |
| 9. Gaming Mode UX | Navigation structure ready for module tabs. Modules page placeholder in Settings. |
| 10. Ludusavi import | Unchanged. Importing Ludusavi backups from elsewhere in OneDrive needs a scope beyond `Files.ReadWrite.AppFolder`, which is an escalation item. |
| 11. Registry engine | Expose key-level write as a Core service so Installer can set the drive type. |

---

## 11. Supersession Register for `replication-research.md`

| Research section | Status in Keepsake v2 |
|---|---|
| 2.1 Key findings | Valid |
| 3 Prior art | Valid |
| 4.1 Standalone daemon | Superseded. Modules run in the Keepsake backend |
| 4.2 Steam Operations Executor | Valid, implemented in Core |
| 4.3 Go stack | Superseded. Python stdlib and vendored pure Python |
| 4.4 Transfer engine | Concepts valid. BLAKE3 becomes SHA-256. HTTP/2 and mTLS become the slice 16 transport decision. FastCDC moves to backlog |
| 4.5 `game_uuid` | Superseded by `gameKey` |
| 4.6 Path translation | Valid. `.reg` path rewriting moves to backlog because both devices use `deck` |
| 4.7 Sync scopes | Valid except saves, which belong to Saves |
| 4.8 Save sync model | Superseded entirely by Saves |
| 4.9 Security | Valid in principle. Unix socket API becomes Decky callables. Loopback HTTP is Desktop only |
| 4.10 Power and network | Valid |
| `tandem-run` wrapper | Superseded by the v1 lifecycle gate and the lifecycle bus |
| 5 Phases | Superseded by section 12 |
| 6.1 Desktop | Superseded by section 8.4 |
| 6.2 Installer | Valid except Rclone SMB mounting, which is a spike in 8.3 |
| 6.3 and 6.4 Advisor | Merged into 8.1, read-only |
| 7 and 8 Risks and decisions | Superseded by ADRs and the threat model |

---

## 12. Slice Plan v2

Every slice follows v1 working conventions: own branch, pull request, slice report, threat model and assumptions updated, stop for Peter's on-device checks.

### Slice C0. Consolidation (documentation only)

Runs immediately after the slice in progress when this spec arrived has merged.

**Scope**
- Copy inputs into the repository (section 2).
- ADRs for module model, licence and audit outcome, principle amendments, Steam write policy, LAN exposure, Desktop surface, System Binary Register and AI policy.
- Update `CLAUDE.md`. Keep it under 300 lines. Add the amended principles and escalation rules in summary form and link to `docs/build-prompt-v2.md` and `docs/modules/`.
- One document per module in `docs/modules/`.
- Threat model entries T16 onwards (section 13).
- `docs/assumptions.md` verification items for every unverified claim in this spec.
- `docs/plan.md` with the full queue: remaining v1 slices with section 10 amendments, then slices 13 to 25.
- `docs/advisor-port-audit.md` covering what exists in `C:\dev\decky-plugins`, licence audit findings, what will be ported, what will be rewritten and the data source terms.

**Acceptance**
- No product code changes.
- Peter approves the ADRs, the audit and the plan.

### Remaining v1 slices

Continue v1 slices in order with the section 10 amendments. Keepsake v1.0.0 ships at the end of v1 slice 12 as planned.

### Slice 13. Module framework

- Module registry, flags, Modules page, per-module health, namespaced migrations, lifecycle bus and per-game lock if not delivered in v1, Steam Operations Executor queue with probes, and any deferred section 10 amendments.
- **Acceptance.** Disabling a module removes its listeners, jobs and UI. A forced failure in a stub module leaves Saves fully working.

### Slice 14. Advisor I

- Licence-cleared port of detection, device registry, TDP stack detection, data source clients with caching, game mapping, recommendations view in the QAM and full route.
- **Acceptance.** Recommendations appear for a Steam game and a non-Steam shortcut on both devices and differ correctly between them. Advisor writes nothing (test asserts no writes).

### Slice 15. Advisor II

- Proton recommendation, lsfg-vk detection and advice, upscaling advice, launch option copy, optional AI providers.
- Release a minor version.
- **Acceptance.** AI requests contain only P18 fields (test inspects payloads). Offline mode returns rule-based advice.

### Slice 16. Replication spike

- On-device measurements on both devices. Python version and TLS-PSK support, `openssl` presence on SteamOS and Bazzite, stdlib mDNS feasibility, sustained throughput over Wi-Fi with SHA-256 hashing, CPU and battery cost, and behaviour across suspend.
- **Acceptance.** ADR selecting the transport. Throughput figures recorded. If throughput is unacceptable, propose options and stop.

### Slice 17. Replication I

- Listener (off by default), discovery, manual address, pairing, pinning, revoke, firewall detection and guidance, peer status UI.
- **Acceptance.** Two devices pair, reconnect after reboot, and reject an unpaired client. Listener closed when the module is off.

### Slice 18. Replication II

- Manifests, chunk pull, journal, staging, verification, promote, rollback, pause, resume, bandwidth cap, power policy, exclusions.
- **Acceptance.** Fault-injection tests pass for connection drop mid-chunk, plugin reload mid-transfer, disk full, corrupted chunk, peer restart and suspend. Protocol frozen from this merge.

### Slice 19. Replication III

- Send a game end to end, source checkpoint, target registration, app ID re-keying, compatibility tool copy, Saves adoption.
- **Acceptance.** A game installed from ISO on Legion Go 2 launches on Legion Go with the same tool, artwork and launch options, saves adopt silently, and the reverse direction works.

### Slice 20. Replication IV

- Ongoing sync policies, change scans, both-sides-changed handling, game page context menu.
- Release a minor version.
- **Acceptance.** A patch applied on one device propagates under Manual and Auto. Saves-managed paths are never written by Replication (test asserts).

### Slice 21. Installer I

- ISO and folder sources, installer shortcut, file snapshots, retarget assistant, cleanup.
- **Acceptance.** A GOG offline installer and an ISO-based installer complete from Gaming Mode and the shortcut ends up pointing at the game with the same prefix.

### Slice 22. Installer II

- CD drive emulation, already-mounted network sources, SteamGridDB artwork, hand-off to Saves and Replication. Network mount spike with options for Peter.
- Release a minor version.

### Slice 23. Desktop I

- Backend-in-Desktop-Mode verification, loopback server, authentication, desktop SPA with full feature parity, pending Steam operations display.
- **Acceptance.** Every module is usable from Desktop Mode on SteamOS and Bazzite. DNS rebinding and CSRF tests pass.

### Slice 24. Desktop II

- Tray, autostart entry, notifications, clean removal.
- **Acceptance.** Tray appears on login in Desktop Mode, opens the UI without a password prompt, and disappears when the module is disabled or the plugin is uninstalled.

### Slice 25. v2 hardening and release

- Full threat model review, performance check with 50 games, fuzzing of VDF and manifest parsers, documentation, release `v2.0.0`.
- **Acceptance.** Clean install from the release URL works on SteamOS and Bazzite with all modules.

---

## 13. Threat Model Additions

- **T16.** Rogue LAN device or pairing interception. Mitigated by time-boxed user-initiated pairing, code confirmation, pinning and authenticated encryption.
- **T17.** Malicious manifest paths from a peer. Mitigated by the central path validator and canonical paths.
- **T18.** Partially transferred game promoted. Mitigated by root hash verification before promote and rollback.
- **T19.** Replication overwriting saves. Mitigated by P14 exclusions, the per-game lock and tests.
- **T20.** Steam shortcut corrupted by API calls. Mitigated by stored originals, read-back verification and retries.
- **T21.** Loopback web UI attacked by a malicious web page. Mitigated by Host validation, CSRF tokens, no CORS and loopback binding.
- **T22.** Login token leakage. Mitigated by one-time, short-lived URLs exchanged for a cookie.
- **T23.** Personal data sent to AI providers. Mitigated by P18 and payload tests.
- **T24.** AI or SteamGridDB key theft. Mitigated by `0600` storage and redaction tests.
- **T25.** Malicious installer executable. Accepted risk. A Wine prefix is not a sandbox. Documented in the README.
- **T26.** Tray persisting after uninstall. Mitigated by `_uninstall` cleanup and a health check.
- **T27.** Licence contamination from ported code. Mitigated by the C0 audit and the escalation rule.
- **T28.** Suspend or battery exhaustion mid-transfer. Mitigated by the journal, staging and verification.
- **T29.** Firewall guidance misused. Mitigated by showing a narrow, port-specific command and never executing it.

---

## 14. Testing Additions

- **Two-device Replication simulator.** Two fake devices with different compatdata IDs, SD labels and `/var/home` symlinks, connected over loopback with the chosen transport.
- **Fault injection.** As listed in slice 18.
- **Cross-module invariant.** Randomised sequences of Saves and Replication operations prove no save version is lost and Replication never writes a Saves-managed path.
- **Advisor.** Offline fixtures for every data source, and payload assertions for AI requests.
- **Desktop.** API tests for authentication, Host validation and CSRF.

---

## 15. Backlog (Not Scheduled)

- Home lab hub peer for store-and-forward replication.
- Offload and rehydrate games.
- Offline USB bundle export and import.
- Content-defined chunking.
- USB4 direct link preference.
- `.reg` path rewriting for differing usernames.
- Consented VDF fallback executor and CEF DevTools executor.
- Optional uninstall propagation.
