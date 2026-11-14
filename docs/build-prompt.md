# Keepsake Build Prompt

Working name Keepsake. Rename it before slice 1 if you prefer, then keep it fixed. The name becomes the plugin folder, the settings folder, the OneDrive app folder and the GitHub repository name.

## 0. Instructions for Claude Code

- Read this whole prompt before writing any code.
- Save this prompt as `docs/build-prompt.md` in the repository.
- Create `CLAUDE.md` in the repository root from sections 1 to 6, so the objective, principles, escalation rules and conventions persist across sessions. Keep it under 300 lines and link to `docs/build-prompt.md` for the detail.
- Work one slice at a time from section 16, each on its own branch.
- At the end of every slice, open a pull request, write the slice report, and stop. Do not start the next slice until Peter confirms the on-device checks.
- At the start of slice 1, ask Peter for the GitHub owner and repository name, and confirm the plugin name.
- Where this prompt conflicts with the Decky Loader source, the `@decky/ui` or `@decky/api` type definitions or the plugin template, the source wins. Record the difference in `docs/assumptions.md` and tell Peter.

## 1. Objective

Build Keepsake, a Decky Loader plugin that syncs PC game saves between SteamOS and Bazzite handhelds through cloud storage, operated entirely from Gaming Mode.

**Outcomes**
- Saves follow the player between devices with no Desktop Mode step at any point, including setup and cloud sign-in.
- Non-Steam shortcuts installed into their own Proton prefixes sync correctly, even though their compatdata IDs differ on each device.
- No save version is ever silently overwritten or lost.
- The plugin updates itself from its own menus in a few clicks.
- Source lives in Peter's public GitHub repository and CI builds every release.

## 2. Context

**Devices**
- Lenovo Legion Go 2 running SteamOS, user `deck`, home `/home/deck`.
- Lenovo Legion Go running SteamOS, user `deck`. It previously ran Bazzite, so Bazzite must stay supported, including `/var/home` symlinked to `/home` and usernames other than `deck`.
- SD card labels differ between devices. The two devices have different screens.

**Games**
- Many non-Steam games installed from ISO. The workflow is to add `setup.exe` as a non-Steam shortcut, install into that shortcut's Proton prefix, then change the shortcut target to the game exe. The game install folder therefore usually sits inside the prefix.
- Steam purchases, which already have Steam Cloud.

**Problem Keepsake solves**
- Non-Steam shortcut app IDs, and therefore `compatdata/<appid>` prefix folders, differ per device. On Peter's devices the same game sits in `compatdata/2826096683` on one device and `compatdata/4084545182` on the other.
- Ludusavi stores absolute paths and restores to the same path. rclone-based plugins sync raw path trees. decky-ludusavi and Spool need a separately installed desktop app. All of them fail this case or need manual per-game redirects.

**Interim setup being replaced**
- Ludusavi flatpak, the decky-ludusavi plugin and rclone to a personal OneDrive, with five manual redirects on the Legion Go. Keepsake must coexist with it during cutover, then replace it.

**Design basis**
- A research report recommended a snapshot DAG with canonical logical roots, native cloud APIs, device code sign-in, a pull before launch and a push after exit. This prompt implements that design.

## 3. Non-Negotiable Principles

1. **Never silently overwrite.** Whenever local and cloud have both changed, the user resolves a conflict.
2. **Snapshots are immutable.** Cloud objects are written once and never modified. Only retention deletes, and only within the protection rules in section 9.
3. **Every restore is reversible.** A local pre-restore snapshot is taken and verified before any local save file is replaced or removed.
4. **Hashes decide, timestamps inform.** Decisions about save data use content hashes and parent links. Timestamps are displayed but never pick a winner.
5. **Fail closed.** If discovery, resolution, hashing, auth or network is uncertain, do nothing destructive, tell the user and keep the game playable.
6. **Never write saves under a running game.** Restores happen only before launch, while the game is frozen, or after exit.
7. **Gaming Mode only.** No feature may need Desktop Mode, a terminal or a separately installed app.
8. **No root.** The backend runs as the user. `plugin.json` carries no root flag.
9. **No bundled binaries by default.** Python stdlib first, vendored pure-Python libraries second.
10. **Canonical paths.** Cloud data never contains absolute device paths, device usernames, compatdata IDs or SD card labels.
11. **A frozen game is always released.** A watchdog resumes any process the plugin pauses, whatever errors occur.
12. **Nothing personal in the public repository.** No tokens, account names, device names, real save files or Peter's game list. Test fixtures are synthetic.

## 4. Escalation Rules

Stop and ask Peter before doing any of the following. Record each decision in an ADR.

- Adding the root flag, a bundled binary or a `remote_binary` entry.
- Loosening any principle in section 3 or any safety gate default in section 9.
- Changing the cloud layout or snapshot schema after slice 6 merges.
- Writing anywhere outside the write allowlist in section 8.
- Editing `shortcuts.vdf`, launch options or any Steam setting, except the explicit per-game opt-in launch wrapper in section 10.
- Deleting cloud data outside retention.
- Adding network endpoints beyond the allowlist in section 6.
- Adding OAuth scopes beyond those in section 11.
- Using code from a GPL project or a project whose licence is unconfirmed.
- Changing repository visibility, branch protection or release signing.
- Installing updates by any route other than the hand-off to Decky's own installer in section 12.

## 5. Working Conventions

- **Branches.** One branch per slice, named `slice/NN-short-name`. Merge to `main` by pull request only, after Peter confirms the on-device checks.
- **Commits.** Conventional commits.
- **Docs every slice.** Update `docs/threat-model.md` (new entries, or "no change" with a reason), `docs/assumptions.md`, `CHANGELOG.md`, and add an ADR in `docs/adr/` for any design decision.
- **Slice report.** End every slice with `docs/slices/NN-report.md` covering what changed, test results, known gaps and the on-device checklist for Peter.
- **Language.** UK English in UI strings, docs, comments and commit messages. Never use em dashes or en dashes in any of them.
- **Verify before relying.** When unsure of a Decky or Steam client API, read the decky-loader source, the `@decky/ui` and `@decky/api` type definitions or the template. Record it in `docs/assumptions.md` as verified or unverified. Never guess API names.
- **Quality bar.** All backend logic has tests. No slice is done with failing tests, type errors, lint errors or a broken build.

## 6. Repository, Stack and Constraints

**Repository**
- Public GitHub repository owned by Peter. If it does not exist, create it as public with the GitHub CLI after Peter confirms the name.
- Protect `main`: pull requests only and CI must pass. Recommend Peter enables 2FA and protects release tags.
- Licence BSD-3-Clause, keeping the decky-plugin-template notice as the template requires. Attribute the Ludusavi manifest (MIT) wherever its data is used.
- Add `SECURITY.md`, `README.md`, `CONTRIBUTING.md` and `.gitignore` entries for local settings, tokens and diagnostics exports.

**Stack**
- Start from `SteamDeckHomebrew/decky-plugin-template` with pnpm 9, TypeScript, React, `@decky/ui` and `@decky/api`.
- Python backend with `main.py` as a thin entry point and all logic in `py_modules/keepsake`.
- Target the Python version embedded in the current stable Decky Loader. Verify it in slice 1 and record it.
- Stdlib first: `asyncio`, `sqlite3`, `hashlib`, `hmac`, `zipfile`, `json`, `urllib`, `ssl`. Confirm availability on device in slice 1, with a JSON fallback if `sqlite3` is missing.
- Vendored pure-Python libraries only, pinned with hashes. Candidates are `vdf`, a pure-Python YAML parser, and a QR encoder unless a JavaScript QR library is used in the frontend.
- HTTP via stdlib in worker threads unless slice 1 proves `aiohttp` is importable from plugin processes.

**Network allowlist**
- `login.microsoftonline.com` and `graph.microsoft.com`
- `oauth2.googleapis.com` and `www.googleapis.com`
- `raw.githubusercontent.com` for the Ludusavi manifest
- `api.github.com` and GitHub release asset downloads for update checks
- User-configured WebDAV and S3 endpoints

**Development environment**
- Peter develops on Windows. Backend tests must run on Linux, so use WSL or a Linux container where needed and document it in `docs/dev-setup.md`.
- Deploy to the devices over SSH using the template's deploy tasks. Document enabling SSH on SteamOS and Bazzite.

## 7. Architecture

**Frontend (TypeScript)**
- Quick Access Menu panel, a full-screen route, game lifecycle listeners, toasts and subscriptions to backend progress events.

**Backend modules (`py_modules/keepsake`)**
- `discovery` covers Steam roots, `libraryfolders.vdf`, `appmanifest_*.acf`, `shortcuts.vdf` for all Steam users, compatdata mapping and running-process inspection.
- `manifest` covers fetching with ETag, building a compact JSON index, title matching and path resolution.
- `roots` resolves logical roots per device.
- `snapshot` covers scanning, hashing, packing, atomic restore, safety gates, quarantine and retention.
- `store` holds the backend abstraction and its implementations.
- `auth` covers device code flows, token storage and refresh.
- `sync` covers the snapshot DAG, three-way decisions, adoption, conflicts and the offline queue.
- `lifecycle` covers session state, freeze and release, the launch wrapper gate and crash recovery.
- `update` covers release checks, verification and the hand-off to Decky's installer.
- `state` holds SQLite with versioned forward migrations.
- `health` and `log` cover health checks, redacted structured logs and diagnostics export.
- `importers` covers Ludusavi backup import.

**Concurrency**
- One job per game at a time through an asyncio queue. Auth and update run under global locks.
- Progress and results reach the frontend through backend events.

## 8. Canonical Model

**Game identity**
- `gameKey` is a normalised slug of the manifest title, for example `goat-simulator-3`. The user can override it and add aliases. The same game has the same key on every device.

**Logical roots**

| Root | Proton resolution | Native or other |
|---|---|---|
| `winAppData` | `<pfx>/drive_c/users/steamuser/AppData/Roaming` | |
| `winLocalAppData` | `<pfx>/drive_c/users/steamuser/AppData/Local` | |
| `winLocalAppDataLow` | `<pfx>/drive_c/users/steamuser/AppData/LocalLow` | |
| `winDocuments` | `<pfx>/drive_c/users/steamuser/Documents` | |
| `winSavedGames` | `<pfx>/drive_c/users/steamuser/Saved Games` | |
| `winPublic` | `<pfx>/drive_c/users/Public` | |
| `winProgramData` | `<pfx>/drive_c/ProgramData` | |
| `base` | Folder of the shortcut's exe or `StartDir`, inside or outside the prefix | `steamapps/common/<installdir>` |
| `home`, `xdgData`, `xdgConfig` | | Real home after `realpath` |
| `steamUserdata` | | `<steam>/userdata/<id3>` |
| `registry` | Manifest-listed keys in `<pfx>/user.reg` | |

**Prefix resolution**
- Read the shortcut's stored `appid` from `shortcuts.vdf`, convert it to unsigned 32-bit with `appid & 0xFFFFFFFF`, and look for `steamapps/compatdata/<unsigned>/pfx` in each library, base library first.
- At runtime, cross-check against `STEAM_COMPAT_DATA_PATH` in the running game's process environment. A mismatch blocks sync for that game and raises a health warning.
- Resolve the home folder with `realpath` so `/var/home` and `/home` are equivalent.

**Write allowlist**
- Resolved save paths under the logical roots of enabled games.
- The plugin's settings, runtime and log directories.
- Staging folders created beside the save folders being restored.
- Every resolved path must stay inside its root after `realpath`. Reject `..`, absolute paths from manifests and symlinks that escape a root.

**Default content**
- Sync manifest entries tagged `save`.
- Entries tagged `config` are off by default, because the two devices have different screens and config files often hold resolution and graphics settings. Allow a per-game opt-in.
- Default exclusions include logs, crash dumps, shader and web caches and temporary files. The user can edit exclusions per game.

## 9. Sync Model

**Cloud layout (inside the backend's app folder)**
```
registry/devices/<deviceId>.json
games/<gameKey>/config/<deviceSeq>-<deviceId>.json
games/<gameKey>/snapshots/<snapId>.json
games/<gameKey>/blobs/<snapId>.zip
games/<gameKey>/pruned/<snapId>
games/<gameKey>/prerestore/<snapId>.json and .zip   (only if upload of pre-restore snapshots is enabled)
```

- `snapId` is `<deviceSeq zero-padded to 6>-<deviceId short>-<contentHash prefix>`.
- Every object is written once. The blob is uploaded first and the metadata second, so the presence of metadata commits the snapshot. Readers ignore blobs without metadata, and retention removes them after a grace period.
- Game config revisions (aliases, custom paths, exclusions, tag choices) are write-once files. The newest revision applies, so custom paths defined on one device reach the other. Concurrent edits raise a warning. Timestamps may order config revisions because principle 4 applies to save data only.

**Snapshot metadata (schemaVersion 1)**
```json
{
  "schemaVersion": 1,
  "snapId": "000042-d3f1a9-9c1e0b7a",
  "gameKey": "goat-simulator-3",
  "parents": ["000041-d3f1a9-77ab01cd"],
  "deviceId": "d3f1a9c2-0000-0000-0000-000000000000",
  "deviceName": "Legion Go 2",
  "deviceSeq": 42,
  "created": "2026-11-14T13:23:18Z",
  "kind": "auto-exit",
  "flags": [],
  "contentHash": "sha256 over the sorted file list",
  "files": [
    {"root": "winLocalAppData", "rel": "Goat2/Saved/SaveGames/slot0.sav", "size": 1234, "sha256": "..."}
  ],
  "blobSha256": "...",
  "pluginVersion": "1.0.0"
}
```
- `kind` is one of `auto-exit`, `auto-recovered`, `manual`, `merge`, `import`, `provisional`.
- Each snapshot holds the complete file list, so deletions are implicit and need no tombstones.
- Each blob is a full zip of the snapshot's files, with entries stored as `<root>/<rel>`. Warn above 200 MB per game.
- The snapshot DAG is formed by `parents`. Heads are snapshots no other snapshot names as a parent. More than one head is a fork.

**Local state per device and game**
- Local shortcut app ID, prefix path, install folder and resolved roots.
- `base`, meaning the last snapshot this device restored or pushed, or none.
- Last scan hashes, `sessionOpen` with start time, job history, quarantined snapshots and up to five local pre-restore snapshots.

**Pull before launch**
1. Fetch snapshot metadata for the game, using the cache and ETags. Compute heads.
2. Scan local files under the resolved roots and hash them.
3. If this device has no `base` for the game (adoption):
   - No cloud snapshots: nothing to pull. The exit push uploads the first snapshot.
   - Cloud snapshots exist and no local files: restore the head and set `base`.
   - Both exist with equal `contentHash`: adopt the head as `base` silently.
   - Both exist and differ: raise an adoption conflict.
4. If `base` is set:
   - More than one head: fork, raise a conflict.
   - Neither side changed: launch.
   - Only the cloud changed: take and verify a local pre-restore snapshot, restore the head atomically, set `base` to the head.
   - Only the local side changed: launch. The exit push uploads it.
   - Both changed: raise a conflict.
5. Persist `sessionOpen` with the start time.

**Push after exit**
1. Scan and hash. If the files equal `base`, record a no-op and clear `sessionOpen`.
2. Apply the safety gates.
3. Re-fetch heads. If the head moved during play, upload the new snapshot with `parent = base`, which creates a fork, then raise a conflict. This keeps the data safe in the cloud rather than blocking.
4. Upload the blob, then the metadata. Verify the blob using the hash the backend reports, or by re-download where it reports none.
5. Set `base` to the new snapshot and clear `sessionOpen`.

**Safety gates (defaults)**
- Refuse a snapshot with zero files when `base` had files.
- Refuse a snapshot that removes more than 50% of `base`'s files.
- Refuse a snapshot whose total size falls by more than 70% against `base`.
- A refused snapshot is kept locally as quarantined, raises a warning toast and is never uploaded automatically. The user can release it with an explicit confirmation.
- Users may tighten gates. Loosening a default in code is an escalation item. User-adjustable thresholds have hard floors that cannot be disabled.

**Conflicts**
- Options are "Use cloud save", "Use this device's save" and "Decide later".
- Whichever side loses is always preserved as a pinned snapshot, so choosing never destroys data.
- "Use cloud save" takes and verifies a pre-restore snapshot, uploads the local state as a pinned snapshot, then restores the chosen head.
- "Use this device's save" uploads the local state as a `merge` snapshot whose parents are all current heads, and pins the losing heads for 30 days at least.
- "Decide later" launches with the local save, marks the game conflicted, disables auto-pull for it and keeps the conflict visible until resolved. The exit push uploads as a fork.
- Forks with several heads list each head with device, time, file count and size.

**Retention**
- Retention prunes blobs only. Metadata is kept for ancestry checks because it is tiny. A write-once marker in `pruned/` records each prune.
- Never pruned: pinned snapshots, every head, every device's `base`, the newest snapshot that passed the gates, and anything younger than 7 days.
- Otherwise keep the last 10 automatic snapshots, one per day for 30 days and one per month for 12 months.

**Crash recovery**
- On backend start and before every launch, any `sessionOpen` for a game that is not running triggers an exit push with kind `auto-recovered`, followed by the toast "Recovered missed exit backup for <game>".

**Offline and timeouts**
- If the store is unreachable at launch, release the game immediately and mark it pending. Reconcile when back online using the normal decision table.
- The launch pull has a timeout, default 20 seconds and configurable from 5 to 60. On timeout, release the game, mark it pending and toast "Cloud check timed out. Playing the local save."
- An idle loop runs every 30 minutes while online. It prefetches cloud heads into local staging and pushes enabled games whose local files changed with no open session, which covers games played while the plugin was not running.

## 10. Lifecycle Integration

**Game identification**
- Listen to the Steam client's app lifetime notifications and game action start events from the frontend. Slice 1 verifies whether non-Steam shortcuts report their real app ID or 0. If they report 0, use the running app details or the game action's ID, as decided in ADR-0001.
- In the backend, find the game's processes by reading `/proc/<pid>/environ` for `STEAM_COMPAT_DATA_PATH` matching the game's prefix, with `SteamGameId` as a secondary match. Only consider processes owned by the plugin's user.

**Launch gate (default mode, freeze)**
1. On launch, poll every 100 ms for up to 5 seconds for the game's processes to appear.
2. Freeze them and their descendants with `SIGSTOP`. Persist the frozen PIDs to state.
3. Run the pull. Restores at this point come from local staging where prefetch has already fetched the blob, so they are local disk only.
4. Resume every frozen PID with `SIGCONT` in a `finally` block.
5. A watchdog resumes everything after a hard ceiling of 30 seconds, whatever state the pull is in. On backend start, resume any PIDs still recorded as frozen.

**When the game cannot be frozen**
- If the processes cannot be identified in time, do not freeze. Run the pull checks anyway.
- If the cloud is newer and the game is already running unfrozen, do not restore. Mark the game pending and toast "Cloud has a newer save. Quit the game to load it."

**Launch gate (opt-in strict mode, wrapper)**
- A per-game toggle labelled "Strict launch gate" wraps the launch options with `<plugin dir>/bin/keepsake-gate %command%`, keeping any existing launch options intact. It needs an explicit confirmation.
- `keepsake-gate` is a shell script, not a binary. It waits for a ready file for that game in the runtime directory, with the same timeout as the launch pull, then executes the original command.
- Turning the toggle off restores the original launch options exactly. Store the originals before changing anything.
- Verify the Steam client method for reading and setting launch options in slice 8 and record it.

**Played without Keepsake**
- Compare `LastPlayTime` in `shortcuts.vdf` with the session log. A game played while the plugin was not running raises a health warning and is pushed on the next idle run.

## 11. Authentication and Credentials

**Microsoft OneDrive (personal accounts)**
- OAuth 2.0 device code flow against `https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode` and the matching token endpoint.
- Scopes `Files.ReadWrite.AppFolder offline_access`. No other scopes without escalation.
- Show the verification URL and user code as large text and as a QR code. Poll at the interval the server returns. Handle expiry, decline and slow-down responses.
- The client ID belongs to a public client app registration that Peter creates. Write `docs/setup-entra.md` with the steps: personal Microsoft accounts only, public client flows allowed, delegated `Files.ReadWrite.AppFolder` and `offline_access`. A public client ID is not a secret and may be committed.
- Use the OneDrive app folder through `/me/drive/special/approot`. Create-only uploads use `@microsoft.graph.conflictBehavior=fail`. Use upload sessions for files above 4 MB.

**Google Drive (slice 10)**
- Device flow for TVs and limited-input devices, with the narrowest scope the device flow allows (`drive.appdata` or `drive.file`, verified in slice 10).
- Because the repository is public, Google client credentials are never committed. The user enters them in Settings and `docs/setup-google.md` explains how to create them.

**WebDAV and S3 (slice 10)**
- Credentials are entered in Settings with the on-screen keyboard.
- Create-only writes use `If-None-Match: *`. S3 requests are signed with SigV4 implemented on stdlib `hmac` and `hashlib`.

**Token and credential storage**
- One file per backend in the settings directory with mode `0600`.
- Never logged, never included in diagnostics exports, never sent anywhere except the issuing endpoint.
- Refresh proactively. Raise a health warning when refresh fails, and keep queued pushes until sign-in is restored.

## 12. Update Feature

Peter must be able to update Keepsake from inside the plugin in a few clicks, without the Decky store and without Desktop Mode.

**Behaviour**
- The plugin checks GitHub Releases for the repository at most once every 24 hours and whenever the user presses "Check for updates".
- Two channels, Stable (default) and Pre-release, chosen in Settings.
- When a newer version exists, the Quick Access Menu shows an "Update available" row with the version. Opening it shows the release notes and an "Update now" button.
- "Update now" verifies the release, then hands the install to Decky Loader's own installer, which shows Decky's confirmation, replaces the plugin and reloads it. Total interaction is open, review, confirm.
- After the reload, a toast confirms "Updated to vX.Y.Z" and the state database migrates forward.
- The Updates page lists previous releases, and any of them can be installed through the same path for rollback.

**Install hand-off**
- Use the mechanism Decky Loader itself uses for Settings, Developer, "Install plugin from URL", or the plugin update API added in Decky Loader 3.3, whichever slice 1 proves most stable. Pass the release zip URL, plugin name, version and expected SHA-256 so Decky verifies the download.
- Record the chosen mechanism, the Decky versions it was tested on and the fallback in ADR-0002.
- If the hand-off is unavailable on a given Decky version, show the release zip URL as text and a QR code with short instructions for installing from URL. A self-updating root backend is an escalation item and is not the fallback.

**Verification (before the hand-off)**
- Must: download `SHA256SUMS` from the release and take the expected hash of the zip from it. Decky's installer then checks the downloaded zip against that hash.
- Should: verify a minisign signature over `SHA256SUMS` with a public key pinned in the plugin source. Implement Ed25519 verification in vendored pure Python, with BLAKE2b from `hashlib`. Without a valid signature, refuse to install and explain why.

**Guards**
- Never update while a sync job runs or a game session is open. Show "Update after the current sync" and offer to update when idle.
- Handle GitHub rate limits and failures quietly. Cache responses with ETag. Unauthenticated requests only.
- Settings, tokens and state live in the settings directory, which an update must leave untouched.
- If the state database schema is newer than the installed plugin supports, which happens after a rollback, open in read-only safe mode and tell the user to update.
- The cloud snapshot schema carries `schemaVersion`. A plugin never writes to a game whose cloud data uses a newer schema than it understands.

**First install (documented in README)**
- Decky Loader, Settings, General, enable Developer mode, then Developer, Install plugin from URL, and paste the latest release zip URL. Every update after that happens inside Keepsake.

## 13. Release Pipeline

- **Version source of truth.** `package.json`. CI fails if any other version field disagrees or if the tag does not match.
- **On pull requests.** Lint, type check, backend tests and a full build.
- **On a tag `vX.Y.Z` or `vX.Y.Z-beta.N` on `main`:**
  - build, run tests and package the zip in the layout Decky expects (mirror the template's packaging and prove install from URL works with it in slice 2)
  - generate `SHA256SUMS`
  - sign it with minisign when the `MINISIGN_SECRET_KEY` repository secret is present
  - create the GitHub Release with the zip, `SHA256SUMS` and the signature, using that version's `CHANGELOG.md` section as release notes
  - mark `-beta.N` tags as pre-releases
- **Release helper.** Provide `pnpm release <version>`, which bumps the version, checks the changelog has a section for it, commits, tags and pushes. Document Peter's release steps in `docs/releasing.md`.
- **Executable bits.** Preserve them in the zip for `bin/keepsake-gate`.

## 14. Gaming Mode UX

Everything works with the controller alone. Text entry uses the Steam on-screen keyboard. No modal can be dismissed into data loss.

**Quick Access Menu panel**
- Status line with backend, account, last sync and a health badge.
- "Update available" row when relevant.
- Current game card while a game runs, showing synced, pending, conflicted or quarantined.
- Buttons "Sync now" and "Open Keepsake".

**Full-screen route, with tabs**
- **Games.** List with status icons, filtered by enabled or all.
- **Per-game page.**
  - enable toggle and matched title with "Change match"
  - resolved roots with a file preview and counts
  - include config files toggle, custom paths (through the Decky file picker) and exclusions
  - launch gate mode (freeze, strict wrapper or off)
  - history with restore and pin, and last sync per device
- **Conflicts.** All open conflicts.
- **History.** Recent snapshots across games, with restore, pin and release quarantine.
- **Settings.**
  - device name
  - backend and sign-in
  - idle sync interval and launch pull timeout
  - safety gate thresholds within their floors
  - Steam apps behaviour
  - update channel and Updates page
- **Logs and Diagnostics.** Log viewer, health checks and diagnostics export.

**Setup wizard (first open)**
1. Device name.
2. Choose backend and sign in with the QR code.
3. Scan games.
4. Review matches.
5. Enable games.
6. Dry-run plan showing per game whether it will push, pull, adopt or conflict.
7. Confirm.

**Conflict modal**
- Shows each side's device, time, file count, size and number of changed files.
- Initial focus sits on "Decide later". The B button means "Decide later". Destructive-looking choices need an explicit press.

**Toasts**
- Sync complete (can be silenced), conflict raised, snapshot quarantined, missed backup recovered, update available, sign-in needs attention.

**Steam apps**
- Off by default because Steam Cloud covers them. They can be enabled per game. Non-Steam shortcuts are never skipped for cloud reasons.

## 15. Health, Logging and Diagnostics

**Health checks**
- Sign-in valid and cloud reachable.
- Last successful push and pull per enabled game.
- Sessions left open, quarantined snapshots and unresolved conflicts.
- Prefix mismatches and games played without Keepsake running.
- Manifest age.
- decky-ludusavi detected with auto-sync active for a game Keepsake also manages.

**Logging**
- Structured JSON lines in the Decky plugin log directory, rotated.
- Tokens, codes, credentials and account identifiers are redacted. Paths are logged relative to logical roots where possible.

**Diagnostics export**
- One JSON file in the settings directory with environment facts, check results and recent redacted log lines. Its path is shown so it can be copied off over SSH if needed.

## 16. Slices

Every slice ends with tests passing, the threat model, assumptions and changelog updated, the slice report written, a pull request open and Claude Code stopped for Peter's on-device checks.

### Slice 1. Skeleton, dev loop and on-device diagnostics
**Scope**
- Repository setup, template, licence, `CLAUDE.md`, docs skeleton and CI for pull requests.
- Settings store, log viewer route, `LocalFolderStore` stub.
- A Diagnostics page recording the following on device:
  - Python version and availability of `sqlite3`, `ssl` and `aiohttp`
  - the Decky environment variables, and write access to `compatdata` as the plugin user
  - lifetime notification and game action payloads for a Steam app and for a non-Steam shortcut
  - running app details from the frontend
  - `shortcuts.vdf` app IDs with signed and unsigned values and whether the matching compatdata folder exists
  - the running game's process tree with its `STEAM_COMPAT_DATA_PATH`
  - suspend and resume notification names
  - which Decky install or update mechanism is available to plugins
  - a manual freeze test button that freezes the running game for 5 seconds behind the watchdog
**Acceptance**
- Installs on both devices and survives a plugin reload. No root flag.
- Diagnostics export produced on both devices and summarised in the slice report.
- ADR-0001 (game identification and freeze approach) and ADR-0002 (update hand-off) drafted from real results.

### Slice 2. Release pipeline and in-plugin updater
**Scope**
- Section 13 in full and section 12 Must items.
- Pre-release channel, release notes view, rollback list and guards.
**Acceptance**
- Tagging `v0.2.0` produces a GitHub Release with zip and `SHA256SUMS`.
- On both devices, a plugin at `v0.2.0` sees `v0.2.1` and updates through the menu with Decky's confirmation only, then shows the toast.
- Rollback to `v0.2.0` works the same way.
- An update is refused while a fake sync job is running.

### Slice 3. Discovery
**Scope**
- Steam roots including Bazzite paths, libraries, Steam apps, `shortcuts.vdf` for all users with the most recent user as default, unsigned ID conversion, prefix mapping and the runtime cross-check.
- Steam versus shortcut classification.
**Acceptance**
- Unit tests with synthetic binary VDF fixtures cover signed and unsigned IDs, several users and missing prefixes.
- On device, the Games list shows Peter's shortcuts with correct prefixes on both devices, including one known to differ between them.

### Slice 4. Manifest resolution and save preview
**Scope**
- Fetch the Ludusavi manifest from `raw.githubusercontent.com/mtkennerly/ludusavi-manifest/master/data/manifest.yaml` with ETag and a weekly background refresh.
- Build the compact JSON index. Read the manifest format documentation in that repository before implementing placeholders and `when` conditions.
- Matching:
  - Steam apps by Steam ID
  - shortcuts by normalised title (case, punctuation, edition suffixes, roman numerals) with aliases and a manual pick
- Logical root resolution, `save` and `config` tags, custom paths and exclusions.
- Preview screen with file counts.
**Acceptance**
- Unknown placeholders skip the entry rather than guessing. Path traversal and escaping symlinks are rejected in tests.
- Parse time and peak memory are measured on device. If parsing exceeds 120 seconds or 400 MB, stop and propose an alternative to Peter.
- Ten of Peter's games resolve to existing files on both devices with matching relative paths.

### Slice 5. Snapshot engine and safety rails
**Scope**
- Scanning, hashing, zip packing with traversal-safe extraction, atomic restore (stage beside the target, fsync, rename), pre-restore snapshots, gates, quarantine, pinning and retention, all against `LocalFolderStore`.
**Acceptance**
- Property tests prove that restoring a snapshot reproduces the scanned state exactly.
- Deletion-only and empty snapshots are refused and quarantined.
- Retention never prunes protected snapshots.
- An interrupted restore leaves either the old state or the new state, never a mix.

### Slice 6. OneDrive sign-in and Graph store
**Scope**
- Device code flow with QR code, token storage and refresh, the app folder store with create-only uploads, upload sessions and hash verification.
- Device registry entry.
**Acceptance**
- Sign-in completes on both devices using only a phone.
- Tokens refresh after expiry without user action.
- Store contract tests pass against a local fake and against OneDrive.
- A create-only conflict is detected correctly, with the behaviour recorded in `docs/assumptions.md`.
- The cloud layout and schema are frozen from this merge onwards.

### Slice 7. Sync engine
**Scope**
- DAG and heads, adoption, the decision table, forks, merges, conflict records, the offline queue, prefetch staging and the idle loop.
**Acceptance**
- A two-device simulator sharing one `LocalFolderStore`, with skewed fake clocks, covers no-op, pull, push, adoption, conflict, fork, merge, offline then reconcile, and a push racing a pull.
- An invariant check proves no file version that ever existed in a snapshot or on a device is lost across randomised operation sequences.

### Slice 8. Lifecycle integration
**Scope**
- Section 10 in full, including the freeze gate, watchdog, crash recovery, the strict wrapper and the played-without-Keepsake check.
**Acceptance**
- On device, playing on the Legion Go 2 and then launching on the Legion Go loads the Legion Go 2 save with no Desktop Mode.
- Killing Steam during a game produces a recovered backup on the next start.
- The watchdog always releases a game in a forced-failure test.
- The strict wrapper round-trips launch options exactly.

### Slice 9. Gaming Mode UX complete
**Scope**
- Section 14 in full, plus the health checks and diagnostics in section 15.
**Acceptance**
- Peter completes the setup wizard, a conflict resolution and a history restore with the controller alone on both devices.
- The conflict modal cannot be dismissed into data loss.

### Slice 10. Additional backends and Ludusavi import
**Scope**
- WebDAV, S3 and Google Drive stores.
- Ludusavi import that reads `mapping.yaml` and zips, maps absolute Proton paths to logical roots by detecting the `compatdata/<id>/pfx/drive_c/users/steamuser` pattern, and writes `import` snapshots.
**Acceptance**
- Store contract tests pass for every backend.
- Peter's existing Ludusavi backups import for at least three games and restore correctly on the other device.

### Slice 11. Registry saves, Steam Cloud detection and suspend snapshots
**Scope**
- Key-level export and merge of manifest-listed registry keys in Wine `user.reg` format, with backup and re-parse validation, only while the game is not running and off by default per game.
- Detecting Steam Cloud enablement for Steam apps so they can be labelled and bulk-enabled when they lack cloud support.
- Provisional snapshots on suspend that another device never adopts without a prompt.
**Acceptance**
- Registry round-trip tests on synthetic `user.reg` files pass, and a corrupt merge is impossible in fault-injection tests.
- Each feature sits behind its own setting.

### Slice 12. Hardening, documentation and cutover
**Scope**
- README with install and first-run steps, setup guides, troubleshooting, security review of the threat model, performance check with 50 games, and the cutover plan in section 19.
**Acceptance**
- A clean install from the release URL works on SteamOS and on Bazzite.
- Every threat model entry has a mitigation or an accepted risk signed off by Peter.
- `v1.0.0` released.

## 17. Testing Strategy

- **Backend.** pytest, with Hypothesis as a development dependency only.
- **Fixtures.** Synthetic binary VDF files generated in tests, fake prefixes in temporary folders, and a fake Graph server built on `http.server` for contract tests.
- **Two-device simulator.** Two fake devices with separate prefixes, different compatdata IDs, different usernames and `/var/home` style symlinks, sharing one store. Fake clocks with skew. Fault injection for network drops, partial uploads and crashes mid-restore.
- **Frontend.** Type check, lint and build in CI. Keep UI logic thin so behaviour is tested in the backend.
- **On-device checklists.** Each slice report lists the exact steps for Peter, using generic game names in the repository and Peter's own games only on his devices.

## 18. Threat Model Seed

Create `docs/threat-model.md` in slice 1 with these entries, then extend it every slice.

- **T1.** Token theft from disk. Mitigated by mode `0600`, no logging, minimal scopes.
- **T2.** Device code phishing. Flows start only from a user action and show the app name and the expected domain.
- **T3.** Malicious or wrong manifest paths. Mitigated by root confinement, traversal rejection and preview before first sync.
- **T4.** Zip slip during restore. Mitigated by validating every entry before extraction.
- **T5.** Cloud tampering or corruption. Mitigated by hash verification of blobs and metadata. Encryption is a later option.
- **T6.** A game left frozen. Mitigated by the watchdog, `finally` blocks and resume on start.
- **T7.** The wrong process frozen. Mitigated by environment matching, user ownership checks and ancestry checks.
- **T8.** Writes outside the allowlist. Mitigated by central path validation used by every write.
- **T9.** Secrets or personal data in logs or diagnostics. Mitigated by redaction tests.
- **T10.** A malicious update through a compromised repository or release. Mitigated by protected branches and tags, CI-only releases, SHA-256 checks and signature verification.
- **T11.** Personal data committed to the public repository. Mitigated by synthetic fixtures, `.gitignore` rules and a pre-commit secret scan.
- **T12.** GitHub API rate limits. Mitigated by caching and quiet failure.
- **T13.** Two devices racing. Mitigated by create-only writes and fork detection.
- **T14.** Clock skew. Mitigated because hashes and parents decide.
- **T15.** A registry merge corrupting a prefix. Mitigated by backup, key-level scope and re-parse validation.

## 19. Cutover from the Interim Setup

1. Install Keepsake on the Legion Go 2 and complete the wizard. Enable the non-Steam games and let the first pushes run. The Legion Go 2 is the starting source.
2. Install Keepsake on the Legion Go and complete the wizard. Shared games already restored from the Legion Go 2 adopt silently because their hashes match. Any differences raise conflicts.
3. Optionally import the Ludusavi history (slice 10).
4. While both tools are active, Keepsake warns about games that decky-ludusavi also auto-syncs. Disable decky-ludusavi auto-sync for those games.
5. After two weeks without issues, remove decky-ludusavi and the Ludusavi flatpak. The five interim Ludusavi redirects go with it.

## 20. Out of Scope for v1

- Windows companion app.
- Client-side encryption.
- Emulator saves.
- Replacing Steam Cloud for Steam apps by default.
- Decky Plugin Store submission, which can follow later.