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
| A123 | minisign signature files have four lines (untrusted comment, base64 of algorithm, key ID and signature, trusted comment, base64 global signature over signature and trusted comment); the default algorithm `ED` signs the BLAKE2b-512 hash of the file; public keys are base64 of `Ed`, key ID and key | verified against the real tool (17 November 2026, ADR-0036): the plugin's verifier accepts minisign's own signed release `minisign-0.12.tar.gz` with its published key, and refuses changed data, a changed signature or trusted comment, and another key (`tests/test_minisign_real.py`); every signed release re-checks its signature with the plugin's verifier before publishing | minisign documentation, minisign 0.12 |
| A190 | A user process can bind UDP 5353 with address reuse beside `avahi-daemon` on SteamOS and Bazzite and receive the mDNS group's queries; SteamOS has no firewall by default; the handhelds' Wi-Fi does not wake from Wake-on-LAN while asleep, but PCs on a cable usually do | unverified until the 17b device run; without the responder, typing the address still works | Linux sockets, avahi-daemon, adapters |
| A193 | The `deck` user (and a Bazzite user) in an active session may take logind's `idle` block and `sleep` delay inhibitors without a password (polkit defaults), and the system bus passes the lock's descriptor; Steam's own suspend in Gaming Mode honours the delay lock | polkit defaults documented; unverified on SteamOS and Bazzite until the slice 18 device run (`systemd-inhibit --list` while a transfer runs) | logind, polkit, Steam |
| A197 | Two handhelds used one at a time are still both on and on the same network often enough (for example both at home) for direct save sync to bring saves across before the next play; when they are not, play goes on with the saves on that device and a later exchange shows any conflict | unverified until the R7 device run; a cloud store stays the choice when the devices are rarely on together | how the owner uses the devices |
| A198 | A Steam game with Steam Cloud saves always has `userdata/<id>/<appid>/remotecache.vdf` or files in `remote/` once it has been played and synced, so `no-cloud` means Steam does not back it up | slice 11 heuristic; unverified for a game played only while offline, which Steam has not synced yet (a conflict, never an overwrite, if wrong) | Steam userdata |
| A199 | Steam Remote Play's entries for games installed on another device on the account are live entries from that client and are not in this device's `shortcuts.vdf` | reports in steam-for-linux #13141 and #12315 (they vanish when the other Steam stops), and Peter's check that their menu offers Stream; unverified until the device check "Games you can stream from another device" runs with both handhelds on | Steam client |
| A200 | For such an entry, `appStore` gives `BIsShortcut()` true, `GetPerClientData("local").installed` false and a `per_client_data` entry for the other client with `installed` true and its `client_name`; a real local shortcut has `installed` true locally | names verified in @decky/ui 4.16.5 types; values unverified until the device run | @decky/ui, Steam client |
| A201 | Hiding a streaming tile on one handheld (Steam's own Hide, or `SetAppsAsHidden`) also hides the same game on the other handheld, because the entry has the real shortcut's app ID and the hidden collection syncs across the account | believed true; unverified. Device run: hide one streaming tile on the Go, then check the same game is still visible and shows Play on the Go 2. The tidy-up stays off (`streamTidyVerified`) until this shows it does not | Steam client |
| A202 | Removing a streaming entry with `RemoveShortcut` does not last: Steam brings it back while the other device runs Steam | steam-for-linux #13141; not offered | Steam client |
| A203 | After `SteamClient.Apps.RemoveShortcut`, `appStore.GetAppOverviewByAppID(appid)` and `appDetailsStore.GetAppDetails(appid)` return nothing for that app within about 600 ms; `ClearCustomArtworkForApp(appid, 0..4)` removes its custom artwork | names verified in @decky/ui 4.16.5 types; timing and values unverified until the Uninstall step of the device run (if Steam answers late, nothing is deleted and the job says so) | @decky/ui, Steam client |
| A204 | `Focusable` with `autoFocus` gives a modal's Cancel button the controller focus when the confirmation screen opens | `Focusable` takes HTML attributes in @decky/ui 4.16.5; focus behaviour unverified until the device run | @decky/ui |
| A205 | `SteamClient.Installs.OpenUninstallWizard([appid], false)` opens Steam's own uninstall confirmation for a Steam game and Steam removes the install itself | name verified in @decky/ui 4.16.5 types (Installs.d.ts); unverified until the device run | @decky/ui, Steam client |
| A206 | From the Decky plugin process on SteamOS and Bazzite, a UDP socket can send to 224.0.0.251:5353, 255.255.255.255:137 and 239.255.255.250:3702 and receive the unicast answers; NAS boxes answer mDNS `_smb._tcp`, Windows answers NetBIOS node status or WS-Discovery | protocols documented (RFC 6762 section 6.7, RFC 1002, WS-Discovery 1.1); unverified until the Device check "Find shares on my network" runs with a NAS or Windows PC on the network | network, SteamOS |
| A207 | `fusermount3` (libfuse 3) is installed and setuid on SteamOS and Bazzite, `/dev/fuse` is open to the user, and udisks can loop-set-up a file on a FUSE mount made by that user (A158) | Flatpak's document portal needs fuse3 on both; unverified until the Device check "Network ISO in place" runs, and the in-place route waits for Peter's approval of the register entry (ADR-0067) | SteamOS, Bazzite |
| A208 | Decky Loader's backend (plugin_loader, a systemd service) keeps running in Desktop Mode on SteamOS and Bazzite, so the plugin's loopback page answers there | Decky's service runs outside gamescope; unverified until the device run (ADR-0017 step 0, A79) | Decky Loader |
| A209 | Plasma's system tray in Desktop Mode on SteamOS and Bazzite accepts a StatusNotifierItem registered with org.kde.StatusNotifierWatcher, shows its icon from IconThemePath, and reads its menu over com.canonical.dbusmenu | the protocols are KDE's own; unverified until the device run | KDE Plasma |
| A210 | xdg-desktop-portal answers org.freedesktop.portal.OpenURI in Plasma Desktop Mode and opens the default browser; when it does not, Python's webbrowser finds the desktop's opener | portal API documented; unverified until the device run | xdg-desktop-portal |
| A211 | `SteamClient.System.Perf.RegisterForDiagnosticInfoChanges` delivers name and value entries that include the frame rate (named like "FPS") and possibly the frame time, while a game runs, even with the performance overlay hidden | the function and its entry shape are in @decky/ui 4.16.5 types; the entry names, and whether updates arrive with the overlay off, are unverified until the Device check "Session stats sources" runs after a game | @decky/ui, Steam client |
| A212 | The Legion Go's Z1 Extreme (Phoenix) exposes amdgpu `gpu_metrics` version 2 (power in mW, temperatures in centi-degrees), and the Legion Go 2's Z2 Extreme (Strix Point) version 3, whose layout Keepsake does not read, so on the Go 2 CPU and GPU power come only if hwmon gives them | kernel headers (`kgd_pp_interface.h`); unverified until the device run | amdgpu |
| A213 | Steam's per-game frame limit is not readable from the plugin in a form Keepsake can decode (it is in `RegisterForStateChanges`' protobuf, whose field numbers are not in the types), so sessions record the frame cap as unknown | @decky/ui 4.16.5 types; revisit if a decoded form appears | @decky/ui |
| A214 | Decky Loader rejects a failed backend call with a `PyError` whose `name` is `Python <ExceptionType>` and whose `message` is the exception's text, so `String(err)` shows "Python ValueError: ..." | Verified from source (decky-loader `frontend/src/wsrouter.ts`, `class PyError`, read 21 November 2026) | decky-loader repository |
| A215 | pysmb 1.2 takes the domain as its own `domain` argument; a `DOMAIN\user` user name passed whole is refused by Windows | Verified from source (vendored `smb/SMBConnection.py` constructor). The Windows behaviour is unverified until the device run (part 4, step 12) | `py_modules/keepsake/_vendor/smb` |
| A216 | Steam's browser may load the loopback sign-in address again, and a tab left open after a phone sign-in loads it when Microsoft redirects. Before v0.30.2 the listener had closed, giving "cannot connect" | Unverified (the owner's report, 21 November 2026). The device run checks it (part 4, step 11) | Owner's report |
| A217 | Walking a game's files with the manifest's exclusions gives sizes close enough to the hashed manifest for a space check with a 5 percent or 2 GiB margin | Unverified on a device; the preflight at the start of the copy still checks the exact sizes (ADR-0072) | `replication/sendgame.py` |
| A218 | `@decky/ui` `Focusable` takes `onActivate`, so a compact line in the quick access menu can open the Devices page | Verified from the type definitions (`node_modules/@decky/ui/dist/components/Focusable.d.ts`) | `@decky/ui` |
| A219 | `@decky/ui` `SidebarNavigation` takes `"separator"` entries and pages with `visible: false` | Verified from the type definitions (`node_modules/@decky/ui/dist/components/SidebarNavigation.d.ts`); how a hidden page's route opens on a device is unverified (device run, step 19) | `@decky/ui` |
| A220 | Steam's `Tabs` component inside a `SidebarNavigation` page may break controller scrolling (it expects a full-height container) | Unverified, so not used: sections draw their own tab row of `DialogButton`s (ADR-0073) | `@decky/ui` `Tabs.d.ts` |
| A221 | Decky's plugin process can reach the user's session bus at `/run/user/<uid>/bus` and call steamos-manager's user daemon there, without polkit | Unverified. steamos-manager's bus policy lets anyone send, and the research found no polkit check (`docs/research/legion-control.md`). The Device check "Performance control" proves it (device run, step 23) | steamos-manager |
| A222 | On the Legion Go, setting `TdpLimit` through steamos-manager writes the same value to SPL, SPPT and FPPT, and takes effect only in the Custom mode | Verified from steamos-manager's source as read by the research (`power.rs` and the Legion device file). Behaviour on the devices is unverified (step 23) | steamos-manager |
| A223 | On Steam's game page in the library, the route's tree has a `renderFunc` whose result holds the app overview and a container with `appDetailsClasses.InnerContainer`, where an extra child can be added | Unverified: the names are verified in `@decky/ui`'s types and are the pattern other Decky plugins use. If the shape differs, the badge does not appear and nothing breaks (device run, step 29) | `@decky/ui` |
| A224 | Decky's `routerHook.addRoute` routes are matched in the order they are added, so an exact route for an old page added before Keepsake's own route wins for that address | Unverified. If it does not hold, an old link lands on the section's first tab instead of redirecting, and nothing loops, because no redirect shares a section's address (`tests/frontend/sidebar.test.cjs`). Device run, step 30 | decky-loader |
| A225 | The signed-in user may list BlueZ devices, run discovery and call `Device1.ConnectProfile` over the system bus without root, as Steam does | Unverified on device; Steam's own Bluetooth screens rely on it. Device check "Controller reconnect help", device run step 31 | BlueZ D-Bus policy |
| A226 | BlueZ emits `PropertiesChanged` with `Paired` true for a new pairing early enough for `ConnectProfile(HID)` to reach the controller before it drops the link (Design B) | Unverified. From BlueZ issue 2679; device run step 32 | BlueZ |
| A227 | `journalctl` is present on SteamOS and Bazzite and the default user may read bluetoothd's and the kernel's lines through the `wheel` group's journal ACL | Unverified on device. Device check "Controller reconnect help" reports it | systemd tmpfiles |
| A228 | Valve's `60-steam-input.rules` (uaccess for 054C:05C4 and 09CC over USB) is installed on SteamOS and Bazzite, so "Read stored host over USB" works without root for those IDs | Verified in Valve's steam-devices file (22 November 2026); installation on each system unverified. Device run step 33 | ValveSoftware/steam-devices |
| A229 | Keepsake's backend and the helper both run as Decky's plugin loader executable, so `/proc/<pid>/exe` of a Keepsake request matches the helper's own | Unverified. If not, the helper refuses every request (fail closed), and the Device check shows the helper as not ready. Device run step 35 | decky-loader `sandboxed_plugin.py` |
| A230 | This Python's `socket.bind` takes `(device, channel)` for `BTPROTO_HCI`, or `ctypes` is available for the fallback | Unverified on device; device run step 37 | CPython socketmodule |
| A231 | MGMT Set Secure Simple Pairing off works with the adapter powered on SteamOS's kernel, or is refused so the gate can cycle power | Unverified; the gate handles both. Device run step 37 | kernel `mgmt.c` |
| A232 | Decky installs the helper zip (top folder `keepsake-helper`, `plugin.json` name "Keepsake Helper", root flag) through `utilities/install_plugin` as a second plugin, and asks before installing a root plugin | Unverified. Device run step 35 | decky-loader |
| A233 | bluetoothd reads a device's `info` file only at start, so a new key takes effect after the helper's restart | From BlueZ issue 2678 (the recipe stops and starts bluetoothd); device run step 36 | BlueZ |
| A234 | `SidebarNavigation` remounts its pages when its `pages` prop or key changes, and in route mode opens each page as focus moves down the list, so a page that takes focus pulls focus out of the sidebar | Inferred from the device report and `@decky/ui`'s types; the static list and the no-focus rule make it moot. Device run step 39 and the navigation recorder | `@decky/ui` |
| A196 | An installed non-Steam game changes its files only while it runs (a launcher patching itself) or when the user updates it, so scanning when it exits or on request finds every change; Saves resolves every save and config file the game writes | unverified; a missed change is caught at the next exit or Check now, and a save Saves does not know would travel with an update (the user can add it as a custom path) | game behaviour, Ludusavi manifest |
| A195 | Steam runs a non-Steam game with a prefix copied from another device into `compatdata/<new appid>`, keeping its saves and settings; a compatibility tool copied into `compatibilitytools.d` while Steam runs appears after a Steam restart; an empty `compatdata/<appid>` may exist right after `AddShortcut` | unverified until the slice 19 device run (the acceptance test, both directions) | Steam, Proton |
| A194 | Both handhelds report their battery as a `Battery` supply with `capacity` and `status`, and the charger as a `Mains` or `USB` supply with `online`, under `/sys/class/power_supply` | kernel documentation; unverified on the Legion Go and Legion Go 2 until the slice 18 device run | Linux power supply class |
| A192 | On the devices' file systems (ext4 and btrfs inside, exFAT on SD cards) a rename within one file system is atomic, `posix_fallocate` works or fails cleanly, and a truncated file keeps unwritten ranges as holes; exFAT has no holes or POSIX modes, so a sparse file uses its full size there and modes are not kept | ext4 and btrfs documented; unverified on the devices until the slice 18 device run, including an SD card | Linux file systems |
| A191 | Bazzite keeps Fedora's FedoraWorkstation firewalld zone as its default, which allows TCP and UDP 1025 to 65535, so TCP 47110 and mDNS on UDP 5353 work without changes | documented for Fedora Workstation; unverified for Bazzite until the 17b device run (`firewall-cmd --get-default-zone`) | firewalld, Bazzite |
| A189 | GitHub secret scanning covers git content, not release assets, and Google does not disable an installed app's client secret that appears in a public download | unverified; Google documents these secrets as not confidential. If a secret is disabled, a new one is made for the same client and released (ADR-0055) | GitHub secret scanning, Google OAuth |
| A188 | The Python in Decky Loader (and on Linux PCs) is 3.13 or later with an OpenSSL that offers TLS-PSK, so `SSLContext.set_psk_*_callback` and `ECDHE-PSK-CHACHA20-POLY1305` work, and `tls-unique` matches on both ends; ChaCha20-Poly1305 keeps up with Wi-Fi on the Z1 Extreme and Z2 Extreme | verified on the Windows laptop (Python 3.14.3, OpenSSL 3.0.18); unverified on the devices until the slice 17 device run. Without it Replication stays off and says why | Python `ssl`, OpenSSL |
| A187 | udisks mounts every ISO under the same folder (`/run/media/<user>`), so passing that folder in `STEAM_COMPAT_MOUNTS` makes later discs visible; an installer running under Wine sees a new disc when the drive link is repointed; the same ISO usually mounts at the same place after a restart | unverified until the R6 device run with a two-disc game | udisks, Wine `dosdevices` |
| A186 | Proton builds a fresh `compatdata/<appid>` prefix when the folder is missing at launch, and Steam rebuilds `steamapps/shadercache/<appid>` when it is missing | widely documented behaviour, unverified by Keepsake until the R5 device run | Proton and Steam behaviour |
| A185 | Heroic, Lutris and Bottles store their libraries and prefixes as Ludusavi reads them (files and fields in ADR-0051), and Wine and Proton processes carry `WINEPREFIX` or `STEAM_COMPAT_DATA_PATH` | from Ludusavi's readers and the Bottles docs; tested against synthetic files; unverified on a device until the R4 run | Ludusavi source, Bottles docs |
| A184 | EmuDeck's Flatpak and AppImage emulators keep their saves in the home-relative folders listed in `data/emulators.json`, and Flatpak processes carry `FLATPAK_ID` | RetroArch's folders from EmuDeck's RetroArch page; the others are unverified until the R4 device run | EmuDeck docs, Flatpak |
| A183 | `@decky/rollup` bundles `@decky/api` and other runtime dependencies into `dist/index.js`, but takes `@decky/ui`, React and ReactDOM from Decky and Steam at run time | verified in `node_modules/@decky/rollup/index.js` (`external` and `externalGlobals`), so the SBOM leaves those three out | `@decky/rollup` source |
| A182 | The Decky Plugin Store asks for a root licence file with the template notice kept, pnpm 9, `plugin.json` with publish details, backend binaries built from source by its CI, and a pull request adding a submodule to `decky-plugin-database` | from the Decky wiki "Submitting plugins" and "Review and testing" pages and the template README (18 November 2026); unverified until Peter submits | Decky wiki, decky-plugin-template |
| A181 | Windows `GetSystemPowerStatus` reports `BatteryFlag` 128 when there is no system battery and 255 when the status is unknown | from the Windows API documentation; tested with injected values (`tests/test_everyday_polish.py`); a desktop without a battery is unverified | Windows API |
| A180 | Linux lists system batteries in `/sys/class/power_supply/*/type` as `Battery`, and peripheral batteries (controllers, mice) with `scope` `Device` | from the kernel's power supply class documentation; tested against a synthetic tree; a Steam Machine and a desktop are unverified | Linux kernel `power_supply` ABI |
| A179 | Every released Keepsake reads pin objects by their `snapId` alone and ignores other fields, so a pin carrying a `label` is still a pin to older devices | verified in the code: `SnapshotEngine.pins` (unchanged since slice 5) keeps any JSON object with a string `snapId`; tested by `tests/test_save_safety.py` | `py_modules/keepsake/engine.py` |
| A178 | Headless Chromium's `--virtual-time-budget` waits for a page's requests to finish before the screenshot, provided no request stays open; with event streams closed at once, screenshots are complete and reproducible | verified on the Windows laptop with Edge: two runs gave identical files; with an open event stream the capture hung, and with `--timeout` it was racy | Chromium headless flags |
| A177 | On SteamOS and Bazzite, the `deck` user (an active local session) may take a logind `sleep` inhibitor in delay mode through polkit, and the system bus socket is at `/run/dbus/system_bus_socket` | unverified until the slice 16 device run (steps in `docs/slices/s2-report.md`); systemd documents that taking locks is a privileged operation governed by polkit | systemd "Inhibitor Locks" |
| A176 | Windows Python 3.14's OpenSSL supports TLS-PSK (`ssl.HAS_PSK`), a PSK handshake negotiates no compression, and `OP_NO_COMPRESSION` is set by default since Python 3.6 | verified on the Windows laptop by `tests/test_replication_rules.py` (a real TLS 1.2 PSK handshake over a socket pair); the device's Python is checked in the slice 16 run | Python `ssl` documentation |
| A175 | Restoring focus with the DOM `focus()` on the Sign in button after returning from Steam's browser moves Steam's gamepad focus back into the page, as DeckyHub's fix (PR #156) describes | unverified until the Legion Go 2 probe run | DeckyHub PR #156 |
| A174 | Steam's browser in Gaming Mode can open `http://localhost:<port>` served by the plugin backend, and Microsoft sign-in completes in it; Google refuses sign-in in it ("This browser or app may not be secure") | unverified: the Diagnostics sign-in probe measures all three on the Legion Go 2. Google's embedded-browser block is documented; whether Steam's browser counts as embedded is reported by users, not by Google | Google Developers Blog (June 2021), Steam community reports |
| A173 | `@decky/ui` 4.16.5 has `Navigation.NavigateToExternalWeb(url: string): void` | verified in `node_modules/@decky/ui/dist/modules/Router.d.ts`; Keepsake already used it in Advisor | `@decky/ui` type definitions |
| A172 | Microsoft ignores the port when matching `localhost` redirect URIs, matches the path, does not support `[::1]`, and its portal refuses `http://127.0.0.1` (manifest only); Google Desktop app clients accept a `127.0.0.1` loopback redirect on any port with PKCE, and treat the client secret as not secret | from Microsoft's "Redirect URI best practices" (updated 2026) and Google's "OAuth 2.0 for iOS and Desktop Apps"; the flow is tested against a fake token endpoint (`tests/test_loopback_auth.py`), and a real sign-in waits for the client IDs | Microsoft Learn, Google for Developers, RFC 8252 |
| A171 | Python's `zipfile` keeps member names as stored, including absolute paths, `..` parts and backslashes, so names must be checked before writing; `ZipInfo.file_size` is the declared unpacked size | from the Python `zipfile` documentation; the refusals are tested with crafted archives (`tests/test_pcupdate.py`). On Windows, `zipfile` turns `\` into `/` when it reads names, so the `..` rule already catches a backslash escape and the backslash rule (kept for defence in depth) is not separately detectable there; on Linux a backslash is an ordinary filename character | Python documentation |
| A170 | On Windows, `EnumProcesses` lists process IDs, and `OpenProcess` with only `PROCESS_QUERY_LIMITED_INFORMATION` is enough for `QueryFullProcessImageNameW` to read the program path of the user's own processes | verified on the Windows laptop: the list includes the running Python (`tests/test_pcwatch.py`) | Windows API |
| A169 | Steam for Windows records its folder in `HKCU\Software\Valve\Steam\SteamPath` (also `InstallPath` under `HKLM\SOFTWARE\WOW6432Node\Valve\Steam`), keeps the same `steamapps`, `libraryfolders.vdf` (paths written with escaped backslashes), `appmanifest_*.acf` and `userdata/<id>/config/shortcuts.vdf` files as on Linux, and runs games natively with no compatdata prefix | the file formats and escaped paths are tested (`tests/test_discovery_windows.py`), and reading the registry works on this laptop; a real Steam for Windows library is unverified until a run on a Windows PC with Steam | Steam for Windows, Valve's file formats |
| A167 | On Windows, `SO_REUSEADDR` (which `socketserver` sets by default for `http.server`) lets a second socket bind a port already in use; `SO_EXCLUSIVEADDRUSE` with reuse off refuses it | verified on the Windows laptop by `tests/test_host.py`: with reuse on, a second bind of the host's port succeeded; with reuse off it fails, and so does a hijacker that sets `SO_REUSEADDR` itself. On this laptop, reuse off alone already refuses the hijacker, so `SO_EXCLUSIVEADDRUSE` is kept as defence in depth, as Microsoft recommends for servers, and its removal alone is not detectable by the test | Python `socketserver`, Windows sockets |
| A168 | If an HTTP server answers and closes without reading the request body, Windows may reset the connection and the client sees `WinError 10053` instead of the answer | seen on the Windows laptop in `tests/test_host.py`; the host reads the capped body before any refusal | Windows sockets |
| A166 | On Windows, `SHGetKnownFolderPath` with the KnownFolders.h IDs gives each Windows logical root, including a Documents folder redirected to OneDrive; `os.path.realpath` resolves symlinks and NTFS junctions (Python 3.8 and later), so the existing escape checks confine writes on Windows too | verified on the Windows laptop (17 November 2026): the roots match `%APPDATA%`, `%LOCALAPPDATA%`, `%PUBLIC%` and `%PROGRAMDATA%`, LocalLow and Saved Games (`tests/test_hosts.py`); real Steam games on a Windows PC are unverified until a PC run | Windows API, Python documentation |
| A165 | minisign 0.12 reads the key password with `fgets(stdin)` on Windows too, so a piped passphrase works; Windows DPAPI (`CryptProtectData`, current user) seals and unseals through stdlib `ctypes` | the first from minisign's `src/get_line.c`; DPAPI verified on this laptop (`tests/test_signing.py`); the piped passphrase is verified: Peter's `signing.py setup` and `status` (17 November 2026) signed with real minisign 0.12 and the plugin's verifier accepted the signature | minisign source, Windows API |
| A124 | `keepsake.ed25519` is correct | verified against RFC 8032 section 7.1 test vectors 1 and 2 | RFC 8032 |
| A125 | 50 games stay responsive: on the development laptop, discovery 0.4 s, matching 0.1 s, preview of all 1.8 s, dry run 16 s, QAM summary 0.3 s, health 0.1 s, first push of all 58 s, idle pass 14 s (local test store) | measured on Windows; on-device figures pending (run on the device with `python scripts/test_on_device.py tests/test_performance.py`) | `tests/test_performance.py` |

## Module framework (slice 13)

| # | Fact | Status | Source |
|---|---|---|---|
| A126 | Steam keeps per-app compatibility tool choices in `config/config.vdf` under `InstallConfigStore/Software/Valve/Steam/CompatToolMapping/<appid>/name` | community-documented, unverified on device; missing or different layouts give no tool (read-only) | |
| A127 | `AppDetails.strDisplayName`, `strShortcutExe`, `strShortcutStartDir`, `strLaunchOptions` and `strCompatToolName` reflect a change about 600 ms after the matching setter | field names verified in `@decky/ui` 4.16.5 `App.d.ts`; timing unverified (the executor reports a mismatch rather than assuming success) | |
| A128 | `sqlite3` with WAL mode works in Decky's embedded Python and on SD-card and internal storage | unverified (A9); without it modules needing state stay off | |

## Installer (slice 21)

| # | Fact | Status | Source |
|---|---|---|---|
| A129 | `openFilePicker(select, startPath, includeFiles, includeFolders, filter, extensions, ...)` with `FileSelectionType` `FILE = 0` and `FOLDER = 1` (a type-only const enum, so the numbers are used) | verified in `@decky/api` types | `@decky/api` |
| A130 | `GetAvailableCompatTools(appId)` returns `CompatibilityTool[]` with `strToolName`; GE-Proton builds are named `GE-Proton<major>-<minor>`, so a numeric descending sort finds the newest | type verified in `@decky/ui` 4.16.5 `App.d.ts`; naming community-documented, unverified on device | `App.d.ts` |
| A131 | `udisksctl` prints `Mapped file X as /dev/loopN.` and `Mounted /dev/loopN at <path>` | udisks documentation; unverified on device (A85); other wording fails closed with an error | udisks |
| A132 | Installers see the Linux root as drive `Z:`, so `Z:\home\deck\Games\Title` reaches the library folder | standard Wine behaviour, unverified with Proton on device | Wine |
| A133 | `STEAM_COMPAT_MOUNTS` makes a path outside the home folder visible inside the Steam Linux Runtime container | community-documented, unverified | research 2.1 |
| A134 | Steam reports the installer shortcut's exit through the same lifetime notification as games, so the Installer hears it | unverified; "I have finished installing" is the manual fallback | |

## Installer II (slice 22)

| # | Fact | Status | Source |
|---|---|---|---|
| A135 | Wine maps drive letters through `<pfx>/dosdevices/<x>:` links, takes the raw device from `<x>::`, and reads the drive type from `HKLM\Software\Wine\Drives` (`"d:"="cdrom"`) in `system.reg` | standard Wine behaviour; unverified with Proton on device | Wine |
| A136 | Proton has finished creating a prefix once `pfx/system.reg` exists | unverified; adding a drive earlier is refused | Proton |
| A137 | The Steam runtime container shows the home folder but not other paths, so `STEAM_COMPAT_MOUNTS` is needed for sources and library folders elsewhere | community-documented, unverified; pressure-vessel may already share `/run/media` and `/mnt`, in which case the option is harmless | research 2.1 |
| A138 | SteamGridDB API v2: `search/autocomplete/<term>`, `grids/game/<id>?dimensions=`, `heroes/game/<id>`, `logos/game/<id>`, a bearer key, and `{"success": true, "data": [...]}` with image `url`s on `cdn2.steamgriddb.com` | SteamGridDB API documentation and the decky-steamgriddb plugin; unverified until the image host is approved | SteamGridDB |
| A139 | `SetCustomArtworkForApp(appId, base64, 'png' or 'jpg', ELibraryAssetType)` (Capsule 0, Hero 1, Logo 2, Header 3) applies artwork to a shortcut, and Steam offers no getter to read it back | signature and enum verified in `@decky/ui` 4.16.5 `App.d.ts`; effect unverified | `App.d.ts` |
| A140 | `RemoveShortcut(appId): void` removes a non-Steam shortcut, and `AppDetails` is gone afterwards | signature verified in types (A75); effect unverified | `App.d.ts` |
| A141 | `/proc/self/mounts` in the plugin process lists the user's CIFS, NFS, gvfs and kio-fuse mounts | unverified; the network mount probe checks it | spike |

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
| A79 | The Decky backend keeps running in Desktop Mode on SteamOS and Bazzite | **unverified**; `scripts/desktop_mode_probe.py` checks it (slice 23 report); slice 23 stops and escalates if false | spec 8.4 | 23 |
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

## Advisor I (slice 14)

| # | Fact | Status | Source |
|---|---|---|---|
| A142 | `navigator.clipboard.writeText` works in Steam's Gaming Mode CEF for a Decky page | unverified (the Steam client has no clipboard API); the text is always shown as well | Tuning Advisor register |
| A143 | `Navigation.NavigateToExternalWeb(url)` opens a page from Gaming Mode | verified in `@decky/ui` 4.16.5 `Router.d.ts`; behaviour unverified on device | `@decky/ui` |
| A144 | `DropdownItem` with `rgOptions`, `selectedOption` and `onChange` | verified in `@decky/ui` 4.16.5 `Dropdown.d.ts` | `@decky/ui` |
| A145 | The Legion Go reports `sys_vendor` `LENOVO` and `product_name` `83E1`; the Legion Go 2 `83N0` or `83N1` | Lenovo machine types; unverified on Peter's devices until `capture_device.sh` runs (c0-report Q2) | Lenovo PSREF |
| A146 | Deck Verified answers `game_details?appid=` and `?name=` with `{"reports": [...]}`, 204 when nothing is known, and links each report to a GitHub issue | Tuning Advisor register, unverified from Keepsake | deckverified.games |
| A147 | The manifest compact index keeps the Steam ID as `s` per game | verified (`manifest.build_index`, slice 4) | Keepsake |

## Advisor II (slice 15)

| # | Fact | Status | Source |
|---|---|---|---|
| A148 | Provider request and reply shapes: Anthropic Messages API version 2026-10-21 with `output_config.format`, OpenAI Responses API with strict `json_schema`, Gemini `generateContent` with `responseJsonSchema` | from Tuning Advisor's register (recorded replies), unverified from Keepsake until a real key is tried | Tuning Advisor |
| A149 | GE-Proton installs as `<steam root>/compatibilitytools.d/GE-Proton<major>-<minor>` | community-documented (ProtonUp-Qt, ProtonPlus), unverified on Peter's devices | |
| A150 | The tools' settings formats in `current.py` (SimpleDeckyTDP, PowerControl, LeGoTDP, Legion Go 2 Companion, lsfg-vk `conf.toml` version 2) | checked by Tuning Advisor on 26 October 2026 against each tool's source; may drift | Tuning Advisor register item 23 |
| A151 | lsfg-vk shows visible artefacts below a base of about 40 fps | research 6.4 heuristic, to tune with testing | research |

## Decky's frozen Python (v0.22.1)

| # | Fact | Status | Source |
|---|---|---|---|
| A152 | Decky Loader's Python is a PyInstaller build that bundles only the stdlib modules its own code reaches plus `hiddenimports` (`logging.handlers`, `sqlite3`, `http.server`, `socketserver`, `configparser`). `xml`, `tomllib` and `resource` are not proven bundled | verified from `backend/pyinstaller.spec` and the loader's imports on `main` (16 November 2026); `xml` confirmed missing on Peter's Legion Go 2 | Decky Loader source, ADR-0030 |

## Full-screen pages and the Gaming Mode footer

| # | Fact | Status | Source |
|---|---|---|---|
| A154 | Gaming Mode's footer bar overlays the bottom of a plugin's full-screen route. Steam's own `SidebarNavigation` and `Tabs` keep their scrolling content clear of it, a plain scrolling `div` does not, and 96 px of bottom padding clears it at the Legion Go 2's scale | the overlay was seen on Peter's Legion Go 2; Decky Loader's Store uses `marginTop: 40px`, `height: calc(100% - 40px)` and Steam's `Tabs` (`frontend/src/components/store/Store.tsx`); the 96 px value is unverified on other screens | Decky Loader source, Peter's device |

## Built-in sign-in clients (ADR-0032)

| # | Fact | Status | Source |
|---|---|---|---|
| A155 | A Microsoft Entra registration for personal accounts with public client flows on lets any personal Microsoft account sign in through the device code flow with no secret and no publisher verification; publisher verification affects only work or school users | verified from Microsoft Learn (device code flow, publisher verification overview), 16 November 2026; unverified with Keepsake's own registration until Peter supplies its ID | Microsoft Learn |
| A156 | A Google client of type "TVs and Limited Input devices" requesting only `drive.appdata` (non-sensitive), published to Production, has no 100-user cap, no 7-day expiry and no unverified-app warning; its secret is not treated as confidential | verified from Google's limited-input device, Drive scopes and Manage App Audience pages, 16 November 2026; unverified with Keepsake's own client until Peter supplies it | Google documentation |

## Network install (ADR-0033)

| # | Fact | Status | Source |
|---|---|---|---|
| A157 | pysmb is pure Python under the zlib/libpng licence, needs only `pyasn1` (BSD-2-Clause), ships its own MD4, and speaks SMB1 and SMB2 but not SMB3. smbprotocol (MIT) speaks SMB 2.0.2 to 3.1.1 but needs `cryptography`, a compiled extension | verified from pysmb's `setup.py`, README and `smb/utils` folder, pyasn1's `LICENSE.rst`, and smbprotocol's PyPI page and `pyproject.toml`, 17 November 2026 | upstream repositories |
| A158 | udisks' `LoopSetup` takes an open file descriptor, so `udisksctl loop-setup` should work on an ISO inside a FUSE mount that only the user can read | the signature is verified from the UDisks2 Manager API page; whether it works on a gvfs or kio-fuse file is unverified until `network_mount_probe.py --loop-test` runs on a device | UDisks2 documentation |
| A159 | kio-fuse mounts a URL on request over the session bus: `org.kde.KIOFuse`, `/org/kde/KIOFuse`, `org.kde.KIOFuse.VFS.mountUrl(s) -> s` | verified from the kio-fuse README; unverified in Gaming Mode, where no KDE session runs | kio-fuse README |
| A161 | Every stdlib module pysmb 1.2.15 and pyasn1 0.6.5 import (`random`, `hmac`, `binascii`, `select`, `socket`, `string`, `struct`, `typing`, `math`, `codecs`, `collections`, `warnings` and others) exists in Decky's frozen Python | unverified; they import on Windows Python 3.14 with no tqdm or Twisted loaded (tested). If one is missing, SMB alone says so (ADR-0034) | local test |
| A162 | pysmb 1.2.15 negotiates SMB 2 with current Samba and Windows servers, signs when the server supports it, and cannot use shares that require SMB 3 encryption | from pysmb's README (SMB1 and SMB2) and source; unverified against a real NAS until the device run | pysmb source |
| A164 | ProtonDB's monthly dump (`reports/reports_<mon><n>_<year>.tar.gz` in `bdefore/protondb-data`) holds one JSON array, `reports_piiremoved.json`, with `app.steam.appId`, `timestamp`, `systemInfo.cpu` and `gpu`, and `responses.verdict`, `variant`, `protonVersion` or `customProtonVersion`, `launchOptions` and `notes` | verified by building from `reports_nov1_2026.tar.gz` (400,906 records; 16,498 games with handheld reports; 1.6 MB index), 17 November 2026 | the dump |
| A163 | WebDAV servers (Nextcloud, Apache `mod_dav`, NAS WebDAV services) answer `PROPFIND` with `Depth: 1` and a `207 Multi-Status` listing each child's `href`, `resourcetype` and `getcontentlength`, and serve files with plain `GET` | from RFC 4918 and the WebDAV store's behaviour; tested against a local server; unverified against Peter's NAS | RFC 4918 |
| A160 | `http.client` never follows redirects, and `ipaddress` may be missing from Decky's frozen Python | the first from the Python documentation; the second is unverified (imported lazily, and a missing module means plain http is refused) | Python documentation, ADR-0030 |

## PCGamingWiki (ADR-0031)

| # | Fact | Status | Source |
|---|---|---|---|
| A153 | PCGamingWiki's Cargo API needs a MediaWiki bot login (`meta=tokens` then `action=login`) with the Cargo grant since August 2026, uses tables `Game` and `Video`, and blocks an IP for a minute after a 429 | from Tuning Advisor's register; unverified from Keepsake until a real bot login is tried | Tuning Advisor |
