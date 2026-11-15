# Build plan

The full queue after the v2 consolidation (slice C0). v1 slices come from `docs/build-prompt.md` section 16, amended by `docs/build-prompt-v2.md` section 10. v2 slices come from `docs/build-prompt-v2.md` section 12. Every slice follows the working conventions in `CLAUDE.md`: its own branch, a pull request, a slice report, threat model and assumptions updated, and a stop for Peter's on-device checks.

## Status on 15 November 2026

| Slice | Branch | Pull request | State |
|---|---|---|---|
| 1 Skeleton, dev loop, diagnostics | `slice/01-skeleton` | #1 | merged, released in v0.1.0 |
| 2 Release pipeline and updater | `slice/02-release-updater` | #2 | merged, released in v0.2.0 |
| Release `--accept-untested` option | `chore/release-accept-untested` | #3 | merged |
| 3 Discovery | `slice/03-discovery` | #4 | open, awaiting on-device checks |
| 4 Manifest resolution and preview | `slice/04-manifest` | #5 | open, stacked on #4 |
| 5 Snapshot engine and safety rails | `slice/05-snapshots-clean` | #6 | open, stacked on #5 |
| 6 to 8 OneDrive store, sync engine, lifecycle | `slice/06-08-cloud-sync-lifecycle` | #7 | open, stacked on #6 |
| Cross-device matching (ADR-0011) | `feat/cross-device-matching` | #8 | open, stacked on #7 |
| Stable `Keepsake.zip` install URL | `feat/stable-latest-link` | #9 | open, based on `main` |
| C0 Consolidation (documentation only) | `slice/c0-consolidation` | this slice | open, stacked on #8 |

Merge order: #4, #5, #6, #7, #8, C0. #9 can merge at any time.

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
| 16 Replication spike | `slice/16-replication-spike` | On-device measurements: Python and TLS-PSK, `openssl`, stdlib mDNS, Wi-Fi throughput with SHA-256, CPU and battery, suspend | ADR selecting the transport; figures recorded; stop if throughput is unacceptable | |
| 17 Replication I | `slice/17-replication-1` | Listener (off by default), discovery, manual address, pairing, pinning, revoke, firewall guidance, peer UI | Pair, reconnect after reboot, reject an unpaired client; no socket when off | |
| 18 Replication II | `slice/18-replication-2` | Manifests, chunk pull, journal, staging, verification, promote, rollback, pause, resume, bandwidth cap, power policy, exclusions | Fault injection passes (drop mid-chunk, reload, disk full, corrupt chunk, peer restart, suspend). **Protocol frozen** | |
| 19 Replication III | `slice/19-replication-3` | Send a game end to end, source checkpoint, registration, app ID re-keying, compatibility tool copy, Saves adoption | An ISO game installed on one device launches on the other with the same tool, artwork and options; saves adopt silently; both directions | |
| 20 Replication IV | `slice/20-replication-4` | Ongoing sync policies, change scans, both-sides-changed handling, game page menu | A patch propagates under Manual and Auto; Replication never writes Saves paths (test) | minor (v1.2.0) |
| 21 Installer I | `slice/21-installer-1` | ISO and folder sources, installer shortcut, file snapshots, retarget assistant, cleanup | A GOG offline installer and an ISO installer complete from Gaming Mode, same prefix kept | |
| 22 Installer II | `slice/22-installer-2` | CD drive emulation, mounted network sources, SteamGridDB artwork, hand-off to Saves and Replication, network mount spike with options | | minor (v1.3.0) |
| 23 Desktop I | `slice/23-desktop-1` | Backend-in-Desktop-Mode check, loopback server, authentication, desktop SPA with parity, pending Steam operations | Every module usable from Desktop Mode on SteamOS and Bazzite; DNS rebinding and CSRF tests pass | |
| 24 Desktop II | `slice/24-desktop-2` | Tray, autostart entry, notifications, clean removal | Tray on login, opens the UI without a password, gone when disabled or uninstalled | |
| 25 v2 hardening and release | `slice/25-v2-hardening` | Full threat model review, 50-game performance check, VDF and manifest parser fuzzing, docs | Clean install from the release URL works on SteamOS and Bazzite with all modules | v2.0.0 |

Desktop (23 and 24) stays at the end of the feature queue, as Peter asked. Only the v2 hardening release follows it.

## Backlog (not scheduled)

From spec section 15: home lab hub peer, offload and rehydrate, offline USB bundles, content-defined chunking, USB4 direct link preference, `.reg` path rewriting, consented VDF fallback and CEF DevTools executors, optional uninstall propagation.
