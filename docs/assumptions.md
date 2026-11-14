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
