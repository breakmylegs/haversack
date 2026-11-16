# Assumptions and verified facts

Each entry is **verified** (read in source or type definitions, or measured on device) or **unverified** (to be confirmed). Sources: decky-loader at commit `ffd103b` (26 October 2026, the v3.3.1 release), decky-plugin-template at `90d0780`, `@decky/api` 1.1.3, `@decky/ui` 4.16.5.

## Decky Loader and Python

| # | Fact | Status | Source |
|---|---|---|---|
| A1 | Current stable Decky Loader is v3.3.1 (27 October 2026) | verified | GitHub releases |
| A2 | Decky Loader is built with Python 3.14.8 (PyInstaller), so plugins run on 3.14 | verified in source, **unverified on device** (Diagnostics page reports it) | `.github/workflows/build.yml` |
| A3 | `aiohttp` 3.14 is a Decky dependency, so it is probably importable from plugin processes | unverified, Diagnostics reports it | `backend/poetry.lock` |
| A4 | Decky sets `DECKY_PLUGIN_SETTINGS_DIR`, `_RUNTIME_DIR`, `_LOG_DIR`, `_DIR`, `_NAME`, `_VERSION` (from `package.json`), `_AUTHOR`, `DECKY_USER`, `DECKY_USER_HOME`, `DECKY_HOME`, `DECKY_VERSION` before importing `main.py`. Settings, runtime and log folders are named after the plugin folder | verified | `plugin/sandboxed_plugin.py` |
| A5 | With `api_version: 1` Decky instantiates `Plugin()` and calls methods with positional arguments (`callable` in `@decky/api`) | verified | `sandboxed_plugin.py` lines 117 to 132, 200 to 210 |
| A6 | The plugin process drops to the host user unless `root` is in `flags` | verified | `sandboxed_plugin.py` `setuid` |
| A7 | `py_modules` is appended to `sys.path` | verified | `sandboxed_plugin.py` line 91 |
| A8 | `DECKY_PLUGIN_VERSION` comes from `package.json`, so `package.json` can be the single version source with no version in `plugin.json` | verified | `sandboxed_plugin.py`, template |
| A9 | `sqlite3` and `ssl` are available in the embedded Python | unverified, Diagnostics reports it | |
| A10 | Stdlib `urllib` with `ssl.create_default_context()` can verify TLS on device. Decky itself uses `certifi` through `get_ssl_context`, so the default CA paths may be missing in the frozen build | unverified, Diagnostics "Test HTTPS" reports it | `helpers.get_ssl_context` |

## Install and update hand-off (input to ADR-0002)

| # | Fact | Status | Source |
|---|---|---|---|
| A11 | Decky's Developer page "Install plugin from URL" calls the websocket route `utilities/install_plugin` with `(url, name)`; version defaults to `dev` | verified | `frontend/src/store.tsx` `installFromURL` |
| A12 | `utilities/install_plugin(artifact, name, version, hash, install_type)` does not install directly; it emits `loader/add_plugin_install_prompt`, so Decky shows its own confirmation and only installs on `utilities/confirm_plugin_install` | verified | `backend/decky_loader/utilities.py`, `browser.py` `request_plugin_install` |
| A13 | If `hash` is non-empty Decky compares it with the SHA-256 of the downloaded zip and refuses to install on mismatch | verified | `browser.py` `_unzip_to_plugin_dir` |
| A14 | When `version` is not `dev`, Decky POSTs an install-count increment to the Decky store server (`plugins.deckbrew.xyz` by default). When `version` is `dev`, it instead reads the plugin name from the zip's `plugin.json` | verified | `browser.py` `_install` |
| A15 | `window.DeckyBackend` (a `WSRouter`) is a global in the Steam UI context, so a plugin frontend can call `window.DeckyBackend.call("utilities/install_plugin", ...)`. It is not part of the typed `@decky/api` surface | verified in source, **unverified from a plugin** (Diagnostics "Frontend facts" reports it) | `frontend/src/index.ts` line 50 |
| A16 | The "plugin update API" in Decky Loader 3.3.0 (PR 992) is a store-side update check in `store.tsx` to reduce server load. It is **not** a plugin-facing install API. **Differs from the build prompt**, which suggested it as a hand-off option | verified | PR 992 file list |
| A17a | An update runs `uninstall_plugin` first, which calls the plugin's `_unload` and `_uninstall` hooks, then deletes only the plugin folder. Settings, runtime and log folders survive, provided `_uninstall` does not delete them | verified | `browser.py` v3.3.1 `uninstall_plugin` |
| A17 | Decky extracts the zip with `ZipFile.extractall` into the plugins folder and expects one top-level folder containing `plugin.json` | verified | `browser.py` |

## Steam client APIs (input to ADR-0001)

| # | Fact | Status | Source |
|---|---|---|---|
| A18 | `SteamClient.GameSessions.RegisterForAppLifetimeNotifications(cb)` gives `{unAppID, nInstanceID, bRunning}` | verified types, unverified payload for shortcuts | `@decky/ui` `GameSessions.d.ts` |
| A19 | `SteamClient.Apps.RegisterForGameActionStart(cb(gameActionId, appId: string, action, launchSource))` | verified types, unverified payload | `@decky/ui` `App.d.ts` |
| A20 | `SteamUIStore.MainRunningApp`, `MainRunningAppID` and `RunningApps` exist | verified types | `steamuistore/index.d.ts` |
| A21 | `SteamClient.System.RegisterForOnSuspendRequest` and `RegisterForOnResumeFromSuspend` exist | verified types, unverified firing | `system/index.d.ts` |
| A22 | `SteamClient.Apps.GetLaunchOptionsForApp` and `SetAppLaunchOptions` exist (for slice 8) | verified types only | `App.d.ts` |
| A23 | For non-Steam shortcuts, game processes carry `SteamGameId` equal to the 64-bit game ID `(appid << 32) | 0x02000000`, and `STEAM_COMPAT_DATA_PATH` ending in `compatdata/<unsigned appid>` | unverified, process matching accepts either and Diagnostics reports which matched | community knowledge |
| A24 | `shortcuts.vdf` stores `appid` as a signed 32-bit integer; `appid & 0xFFFFFFFF` gives the compatdata folder name | unverified on device, Diagnostics reports both values and whether the folder exists | build prompt |

## Updates (slice 2)

| # | Fact | Status | Source |
|---|---|---|---|
| A33 | GitHub release `browser_download_url` links on `github.com` redirect to `release-assets.githubusercontent.com` (older: `objects.githubusercontent.com`). Both are allowlisted as "GitHub release asset downloads" | unverified on device; the Updates page reports `offline` or `disallowed-host` if this is wrong | GitHub behaviour |
| A34 | With version `dev`, Decky's confirmation prompt shows "dev" and still checks the SHA-256 | verified in source (`browser.py`), unverified on screen | ADR-0002 |
| A35 | `decky.emit` events from the backend reach `addEventListener` in the frontend (used for `keepsake_idle`) | verified in source and types | `sandboxed_plugin.py`, `@decky/api` |
| A36 | The unauthenticated GitHub API limit (60 requests an hour per IP) is ample for one automatic check a day plus manual checks | verified | GitHub docs |

## Discovery (slice 3)

| # | Fact | Status | Source |
|---|---|---|---|
| A37 | `config/loginusers.vdf` maps SteamID64 to a block with `MostRecent` and `Timestamp`; id3 = SteamID64 minus 76561197960265728, matching `userdata/<id3>` | community-documented, unverified on device; falls back to the newest `userdata` folder | |
| A38 | `appmanifest_*.acf` has `AppState` with `appid`, `name`, `installdir` and `LastPlayed` | community-documented, unverified on device | |
| A39 | Tool app IDs (Proton, Steam Linux Runtime, redistributables) are as listed in `discovery.TOOL_APPIDS`; name prefixes catch other Proton versions | unverified; a missed tool only adds a harmless entry to the list | |
| A40 | Shortcut `StartDir` and `Exe` are stored quoted; the `base` root is `StartDir`, else the exe's folder (build prompt section 8) | community-documented, unverified on device; quotes are stripped when present | |
| A41 | Shortcut keys `shortcut:<id3>:<appid>` are stable on one device only; the cross-device identity is the `gameKey` from slice 4 | design | build prompt section 8 |

## Manifest (slice 4)

| # | Fact | Status | Source |
|---|---|---|---|
| A42 | The current manifest URL is on the `data` branch; `master` will stop being updated. **Differs from the build prompt**, same host | verified | manifest README |
| A43 | The live manifest uses only block mappings and sequences, plain and double-quoted scalars and `{}`; no block scalars, anchors, aliases, tags or non-empty flow collections | verified 14 November 2026 by a survey of 886,474 lines | ADR-0006 |
| A44 | The schema in `data/schema.yaml` (files, registry, installDir, steam, id.steamExtra, alias, cloud, notes) is what tools should implement | verified | manifest README |
| A45 | Laptop measurements: 53,541 entries, 0 skipped, index build 22 s with tracing, 30 MB peak traced, 5.6 MB index. Device measurements pending (`parseSeconds`, `peakRssMb` in the index) | laptop verified, device unverified | ADR-0006 |
| A46 | `FileSelectionType` in `@decky/api` is a type-only `const enum`; `FOLDER` is 1 | verified | `@decky/api` `types.d.ts` |
| A47 | `<storeUserId>` folders under AppData are SteamID64-named, the same on both devices for the same account, so a `*` wildcard finds them and the relative path matches across devices | community-documented, unverified on device | Ludusavi behaviour |

## Snapshots (slice 5)

| # | Fact | Status | Source |
|---|---|---|---|
| A48 | `os.replace` within one folder tree on the same filesystem is atomic on Linux (ext4, btrfs), so per-file moves inside a save root are atomic | verified (POSIX rename semantics) | |
| A49 | Staging and backup folders inside the save root are on the same filesystem as the saves, including SD cards | design, follows from A48 | |
| A50 | Python's `zipfile` writes ZIP64 when needed and reads entries' `external_attr` for symlink detection | verified | Python docs |
| A51 | The build prompt's cloud layout gains `games/<gameKey>/pins/<snapId>.json` (ADR-0007), before the slice 6 freeze | owner delegation | |

## OneDrive (slice 6)

Microsoft documentation read on 15 November 2026: device code flow (Entra, updated 2026-06-15), createUploadSession and simple upload (Graph v1.0, updated 2026-08-11), app folder (OneDrive dev centre).

| # | Fact | Status | Source |
|---|---|---|---|
| A52 | Device code endpoint `/{tenant}/oauth2/v2.0/devicecode` with `client_id` and `scope`; response has `device_code`, `user_code`, `verification_uri`, `expires_in`, `interval`, `message`; `verification_uri_complete` is not supported | verified | Entra docs |
| A53 | Polling uses `grant_type=urn:ietf:params:oauth:grant-type:device_code`; documented errors are `authorization_pending`, `authorization_declined`, `bad_verification_code`, `expired_token`. `slow_down` is not listed by Microsoft but is handled per RFC 8628 | verified | Entra docs, RFC 8628 |
| A54 | A refresh token is returned when `offline_access` is requested | verified | Entra docs |
| A55 | Upload sessions default to `conflictBehavior: fail`; a name taken by the time the last range is uploaded returns 409 `nameAlreadyExists` | verified in docs; live behaviour checked by `tests/test_onedrive_live.py` on device | Graph docs |
| A56 | Chunks must be multiples of 320 KiB and under 60 MiB; the `Authorization` header must not be sent to the upload URL; intermediate ranges return 202, the last 200 or 201 with the driveItem | verified | Graph docs |
| A57 | The app folder is `/me/drive/special/approot`, created on first access and named after the app registration; items are addressed as `approot:/{path}:` | verified | OneDrive dev centre |
| A58 | The simple upload page (PUT `/content`) documents no create-only option in v1.0, so it is not used | verified | Graph docs |
| A59 | Upload URLs and download redirects for OneDrive personal are on `*.1drv.com` or `*.microsoftpersonalcontent.com` | partly verified (docs example `sn3302.up.1drv.com`); download host unverified, a wrong guess shows as a "refused" store error | Graph docs |
| A60 | Creating an upload session by path creates missing parent folders; if Graph instead answers 404, Keepsake creates the folders and retries | unverified; both paths are handled and tested against the fake | |
| A61 | OneDrive reports `quickXorHash` for every file (SHA-1 and SHA-256 may be absent for personal accounts) | community-documented; Keepsake falls back to re-download | |
| A62 | `keepsake/quickxor.py` matches Microsoft's QuickXorHash. Verified only against its own reference implementation and the all-zero empty value | unverified against OneDrive until the live test runs (it prints whether the reported hash verified) | |

## Sync (slice 7)

| # | Fact | Status | Source |
|---|---|---|---|
| A63 | The build prompt's "Use cloud save" (keep local pinned, restore head) needs a closing merge, otherwise the kept copy and the losing head stay as heads and the conflict returns. **Differs from the build prompt** (an addition, not a change) | design, ADR-0009 | |
| A64 | Game config revisions in the cloud layout are implemented with the per-game page in slice 9 | done in slice 9 (ADR-0020); `<deviceSeq>` in the frozen key pattern counts this device's revisions for that game | ADR-0009, ADR-0020 |

## Lifecycle (slice 8)

| # | Fact | Status | Source |
|---|---|---|---|
| A65 | The user's launch options are `AppDetails.strLaunchOptions` (via `appDetailsStore.GetAppDetails`) and are set with `SteamClient.Apps.SetAppLaunchOptions(appId, string)`; `GetLaunchOptionsForApp` returns the game's launch menu entries instead | verified in `@decky/ui` types; unverified on device | `App.d.ts`, `appdetailsstore.d.ts` |
| A66 | Game processes run as the same user as the plugin with `HOME` set, so the gate script finds Decky's runtime folder at `~/homebrew/data/Keepsake` | unverified | |
| A67 | Steam lifetime notifications report the app ID the backend can normalise for shortcuts | unverified (ADR-0001) | |

## Cross-device matching

| # | Fact | Status | Source |
|---|---|---|---|
| A68 | The manifest's `launch` keys are executable paths such as `<base>/Binaries/Game.exe`, so their file names identify a game's executable | verified in the live manifest (slice 4 survey) | manifest |
| A69 | A game installed from the same ISO keeps the same exe name and save folder names on both devices, whatever the prefix number or shortcut name | design assumption; the scoring needs two signals so one difference does not cause a wrong match | |

## Gaming Mode UX (slice 9)

| # | Fact | Status | Source |
|---|---|---|---|
| A105 | `ModalRoot` (typed `any`) takes `onCancel`, `closeModal`, `bCancelDisabled` and the other `ModalRootProps`; `showModal` injects `closeModal` | verified in types (`components/Modal.d.ts`); that B and a background tap call `onCancel` is unverified on device | `@decky/ui` 4.16.5 |
| A106 | `DialogButton` accepts `preferredFocus` (from `FooterLegendProps`), which gives it the initial focus in the modal | prop verified in types; focus behaviour unverified on device | `components/Dialog.d.ts`, `FooterLegend.d.ts` |
| A107 | `TextField` opens the Steam on-screen keyboard when activated with the controller | unverified on device (already used for the device name since slice 1) | |
| A108 | Decky lists disabled plugins by `plugin.json` name under `disabled_plugins` in `~/homebrew/settings/loader.json`, and `DECKY_HOME` points at `~/homebrew` | verified in the Tuning Advisor register (item 11) and A4 | decky-loader `loader.py` |
| A109 | decky-ludusavi's per-game auto-sync setting has no documented file format, so Keepsake cannot tell which games it syncs | unverified; the health check warns whenever it is active alongside synced games | |
| A110 | `SidebarNavigation` pages can be built from a list at render time; route paths stay `/keepsake/<tab>` | verified in types | `components/SidebarNavigation.d.ts` |

## Backends and Ludusavi import (slice 10)

| # | Fact | Status | Source |
|---|---|---|---|
| A111 | Google's device flow allows only `drive.appdata` and `drive.file` among Drive scopes; polling needs `client_secret`; errors include `authorization_pending`, `slow_down`, `access_denied`, `invalid_grant` | verified 15 November 2026 | Google "OAuth 2.0 for TV and Limited-Input Device Applications" |
| A112 | Drive returns `sha256Checksum` for files and serves `alt=media` downloads from `www.googleapis.com` without redirecting | `sha256Checksum` documented in Drive v3; the no-redirect behaviour is unverified on device (a redirect is refused, so a wrong guess fails closed) | Drive API v3 |
| A113 | AWS S3 honours `If-None-Match: *` on PUT (412 when the key exists, 409 for a concurrent conditional write) | AWS documentation (conditional writes, 2024); compatible services vary, so Keepsake proves it per endpoint | AWS |
| A114 | Nextcloud and ownCloud honour `If-None-Match: *` on WebDAV PUT | community-documented, unverified; proven per server by the probe | |
| A115 | Ludusavi's `mapping.yaml` has `name`, `drives` (folder to drive), and `backups` with `name`, `when`, `files` (path to `hash` and `size`) and `children` whose `files` entries may be null for removed files; a name ending in `.zip` means the zip format; files are stored at `<drive folder>/<path without drive>`, `drive-0` being the empty Linux drive; hashes are SHA-1 | read in Ludusavi's source (`src/scan/layout.rs`, MIT) on 15 November 2026; SHA-1 assumed from the 40-hex hashes (SHA-256 also accepted, other lengths fall back to the size check) | Ludusavi |
| A116 | A Google OAuth app in testing mode expires refresh tokens after 7 days; whether publishing needs verification for `drive.appdata` | expiry is Google's documented testing-mode rule; verification need unverified | Google |
| A117 | Peter's Ludusavi backups are in a folder on the device (Ludusavi's default `~/ludusavi-backup`) as well as in OneDrive through rclone | unverified; the import reads a local folder only (ADR-0021 item 7) | |

## Registry, Steam Cloud and suspend (slice 11)

| # | Fact | Status | Source |
|---|---|---|---|
| A118 | Steam writes `userdata/<id3>/<appid>/remotecache.vdf` (and `remote/`) for apps that use Steam Cloud, and not for apps without it | community-documented, unverified on device; a wrong answer only mislabels (T69) | |
| A119 | Wine's `user.reg` is UTF-8 text starting `WINE REGISTRY Version 2`, with `[key] <unix time>` headers, optional `#time=` lines, value lines starting `"` or `@`, and hex data continued with a trailing backslash; key names escape `\` as `\\`; Wine accepts headers without `#time` | format read from Wine-written files and Wine's registry code conventions; unverified against every Proton version, so an unparseable file is left alone (fail closed) | Wine |
| A120 | Wine re-reads `user.reg` when the prefix's wineserver starts, so a merge while the game is closed takes effect at the next launch | design assumption; merges only happen with the game closed | |
| A121 | `SteamClient.System.RegisterForOnSuspendRequest(cb)` fires before the device sleeps, leaving a few seconds for a snapshot | verified in types (`system/index.d.ts`); timing unverified on device (A21) | `@decky/ui` 4.16.5 |
| A122 | The Ludusavi manifest's `registry` keys use `HKEY_CURRENT_USER/...` paths with forward slashes | verified in the manifest schema (A44) | manifest |

## Hardening (slice 12)

| # | Fact | Status | Source |
|---|---|---|---|
| A123 | minisign signature files have four lines (untrusted comment, base64 of algorithm, key ID and signature, trusted comment, base64 global signature over signature and trusted comment); the default algorithm `ED` signs the BLAKE2b-512 hash of the file; public keys are base64 of `Ed`, key ID and key | minisign's documented format; verified by tests built in that format, not yet against a file made by the minisign tool (the first signed release proves it) | minisign documentation |
| A124 | `keepsake.ed25519` is correct | verified against RFC 8032 section 7.1 test vectors 1 and 2 | RFC 8032 |
| A125 | 50 games stay responsive: on the development laptop, discovery 0.4 s, matching 0.1 s, preview of all 1.8 s, dry run 16 s, QAM summary 0.3 s, health 0.1 s, first push of all 58 s, idle pass 14 s (local test store) | measured on Windows; on-device figures pending (run on the device with `python scripts/test_on_device.py tests/test_performance.py`) | `tests/test_performance.py` |

## v2 verification items (slice C0)

Every claim in `docs/build-prompt-v2.md` and `docs/research/replication-research.md` that Keepsake will rely on. "TA" means Peter's Tuning Advisor verification register (`decky-plugins/docs/VERIFICATION.md`), reused as evidence with its date and re-checked in the slice named. Types were read in `@decky/ui` 4.16.5 on 15 November 2026.

### Steam client (Steam Operations Executor, ADR-0015)

| # | Claim | Status | Source | Slice |
|---|---|---|---|---|
| A70 | `SteamClient.Apps.AddShortcut(appName, executablePath, directory, launchOptions): Promise<number>` returns the new app ID. **Differs from the research**, which says it takes no start dir or launch options and ignores them: the types take both. Whether they are honoured is unverified, so the executor always follows with the `Set*` calls | signature verified in types; behaviour unverified | `steam-client/App.d.ts` | 13 |
| A71 | `SetShortcutName`, `SetShortcutExe`, `SetShortcutStartDir`, `SetAppLaunchOptions` (all `(appId: number, value: string): void`) silently fail if called within about 500 ms of `AddShortcut` | signatures verified; timing unverified | types; research 2.1 | 13 |
| A72 | Pre-quoted exe paths are double quoted by Steam | unverified | research 2.1 | 13 |
| A73 | `SpecifyCompatTool(appId, strToolName): void` and `GetAvailableCompatTools(appId): Promise<CompatibilityTool[]>` work for non-Steam shortcuts | signatures verified; shortcut behaviour unverified | types; TA item 8 | 13, 19 |
| A74 | `SetCustomArtworkForApp(appId, base64, 'jpg' or 'png', assetType): Promise<void>` applies artwork in Gaming Mode | signature verified; behaviour unverified | types | 19 |
| A75 | `RemoveShortcut(appId)` and `SetShortcutIcon(appId, path)` exist | verified in types | types | 21 |
| A76 | `AppDetails` exposes `strShortcutExe`, `strShortcutStartDir`, `strShortcutLaunchOptions`, `strLaunchOptions` and `strCompatToolName` for read-back | verified in types (TA, 4.16.0); re-check in 4.16.5 | TA items 7, 8 | 13 |
| A77 | Shortcut app IDs are random on current Steam clients, so the same game gets a different ID per device | community-documented, unverified | research 2.1 | 19 |
| A78 | Steam has read `shortcuts.vdf` from different `userdata` folders in Desktop and Gaming Mode | reported upstream bug, unverified; only a reason never to write VDF | research 2.1 | |

### Decky runtime and transport

| # | Claim | Status | Source | Slice |
|---|---|---|---|---|
| A79 | The Decky backend keeps running in Desktop Mode on SteamOS and Bazzite | **unverified**; slice 23 stops and escalates if false | spec 8.4 | 23 |
| A80 | The device's Python supports TLS-PSK through `SSLContext.set_psk_client_callback` and `set_psk_server_callback` (added in Python 3.13; needs OpenSSL PSK support in Decky's build) | unverified | Python docs; spec 8.2 | 16 |
| A81 | Stdlib multicast sockets can do mDNS / DNS-SD from the plugin process | unverified | spec 8.2 | 16 |
| A82 | Decky uses ports 1337 and 8080; TCP 47110 is otherwise free | 1337 and 8080 verified (TA item 12); 47110 unverified | TA item 12 | 17 |
| A83 | Wi-Fi 6E device to device throughput is 40 to 120 MB/s with SHA-256 hashing affordable on Z1E and Z2E | unverified, measured in the spike | research 4.10 | 16 |
| A84 | Bazzite ships an active firewall that blocks inbound ports by default; SteamOS does not | community-documented, unverified | research 2.1 | 17 |

### System Binary Register (ADR-0018)

| # | Claim | Status | Slice |
|---|---|---|---|
| A85 | `udisksctl loop-setup -r -f <iso>` and `mount` work as `deck` from the Gaming Mode session under default polkit rules on SteamOS and Bazzite, for ISO9660 and UDF | unverified | 21 |
| A86 | `systemd-inhibit` is present and can hold a sleep inhibitor as the user | unverified | 18 |
| A87 | `openssl` is present on SteamOS and Bazzite | unverified | 16 |
| A88 | `firewall-cmd` is present on Bazzite and answers `--state` without root | unverified | 17 |
| A89 | System `python3` is available in the Desktop Mode session on both | unverified | 24 |
| A90 | `jeepney` is pure Python under a licence compatible with BSD-3-Clause, and KDE Plasma on both distributions hosts StatusNotifierItem | unverified | 24 |

### Devices and Advisor

| # | Claim | Status | Source | Slice |
|---|---|---|---|---|
| A91 | Legion Go: 2560x1600 144 Hz IPS, no VRR, Z1 Extreme. Legion Go 2: 1920x1200 144 Hz OLED with VRR, Z2 Extreme. Both have two USB4 ports and Wi-Fi 6E | Legion Go 2 Z2E and Legion Go spec values verified by TA from PSREF and hhd; USB4 and Wi-Fi unverified | TA items 19, 20 | 14 |
| A92 | Lenovo puts the machine type in DMI `product_name` and the model in `product_version` | verified (TA) | TA item 19 | 14 |
| A93 | The Ludusavi manifest's Steam ID is in Keepsake's compact index for Advisor lookups | verified in code: slice 4 matches games by Steam ID from the index | `manifest.py` | 14 |
| A94 | Deck Verified is at `deckverified.games/deck-verified/api/v1/game_details`, 120 requests per 2 minutes per IP, report data GPL-3.0 | verified (TA, 25 October 2026); licence re-confirmed 15 November 2026 | TA item 16 | 14 |
| A95 | The Steam store and Deck Verified hosts Advisor needs (spec 6.2 "verify exact hosts") | unverified | spec 6.2 | 14 |
| A96 | The ProtonDB summaries endpoint has no published terms; the monthly dumps are ODbL | verified (TA, 30 October 2026) | TA `DATA-SOURCES.md` | 15 |
| A97 | PCGamingWiki Cargo needs a bot password since August 2026, 60 requests a minute | verified (TA, 26 October 2026) | TA item 18 | 14 |
| A98 | `decky-lsfg-vk` writes `~/.config/lsfg-vk/conf.toml` and needs `~/lsfg %command%` in launch options; lsfg-vk 2.0.0 shipped in September 2026 | unverified | research 2.1 | 15 |
| A99 | There is no Steam client clipboard API for text; `navigator.clipboard` with an `execCommand` fallback is what plugins use | API absence verified (TA); device behaviour unverified | TA item 10 | 14 |
| A100 | FSR 4 under Proton is unofficial on every target handheld | verified as of 25 October 2026 (TA); re-check before slice 15 | TA item 25 | 15 |
| A101 | AI provider endpoints, headers and models lists as in the TA brief | verified from documentation (TA, October 2026); recheck, including Anthropic API version changes | TA item 24 | 15 |

### Installer

| # | Claim | Status | Source | Slice |
|---|---|---|---|---|
| A102 | `STEAM_COMPAT_MOUNTS` exposes extra paths to Proton | community-documented, unverified | research 2.1 | 21 |
| A103 | Retargeting the same shortcut after installing keeps its prefix; recreating it makes a new prefix | community-documented, unverified | research 2.1 | 21 |
| A104 | Both devices use the user `deck` and the same root layout, so prefix registry paths need no rewriting | owner's setup (spec section 3); `.reg` rewriting is backlog | spec 11 | 19 |

## Template differences

| # | Difference | Reason |
|---|---|---|
| A25 | The template's VS Code tasks (bash, rsync, Docker, Decky CLI) are replaced by cross-platform Python scripts: `scripts/package.py` and `scripts/deploy.py` | Development is on Windows without WSL or Docker. The zip layout matches the template README; proving install from URL with it is a slice 2 acceptance item |
| A26 | `@rollup/rollup-linux-x64-musl` is dropped from dev dependencies | Only needed inside the Decky CLI's Alpine Docker build, which is not used |
| A27 | `plugin.json` flags are `[]` (template ships `["debug", "_root"]`) | Principle 8 |

## Local development

| # | Fact | Status |
|---|---|---|
| A28 | WSL fails to start on the development laptop ("logon type not granted", policy) and Docker is not installed | verified 14 November 2026 |
| A30 | No GitHub Actions (owner decision, ADR-0004). Linux test runs happen on a device over SSH | decided 14 November 2026 |
| A31 | SteamOS and Bazzite ship `python3` with the `venv` module and `ensurepip`, and the device can reach PyPI, so `scripts/test_on_device.py` can create its test venv | unverified, first device run confirms |
| A32 | **Differs from the build prompt:** sections 1, 6, 13, 16 and 17 assume GitHub Actions for pull request checks and releases. Replaced by `pnpm run check`, device tests and a local `pnpm release` (ADR-0004) | owner decision |
| A29 | `LocalFolderStore` create-only writes use hard links, which exFAT and FAT32 SD cards do not support | known gap; acceptable for tests and the simulator, revisit before offering it as a user backend |
