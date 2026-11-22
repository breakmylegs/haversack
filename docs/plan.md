# Build plan

The full queue after the v2 consolidation (slice C0). v1 slices come from `docs/build-prompt.md` section 16, amended by `docs/build-prompt-v2.md` section 10. v2 slices come from `docs/build-prompt-v2.md` section 12. Every slice follows the working conventions in `CLAUDE.md`: its own branch, a pull request, a slice report, threat model and assumptions updated, and a stop for Peter's on-device checks.

## Status on 18 November 2026

Released up to v0.24.0. Merged since, not yet released: network install (#38 to #41), the ProtonDB index source, P1 to P5, S1, S2, D1, R0, R1 to R6, slice 17a and the built-in sign-in clients (ADR-0055). The next release now needs only the device checks.

| Slice | State |
|---|---|
| 12 Hardening and v1.0.0 | merged; v1.0.0 waits for the release signing key, the security review sign-off and clean installs |
| 13 Module framework, 14 and 15 Advisor, 21 and 22 Installer | merged and released |
| P1 to P5, S1, S2, D1, R0, R1 to R6 | merged; device checks in each slice report |
| R6b Dropbox | waits for Peter's Dropbox app registration |
| 16 Replication spike | no longer a gate (ADR-0054): its figures become tuning input from the device runs |
| 17 Replication I | built: 17a (link, pairing, peers, ADR-0054) and 17b (discovery, Wake-on-LAN, addresses, pages, ADR-0056); waits for the device checks |
| 18 Replication II | built: 18a (engine, ADR-0057) and 18b (adaptive streams, several sources, sleep inhibitor, battery and game holds, transfers manager and progress, protocol frozen; ADR-0058); waits for the device checks |
| 19 Replication III | built: 19a (send a game, ADR-0059) and 19b (Send buttons, offers on Devices, the user guide); waits for the device checks |
| 20 Replication IV | built: 20a (ADR-0060) and 20b (controls); the minor release waits for the device checks |
| R7 direct save sync | built (ADR-0061, `docs/slices/r7-report.md`); waits for the device checks |
| 23 Desktop I | step 0 (A79 probe) waits for device runs |
| 24 Desktop II | after 23 |
| 25 v2 hardening | parser fuzzing done; the rest after the other slices |
| Network install follow-ons (ADR-0033, ADR-0034) | HTTP, HTTPS, SMB and WebDAV built; NFS needs a mount; SFTP not offered (needs a compiled library or a binary); the network probe waits for device runs |
## Peter's queue of 21 November 2026

Each item is merged on its own and then published as its own signed **stable** release, a new minor version per feature (`docs/releasing.md`, release cadence; Peter's second instruction of 21 November 2026 replaced pre-releases). 0.27.0-beta.1 and -beta.2 were published before that and are superseded by 0.27.0.

| Item | State |
|---|---|
| R8 Steam games sync like non-Steam games (ADR-0063) | merged (#81), in 0.27.0 |
| R9 Games you can stream from another device (ADR-0064) | merged (#82), in 0.27.0; the hide tidy-up waits for the device run (A201) |
| R10 Uninstall (ADR-0065) | merged (#83), in 0.27.0 |
| R11 Find Windows shares (ADR-0066) | merged (#84), in 0.27.0 |
| R12 Network ISOs in place (ADR-0067) | merged (#85), in 0.27.0; the in-place mount for shares that are not mounted waits for Peter's approval of `fusermount3` |
| R13 Desktop app with the plugin, in the tray (slices 23 and 24 brought forward) | merged (#88), in 0.27.0 |
| R14 Advisor session stats (ADR-0069) | in 0.28.0 |
| R15 Pairing by code (ADR-0070) | in 0.29.0 |
| R16 Several save locations, step 1 (ADR-0071) | in 0.30.0; step 2 (take the newest save, clock guard, Undo) is queued below |
| Tray freeze hotfix (r17 report) | in 0.30.1 |
| Three fixes: offers that stall, sign-in localhost page, raw SMB errors (r18 report) | in 0.30.2 |

Peter's new direction of 21 November 2026 sets the order from here:

| Item | State |
|---|---|
| R19 Replication both ways: two-way pairing, space check, no Accept, pull, progress bars on every surface, Stop and remove on either side, toasts (ADR-0072) | in 0.31.0; Send's wording fixed in 0.31.1 |
| R20 Layout review: `docs/design/layout-v3.md`, an ADR, and the new structure for the quick access menu, the full page and the desktop app, every feature still reachable (ADR-0073) | this release, 0.32.0 |
| R21 Legion Go device control (stage 1, read-only readings, ADR-0074, in 0.33.0; research `docs/research/legion-control.md` and the permission ADR-0075, with tier 1 waiting for Peter; stage 2, performance profiles, ADR-0076, in 0.34.0; stage 3, fans, waits for the tier 1 decision; stage 4, battery charge limit (R17), ADR-0077, in 0.35.0; stage 5, controllers read-only, ADR-0078, in 0.36.0; stage 6, Wi-Fi power saving and the BIOS check, ADR-0079, in 0.37.0. Fans and the root parts wait for Peter's decision on ADR-0075 tier 1), after research (`docs/research/legion-control.md`) and a permission-model ADR. In stages, each a release: read-only status; TDP and per-game profiles; fans; battery (R17 folds in here); controllers and RGB; display and other features. Anything needing root waits for Peter's approval of the permission ADR | next |
| R16 step 2 Take the newest save (ADR-0080) | in 0.38.0 |
| R18 Library badges and artwork for streaming tiles (ADR-0081) | in 0.39.0 |
| Sidebar fix (ADR-0073 addendum) | 0.39.1 |
| Static sidebar, one entry per tab, focus and reload rules, navigation recorder (ADR-0073 addendum) | 0.41.1 |

Peter's decisions and priorities of 22 November 2026 (ADR-0075 tier 1 approved; `fusermount3` approved). The order:

| Item | State |
|---|---|
| R22 Controller reconnect help, without root (ADR-0082; generic for Bluetooth Classic controllers, the DualShock 4 as the first cable provider): device list, passive detection, Reconnect assist (also in the quick menu), pair and commit, diagnosis from D-Bus and the journal, the USB stored-host read, report bundle | in 0.40.0 |
| R23 The root helper (ADR-0075 tier 1, ADR-0083), first jobs for reconnect help: HCI capture, cable pairing through providers with a confirmed bluetoothd restart and Restore backup, the opt-in SSP gate | in 0.41.0 |
| R24 The desktop app's reconnect help page (in 0.42.0); separate SPL, SPPT and FPPT (in 0.43.0, ADR-0084); fan control (in 0.44.0, ADR-0085); in-place network ISOs (in 0.45.0, `fusermount3` approved); next, the helper's other jobs: fan control (every feature of the fan plugins Peter uses), separate SPL, SPPT and FPPT, RGB, controller settings, the power LED; in-place network ISOs (`fusermount3`) | queued |
| R25 Quick menu shortcuts (ADR-0073 addendum) | in 0.46.0 |
| R26 Emulator games between devices, with emulators, EmuDeck, firmware, BIOS and keys | queued |
| R27 The rename (name search and ADR), with a new full-colour logo and icons | queued |
| R28 README and in-app Help rewrite, kept in step with each release from then on | queued |
| R29 Research every Decky plugin (`docs/research/decky-plugins.md`), then the plugin feature stages: looks (themes, sounds, animations), library extras, performance and display, utilities, launchers and stores | queued |

## Section 10 amendments: where each is delivered

Spec section 10 applies amendments to v1 slices not yet merged, and moves them to slice 13 for merged slices. Slices 3, 4 and 8 are complete and awaiting on-device checks, but not merged. Reopening them would invalidate checks already prepared, so their amendments are delivered as follows (decision under Peter's delegation; c0-report Q6 lets him reverse it).

| v1 slice | Amendment | Delivered in |
|---|---|---|
| 3 Discovery | Also capture exe, start dir, launch options, compatibility tool, artwork file set and icon per shortcut, exposed through Core. Exe and start dir are already captured | 13 |
| 4 Manifest | Keep the Ludusavi Steam ID in the compact index | already in slice 4 (`manifest.py` stores it), nothing to do |
| 8 Lifecycle | Publish the lifecycle bus events and implement the per-game lock | 13 |
| 9 Gaming Mode UX | Navigation ready for module tabs; Modules page placeholder in Settings | 9 |
| 10 Ludusavi import | Unchanged. Any scope beyond `Files.ReadWrite.AppFolder` stays an escalation item | 10 |
| 11 Registry engine | Expose key-level write as a Core service for Installer's drive type | 11 |

## Queue

### Remaining v1 (Keepsake v1.0.0 at the end of slice 12)

| Slice | Branch | Scope | Release |
|---|---|---|---|
| 9 Gaming Mode UX complete | `slice/09-gaming-mode-ux` | Build prompt section 14 UX, game config revisions in the cloud (A64), plus navigation for module tabs and a Modules placeholder | |
| 10 Ludusavi import and cutover | `slice/10-ludusavi-import` | Build prompt section 19, unchanged | |
| 11 Registry engine | `slice/11-registry-engine` | Build prompt registry merge, plus key-level write as a Core service | |
| 12 Hardening and v1.0.0 | `slice/12-hardening` | Threat model sign-off, minisign verification in the updater (T10 gap), performance, docs | v1.0.0 |

### v2 (Keepsake v2.0.0 at the end of slice 25)

| Slice | Branch | Scope | Acceptance (summary) | Release |
|---|---|---|---|---|
| 13 Module framework | `slice/13-module-framework` | Registry, flags, Modules page, per-module health, namespaced migrations, lifecycle bus, per-game lock, Steam Operations Executor with probes, the deferred slice 3 and 8 amendments | Disabling a module removes its listeners, jobs and UI; a forced failure in a stub module leaves Saves working | |
| 14 Advisor I | `slice/14-advisor-1` | Licence-cleared port: detection, device registry in Core, stack detection, data sources with caching, game mapping, QAM and full route | Recommendations for a Steam game and a shortcut on both devices, differing correctly; Advisor writes nothing (test) | |
| 15 Advisor II | `slice/15-advisor-2` | Proton recommendation, lsfg-vk advice, upscaling advice, copy launch options, optional AI | AI payloads hold only P18 fields (test); offline rule-based advice | minor (v1.1.0) |
| 16 Replication spike (no longer a gate, ADR-0054) | `slice/16-replication-spike` | On-device measurements: Python and TLS-PSK, `openssl`, stdlib mDNS, Wi-Fi throughput with SHA-256, CPU and battery, suspend; plus (ADR-0045) throughput with and without TLS at 256 KiB and 4 MiB reads, hashing speed, one versus parallel streams, a Tailscale direct and relayed link, and the logind sleep inhibitor as `deck` | ADR selecting the transport; figures recorded; stop if throughput is unacceptable | |
| 17 Replication I | `slice/17-replication-1` | Listener (off by default), discovery, manual address, pairing, pinning, revoke, firewall guidance, peer UI | Pair, reconnect after reboot, reject an unpaired client; no socket when off; a manual or VPN address works; TLS compression off and checked (ADR-0045) | |
| 18 Replication II | `slice/18-replication-2` | Manifests, chunk pull, journal, staging, verification, promote, rollback, pause, resume, bandwidth cap, power policy, exclusions | Fault injection passes (kill mid-chunk, power loss with unsynced writes, network drop, reload, disk full, corrupt chunk, peer restart, suspend, a stop at every phase leaving no files); durable journal; resume re-verifies only possibly incomplete chunks; "Stop and remove" separate from Pause; free-space check and preallocation; sleep inhibitor; no cloud and no compression (ADR-0045). **Protocol frozen** | |
| 19 Replication III | `slice/19-replication-3` | Send a game end to end, source checkpoint, registration, app ID re-keying, compatibility tool copy, Saves adoption | An ISO game installed on one device launches on the other with the same tool, artwork and options; saves adopt silently; both directions; a stop removes every shortcut, registration, compatdata and tool copy the job made; progress, MB/s and ETA in the QAM and game page (ADR-0045) | |
| 20 Replication IV | `slice/20-replication-4` | Ongoing sync policies, change scans, both-sides-changed handling, game page menu | A patch propagates under Manual and Auto; Replication never writes Saves paths (test); cross-OS targets (long paths, invalid names, case, exec bits) (ADR-0045) | minor (v1.2.0) |
| 21 Installer I | `slice/21-installer-1` | ISO and folder sources, installer shortcut, file snapshots, retarget assistant, cleanup | A GOG offline installer and an ISO installer complete from Gaming Mode, same prefix kept | |
| 22 Installer II | `slice/22-installer-2` | CD drive emulation, mounted network sources, SteamGridDB artwork, hand-off to Saves and Replication, network mount spike with options | | minor (v1.3.0) |
| 23 Desktop I | `slice/23-desktop-1` | Backend-in-Desktop-Mode check, loopback server, authentication, desktop SPA with parity, pending Steam operations | Every module usable from Desktop Mode on SteamOS and Bazzite; DNS rebinding and CSRF tests pass | |
| 24 Desktop II | `slice/24-desktop-2` | Tray, autostart entry, notifications, clean removal | Tray on login, opens the UI without a password, gone when disabled or uninstalled | |
| 25 v2 hardening and release | `slice/25-v2-hardening` | Full threat model review, 50-game performance check, VDF and manifest parser fuzzing, docs | Clean install from the release URL works on SteamOS and Bazzite with all modules | v2.0.0 |

Desktop (23 and 24) stays at the end of the feature queue, as Peter asked. Only the v2 hardening release follows it.

### Re-plan for PCs and laptops (ADR-0038, 17 November 2026)

Keepsake now targets Decky handhelds, Linux PCs with or without Decky, and Windows PCs:
- **One core, three hosts.** The same `keepsake` package runs inside Decky or as a headless `keepsake.host` on a PC.
- **One desktop UI.** It is the slice 23 single-page app, served on loopback. Handhelds use it in Desktop Mode, and PCs use it as their main UI.

The device-free work moves ahead of slices 16 to 25 and is built in this order (ADR-0037):

| Item | Scope | Needs a device? |
|---|---|---|
| P1 Platform layer | Host detection; Windows known folders; the `windows` save layout; case-insensitive Windows matching; `<osUserName>`; then Steam discovery on Windows (registry `SteamPath`, `libraryfolders.vdf`) and the registry root through `winreg` | No: built and tested on the Windows laptop. Real Steam games need a PC run. |
| P2 Headless host | `python -m keepsake.host`: `KeepsakeApp` without Decky, with platform settings and state folders (`%APPDATA%\Keepsake`, `$XDG_CONFIG_HOME/keepsake`) and the loopback API with token authentication, DNS-rebinding and CSRF protection (slice 23's server, moved forward) | No |
| P3 Desktop UI | Slice 23's single-page app (plain TypeScript, ADR-0040), served by the host, with parity for Saves first. Built: Overview, Conflicts, Games, Cloud, Import, History, Health, Modules, Updates and Settings (`docs/slices/p3-report.md`) | No for the build, screenshots and tests. Yes for Desktop Mode on a handheld (the A79 probe). |
| P4 PC lifecycle | A process watcher: push after a game exits, "Sync now" and idle pulls while nothing runs | No for the logic. Yes for real games. |
| P5 PC package and self-update | `Keepsake-desktop-v<version>.zip` in the signed `SHA256SUMS`, self-update (verify, unpack into a versioned folder, switch, keep the previous one), autostart (Startup folder, XDG autostart or a systemd user unit) | No for the build and tests. Yes for a PC install run. |

What changes in the remaining slices:

| Slice | Change |
|---|---|
| 16 to 18 Replication | Unchanged. The protocol stays platform-neutral (canonical paths, P10). |
| 19 Replication III | Adds endpoint translation for PCs: Proton prefix to and from native Windows folders, the exe mapping, and registry entries from `user.reg` into `HKCU` (with its own ADR). Shortcuts on hosts without Decky are added by the user, following on-screen steps (P15). |
| 20 Replication IV | Policies for PC peers. |
| 23 Desktop I | Most of it moves to P2 and P3. What stays is the Desktop Mode check on handhelds and pending Steam operations. |
| 24 Desktop II | Tray and notifications on all three hosts; autostart moves to P5. |
| 25 v2 hardening | Adds a clean install on a Windows PC and a Linux PC, as well as SteamOS and Bazzite. |

Advisor is off by default and hidden on PCs. Installer stays Decky only (ADR-0038).

### Owner requirements (Peter, 17 November 2026)

These two come before R0. S1 is next after the PC self-update change. Each is recorded in its own ADR, and the research is checked against primary sources first.

| Item | Scope | Rule |
|---|---|---|
| S1 One-button cloud sign-in | Authorization code with PKCE (S256) and an RFC 8252 loopback redirect: a one-shot listener on 127.0.0.1 on a random port, with a checked `state` and a timeout. The browser opens itself: the default browser on a PC and in Desktop Mode, Steam's browser in Gaming Mode where the provider allows it. Otherwise "Sign in on your phone" with a QR code, and device code is kept as the fallback. Tokens refresh silently. Client IDs only appear under Advanced. Also: an ADR on "one sign-in for all devices", ADR-0032's registration steps updated, and a Steam browser probe for the Legion Go 2. | Built (ADR-0044, `docs/slices/s1-report.md`). The client IDs are in (ADR-0055); it waits for the Legion Go 2 probe run, which sets the Gaming Mode defaults. |
| S2 Replication direct-only requirements | Hard requirements for slices 16 to 20:<br>- never through cloud storage or a relay (with a test);<br>- no compression at any layer (`OP_NO_COMPRESSION` asserted and tested);<br>- pause and resume with a durable journal and automatic recovery;<br>- "Stop and remove" cleans up everything;<br>- free-space checks, preallocation and sleep inhibition;<br>- speed and progress UI, and a bandwidth cap;<br>- cross-OS targets;<br>- fault injection tests.<br>Updates `docs/modules/replication.md`, the threat model and the slice plans, plus an ADR and the slice 16 device steps. | Recorded (ADR-0045, `docs/slices/s2-report.md`): the requirements are in the module document, the threat model and slices 16 to 20 above; the no-cloud and no-compression rules are enforced by tests now. The rest is built in slices 16 to 20. |

### After slice 25 (Peter, 17 November 2026)

| Item | Scope | Rule |
|---|---|---|
| D1 User documentation | Detailed user docs on GitHub with screenshots and diagrams:<br>- Getting started for each device type;<br>- a guide per feature, privacy and an FAQ;<br>- automated screenshots from a frontend harness with sample data, with a personal-data check;<br>- Mermaid or SVG diagrams;<br>- a release-time step that regenerates screenshots and checks links and images.<br>Where it lives and how it is published is decided in its own ADR. | Built (ADR-0046, `docs/slices/d1-report.md`). Screenshots are regenerated at each release. |
| R0 Post-v2 roadmap (Peter, 17 November 2026) | A candidate backlog of 32 items from market research, not a spec:<br>- A: save sync and safety;<br>- B: coverage;<br>- C: storage and prefixes;<br>- D: multi-device;<br>- E: Advisor;<br>- F: Installer;<br>- G: UX and accessibility;<br>- H: distribution and security.<br>For each item: check the code (skip or shrink what exists), the principles (P7, P9, P18) and the threat model; research primary sources; decide build, defer or reject in one ADR, "Post-v2 roadmap". Accepted items become new slices here, and anything that changes a principle gets its own ADR. The full list is in the request of 17 November 2026, recorded in that ADR. | Decided (ADR-0047): the slices below. |

### Post-v2 roadmap slices (ADR-0047)

R1 to R3 need no device, so they are built now, while slices 16 to 25 wait for device runs. R4 to R6 follow, with device checks.

| Slice | Items | Device? |
|---|---|---|
| R1 Save safety and control | Better conflict screen (times, devices, per-file changes), named checkpoints from the QAM, partial restore with preview, search and bulk actions on Games, Activity list. Built (ADR-0048, `docs/slices/r1-report.md`) | No |
| R2 Everyday polish | Newer save from another device shown before launch, combined playtime (own layout ADR), no-battery devices, accessibility (icon plus text, larger text, controller hints), What's new and first-run tips. Built (ADR-0049, `docs/slices/r2-report.md`) | No |
| R3 Trust and distribution | Cloud integrity scrub, zip export to a chosen folder, Decky store readiness, SBOM and key runbooks, performance budget in the gate. Built (ADR-0050, `docs/slices/r3-report.md`); the store submission needs Peter | No |
| R4 Coverage | Emulator saves (RetroArch, EmuDeck), Heroic, Lutris and Bottles games. Built (ADR-0051, `docs/slices/r4-report.md`); waits for the device checks | Yes, at the end |
| R5 Storage | Per-game disk use, clear shader cache, reset prefix and keep saves. Built (ADR-0052, `docs/slices/r5-report.md`); waits for the device checks | Yes, at the end |
| R6 Installer III | Multi-disc swap, install queue, runtime check. Built (ADR-0053, `docs/slices/r6-report.md`); waits for the device checks | Yes, at the end |
| R6b Dropbox | Dropbox with PKCE and an app folder | Needs Peter's app registration |
| R7 Direct save sync (ADR-0054, Peter's option C) | Saves go device to device over Replication's link with no cloud account, under Saves' own snapshot and conflict rules. Built (ADR-0061, `docs/slices/r7-report.md`) | Yes, at the end |

Also: Wake-on-LAN joins slice 17, and the Steam LAN transfer explanation joins slice 19.

## Backlog (not scheduled)

- Deferred by ADR-0047, each with the condition that brings it back:
  - end-to-end encryption (its own ADR after v2.0.0);
  - Steam screenshot sync;
  - offload and rehydrate (after slice 20);
  - the Playnite extension and Heroic hooks;
  - learning from MangoHud;
  - an i18n framework;
  - battery- and network-aware sync (after the D-Bus client);
  - the Ludusavi-layout export;
  - whole-prefix backups.
- Rejected by ADR-0047: pCloud, Optional Apply, Redump verification.

- Done: the Advisor data sources deferred from slice 15 (ADR-0029): PCGamingWiki (ADR-0031) and the ProtonDB monthly-dump index (ADR-0035). The index needs a monthly refresh by hand (`docs/releasing.md`).
From spec section 15: home lab hub peer, offload and rehydrate, offline USB bundles, content-defined chunking, USB4 direct link preference, `.reg` path rewriting, consented VDF fallback and CEF DevTools executors, optional uninstall propagation.
