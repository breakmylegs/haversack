# ADR-0047: Post-v2 roadmap

- Status: accepted (Peter's R0 request, 17 November 2026; decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

Peter gave a candidate backlog of 32 items from market research. The sources were Decky Cloud Save, SDH-GameSync, decky-ludusavi, Ludusavi, EmuSync, Syncthing, Heroic, NonSteamLaunchers, Junk-Store, Storage Cleaner, CryoUtilities, MoonDeck, Steam's LAN transfer and SteamOS 3.8.

Each item was checked against:
- the current code;
- the principles (especially P7 Gaming Mode first, P9 no bundled binaries, P16 Advisor read-only and P18 minimal AI) and the threat model;
- primary sources.

It was then built, deferred or rejected. Accepted items become slices R1 to R6 in `docs/plan.md`. Anything that changes a principle or the frozen cloud layout gets its own ADR when it is built.

## Primary sources consulted (18 November 2026)

- **Dropbox:**
  - the OAuth Guide (developers.dropbox.com/oauth-guide) says apps that cannot keep a secret, including desktop apps without a server, should use PKCE;
  - the Dropbox blog "PKCE: what and why";
  - Dropbox staff on the developer forum confirm PKCE works with or without a redirect URI.
- **pCloud:**
  - the API documentation (docs.pcloud.com, OAuth 2.0 `authorize` and `oauth2_token`) offers a token flow for client-side apps and a code flow that needs the client secret, with no PKCE;
  - a third-party helper reports that creating new apps is disabled.
- **Decky:** the plugin database submission rules (wiki.deckbrew.xyz, "Submitting plugins"; the decky-plugin-template README):
  - a licence file;
  - the template licence kept at the bottom;
  - pnpm 9;
  - submission as a pull request adding a submodule;
  - review by the Decky team, with the store's CI building the plugin.
- **Steam Support, "Local Network Game Transfers"** (help.steampowered.com):
  - it copies only Steam game content between Steam clients on a LAN;
  - saves, Workshop, Cloud and shader files are excluded;
  - there is no API for other programs.
- **SimpleDeckyTDP:** its repository documents no interface for other plugins. Its README shows control through its own bundled `ryzenadj` binary.
- **Redump:** no public statement of licence or redistribution terms for its DAT files was found. Some DATs are reported as available to members only.
- **Pure-Python authenticated encryption:**
  - the stdlib has no AES or ChaCha20;
  - `purecrypt` (0BSD) and `chacha20poly1305` (licence not stated in the sources found) are pure Python, and their own pages warn they are not constant-time.
- **MangoHud README:** `output_folder`, `log_duration` and `log_interval` exist. The CSV column set is not documented in the README, and `log_versioning` changes the format.
- **SteamOS 3.8:**
  - press coverage (Engadget, GamingOnLinux) reports initial Steam Machine support and Desktop Mode on Wayland;
  - no source confirms Decky Loader on the Steam Machine.
- **Heroic:** GOG cloud saves exist and are off by default per game (Heroic 2.4.0 release notes and coverage). The setting's key in Heroic's configuration is not documented in the sources found.

## Decisions

| # | Item | Decision | Where | Reasoning |
|---|---|---|---|---|
| 1 | Better conflict screen | Build | R1 | The details call already returns sides and changed counts. Add each side's last-changed time (not "now"), device and a per-file added, removed and changed list. Never auto-pick (P4). Playtime comes with 12. Thumbnails are deferred: no reliable per-game source, and Steam screenshots are item 11. |
| 2 | Continue where you left off | Build | R2 | Suspend snapshots exist (ADR-0022, off by default). Add a cloud-head check in the idle loop, plus "Newer save from <device>, 10 min ago" on the game row and in the QAM, with the existing pull before launch. |
| 3 | Named checkpoints | Build | R1 | Manual snapshots and pins exist. Add a label, a QAM "Save checkpoint" button while playing, and restore in two presses with the usual pre-restore snapshot. |
| 4 | End-to-end encryption | Defer | own ADR, after v2.0.0 | The stdlib has no authenticated cipher. Vendorable pure-Python ones are not constant-time, and their licences are partly unconfirmed. It changes the frozen cloud layout, which is an escalation item. Needs its own ADR weighing the options (for example a stdlib-only HMAC-SHA-256 counter-mode stream cipher, or a vendored, audited AEAD). |
| 5 | Cloud integrity check | Build | R3 | A periodic scrub verifies blob hashes and reports in plain words. Write-once forbids repairing in place, so "repair" offers a fresh snapshot from a device holding the same content (P2). |
| 6 | No lock-in export | Build (zips), defer (Ludusavi layout) | R3 | Export snapshots as plain zips with a JSON index to a folder the user chooses (USB or SD), new files only, never overwriting. That is a new write location, decided here as allowed after an explicit user action. Ludusavi's layout needs absolute paths that canonical roots do not keep, so it is deferred. |
| 7 | Partial restore | Build | R1 | The restore engine takes a file filter, with a preview and a pre-restore snapshot of the affected files (P3). |
| 8 | More cloud backends | Dropbox: build when registered; pCloud: reject | R6b | Dropbox supports PKCE and an "App folder" access type, the same model as OneDrive. It needs Peter's app registration and two endpoints added (`api.dropboxapi.com`, `content.dropboxapi.com`), approved here when built. pCloud has no PKCE, its code flow needs the secret, and new app registration is reported closed. |
| 9 | Emulator saves | Build | R4 | RetroArch's save folder comes from `retroarch.cfg`, plus the EmuDeck standalones' folders. Battery and memory-card saves only. Save states are optional and off. A new game kind ("emulator system") that needs a device check of EmuDeck paths. |
| 10 | Heroic, Lutris and Bottles | Build | R4 | Read their game lists (JSON or YAML in their own folders) and resolve saves through the prefix as for Proton. Heroic's own GOG/Epic cloud sync key is unverified, so it is treated like Steam Cloud "unknown": ask before enabling. |
| 11 | Steam screenshots | Defer | | Personal media adds storage and privacy weight, and Steam already uploads screenshots. Showing the nearest local screenshot in the conflict screen may come with item 1 later. |
| 12 | Combined playtime | Build | R2, own ADR | Session lengths come from lifecycle events. Storing them adds a write-once cloud object per session (`games/<key>/sessions/<deviceId>/<seq>.json`), a layout addition decided in its own ADR. |
| 13 | Safe storage cleaner | Build | R5 | Per-game disk use. Clear the shader cache with confirmation (a new write location, allowed here after a user action). "Reset prefix, keep saves" as in 14. |
| 14 | Prefix backup and repair | Build (reset, keep saves), defer (whole-prefix backup) | R5 | Reset: snapshot the saves, move the prefix aside, let Proton recreate it, restore the saves, then remove the old prefix. Whole-prefix backups are gigabytes and wait for Replication's chunk engine. |
| 15 | Offload and rehydrate | Defer | after slice 20 | Needs Replication's transfer engine (slices 18 and 19). |
| 16 | Peer wake-up | Build | slice 17 | A Wake-on-LAN magic packet is a stdlib UDP broadcast, with BIOS and NIC guidance and online status in the peer list. It only sends; it never listens (P17). |
| 17 | Steam LAN transfer for Steam games | Explain only | slice 19 | Steam does this itself and offers no API. The Replication screen says Steam games use Steam's own transfer, and Keepsake handles non-Steam games. |
| 18 | SteamOS 3.8 and the Steam Machine | Build (no-battery behaviour), defer (profile) | R2 | Devices without a battery skip battery rules, and Advisor shows no TDP advice without a profile. A Steam Machine profile and a Decky check wait for hardware and Valve's specifications. |
| 19 | Playnite extension and Heroic hooks | Defer | | A Playnite extension is a .NET assembly (P9), or a script extension whose future in Playnite is unclear. The PC host already pushes after exit (ADR-0041). Pre-launch pull on Windows is revisited after v2.0.0. |
| 20 | Learn from MangoHud | Defer | after v2.0.0 | Reading logs is allowed (P16), but the CSV format is undocumented and versioned. Sharing results with peers needs Replication. |
| 21 | Optional Apply | Reject for now | | SimpleDeckyTDP offers no API. Applying through its bundled `ryzenadj` would mean running a binary (P9, ADR-0018) and would break P16. Revisit only if a tuning tool publishes an API, with its own ADR. |
| 22 | Multi-disc installs | Build | R6 | The emulated CD drive is a `dosdevices` link (ADR-0027). "Swap to disc 2" repoints it in place. Needs a device check. |
| 23 | Redump verification | Reject | | DAT licence and redistribution terms are unconfirmed, and some DATs are members only (an escalation item for unconfirmed licences). |
| 24 | Install queue | Build | R6 | Sequential installs, with the queue in the Installer's state so it resumes after a reboot. |
| 25 | Runtime check | Build | R6 | Detect redistributable installers shipped with the game (`_CommonRedist`, `vcredist*`, `DXSETUP.exe`, `dotNetFx*`) and guide the user to run them through the game's shortcut. Nothing is bundled or downloaded (P9). |
| 26 | Search, bulk actions and Activity | Build | R1 | The desktop interface has search. Add search and bulk on/off to the Gaming Mode Games page and both interfaces, plus a plain-words Activity list from the event log. |
| 27 | Localisation and accessibility | Build (accessibility), defer (i18n) | R2 | Icon plus text for every status, larger-text support and consistent controller hints are cheap. An i18n framework is a large change with no translators yet. |
| 28 | First-run tips and What's new | Build | R2 | `take_startup_notice` exists. Ship the changelog's section in the package and show it once after an update. Short tips on first open. |
| 29 | Battery- and network-aware sync | Defer | | Saves are small. Metered detection needs NetworkManager over D-Bus, so it is revisited after the D-Bus client (ADR-0045). The battery rule applies to Replication. |
| 30 | Decky Plugin Store | Prepare | R3 | Keepsake already meets the rules (licence, template notice, pnpm 9, no binaries). R3 adds a submission checklist. The pull request to the plugin database comes from Peter's account. Store-installed copies update through the store; the GitHub URL stays. |
| 31 | SBOM, reproducible builds, key runbooks, SECURITY.md | Build | R3 | `SECURITY.md` exists; R3 adds the reporting route. A CycloneDX SBOM (from the lockfile and the vendored wheels) becomes a release asset listed in `SHA256SUMS`. Reproducible-build steps go in (the package is already deterministic), plus key rotation and compromise runbooks in `docs/releasing.md`. |
| 32 | Performance budget | Build | R3 | A synthetic benchmark (500 games, 10,000 snapshots) for matching, history, retention planning and status, with time budgets, as a quick gate step. It merges slice 25's 50-game check into a stricter one. |

## Slices

- **R1 Save safety and control:** items 1, 3, 7 and 26.
- **R2 Everyday polish:** items 2, 12 (with its own layout ADR), 18 (no battery), 27 (accessibility) and 28.
- **R3 Trust and distribution:** items 5, 6 (zips), 30 (prepare), 31 and 32.
- **R4 Coverage:** items 9 and 10, with device checks.
- **R5 Storage:** items 13 and 14 (reset, keep saves), with device checks.
- **R6 Installer III:** items 22, 24 and 25, with device checks.
- **R6b Dropbox:** item 8, when Peter registers the app.
- **Into existing slices:** item 16 into slice 17, and item 17 into slice 19.

R1 to R3 need no device, so they are built now, while slices 16 to 25 wait for device runs (ADR-0037). R4 to R6 are built after them, with their device checks listed for Peter.

## Consequences

- Rejected items (pCloud, Optional Apply, Redump) are recorded with their reasons, so they are not proposed again without new facts.
- Deferred items keep their place in the plan's backlog with the condition that would bring them back.
