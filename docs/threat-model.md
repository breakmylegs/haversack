# Threat model

Seeded from build prompt section 18 in slice 1 and extended every slice. Each entry has a mitigation or an accepted risk signed off by the owner before v1.0.0.

Status values: **planned** (mitigation designed, not built yet), **partial** (some of it built), **in place** (built and tested), **accepted** (risk accepted by the owner).

| ID | Threat | Mitigation | Status | Since |
|---|---|---|---|---|
| T1 | Token theft from disk | Mode 0600 token files, no logging, minimal scopes | planned (slice 6). Settings file already written 0600 through `fsutil.atomic_write_*` | 1 |
| T2 | Device code phishing | Flows start only from a user action and show the app name and expected domain | planned (slice 6) | 1 |
| T3 | Malicious or wrong manifest paths | Root confinement, traversal rejection, preview before first sync | in place (slice 4): `resolve.to_logical` rejects unknown placeholders, `..`, `.`, absolute paths and drive letters; `resolve.scan` keeps every match inside its root after `realpath` and never follows symlinked folders; `resolve.safe_base` refuses over-broad `base` roots; the Games page previews files before any sync. Tests in `tests/test_resolve.py` (symlink cases run on device) | 1 |
| T4 | Zip slip during restore | Validate every entry before extraction | planned (slice 5). Keys and relative paths already validated by `safepath` and `store.validate_key` | 1 |
| T5 | Cloud tampering or corruption | Hash verification of blobs and metadata. Encryption is a later option | planned (slices 5 to 7). `LocalFolderStore.put_new` returns SHA-256 | 1 |
| T6 | A game left frozen | Watchdog, `finally` blocks, resume on start | in place for the slice 1 freeze test: `freeze.Freezer` persists PIDs before stopping, fails closed if it cannot persist, runs a 30 second watchdog thread independent of asyncio, keeps an in-memory copy if the state file is corrupt, and `KeepsakeApp.start` resumes leftovers. Tested in `tests/test_freeze.py` and `tests/test_app.py` | 1 |
| T7 | The wrong process frozen | Environment matching, user ownership, ancestry checks | in place for the freeze test: `procs.find_game_processes` matches `STEAM_COMPAT_DATA_PATH`, `SteamGameId` or `SteamAppId`, filters by UID, never selects the plugin or its ancestors; resume checks process start time so a reused PID is never signalled | 1 |
| T8 | Writes outside the allowlist | Central path validation used by every write | partial: `safepath` and `PluginPaths.write_roots`; settings and store writes go through it. Slice 5 routes save writes through it | 1 |
| T9 | Secrets or personal data in logs or diagnostics | Redaction tests | in place: `redact.redact` on every log record and on the diagnostics export; non-stock usernames hidden; tests in `tests/test_redact_log.py` and `tests/test_diagnostics.py` | 1 |
| T10 | Malicious update via compromised repository or release | Protected tags, SHA-256 checks, signature verification. **Changed by ADR-0004:** no CI, so releases are built locally from a deterministic zip and the minisign signature with a key held only by the owner becomes the main control; anyone can rebuild a tag and compare hashes | partial: `main` protected and `v*` tags immutable (ADR-0005), Actions disabled. Slice 2: `scripts/release.py` builds deterministic zips and signs `SHA256SUMS` when a minisign key is set; the updater requires a `SHA256SUMS` entry and Decky checks the zip against it. **Gap:** the plugin does not yet verify the minisign signature (build prompt "Should"), so a compromised GitHub account could publish a matching zip and `SHA256SUMS`. Planned for slice 12 | 1 |
| T11 | Personal data committed to the public repository | Synthetic fixtures, `.gitignore`, pre-commit secret scan | in place: `scripts/secret_scan.py` (plain in-repo script, no third-party scanner), `.githooks/pre-commit`, `pnpm run check`, optional local denylist, `.gitignore` for settings, tokens and diagnostics | 1 |
| T12 | GitHub API rate limits | Caching and quiet failure | in place: at most one automatic check a day, ETag `If-None-Match`, 403 and 429 keep the cache and report quietly, unauthenticated requests only (`keepsake.update`, tests in `tests/test_update.py`) | 1 |
| T13 | Two devices racing | Create-only writes and fork detection | partial: `LocalFolderStore.put_new` is atomic create-only (hard link), tested with 8 racing writers | 1 |
| T14 | Clock skew | Hashes and parents decide | planned (slice 7) | 1 |
| T15 | A registry merge corrupting a prefix | Backup, key-level scope, re-parse validation | planned (slice 11) | 1 |

## Slice 1 additions

| ID | Threat | Mitigation | Status |
|---|---|---|---|
| T16 | Diagnostics export reveals the game list or device facts if shared | Export stays in the device settings folder, is redacted, and the slice report summarises it with generic names. Peter decides what to copy off the device | in place |
| T17 | Development deploy script runs `sudo` on the device | Development only, prompts for the password interactively, never stored; the plugin itself has no root flag | accepted for development; owner to confirm |
| T18 | Decky's installer reports installs to the Decky store server when a version string other than `dev` is passed | ADR-0002: Keepsake passes `dev`, so no store POST is made | in place (slice 2) |
| T20 | Device test runner executes repository code on the device | Runs as the device user in a temporary folder under `~/.cache`, deleted afterwards; never touches the installed plugin or Decky; only run by the owner against their own device | accepted for development |
| T21 | Network calls to hosts outside the allowlist, including through redirects | `keepsake.net` allows only HTTPS to allowlisted hosts, checks every redirect target, rejects credentials in URLs and caps response size | in place (slice 2), tests in `tests/test_net.py` |
| T22 | An update while a sync job or game session is running corrupts state | `JobTracker` guard in `Updater.prepare`; "Update when idle" waits for the idle event | in place (slice 2) |
| T23 | A rollback deletes settings written by the newer version, or the older version writes data it does not understand | Unknown settings keys are preserved on write; a newer `schemaVersion` opens read-only safe mode that never writes | in place (slice 2), tests in `tests/test_settings.py` |
| T24 | Release signing key leaked or committed | Key kept outside the repository; `.gitignore` blocks common key filenames; secret scan flags minisign secret key headers | in place, owner to keep the key offline |
| T25 | Discovery results (absolute paths, per-device app IDs, Steam account id3) leak into cloud data or logs | Discovery output stays on the device and is never uploaded (principle 10); account and persona names in `loginusers.vdf` are never read into results; scan logs record counts only | in place (slice 3), test `test_results_carry_no_account_names` |
| T26 | Wrong prefix chosen for a shortcut, so a later restore writes into another game's prefix | Prefix from the shortcut's own app ID, `pfx` must exist, base library first; runtime cross-check records mismatches; a mismatch or an unreadable mismatch file blocks sync (fail closed) | in place (slice 3); enforced by sync from slice 7 |
| T27 | Tampered or malformed manifest download (compromised upstream or transit) | HTTPS to an allowlisted host; streaming subset parser that skips unsupported entries; size cap (64 MB); an empty index never replaces a good one; manifest paths are confined to logical roots (T3), so the worst case is wrong or missing files in the preview, not writes elsewhere | in place (slice 4); accepted that the manifest is unsigned |
| T28 | Custom paths chosen in the file picker point outside the game's folders | Converted to root plus relative path; refused unless inside one of the game's roots; relative paths validated | in place (slice 4), tests in `tests/test_gameconfig.py` |
| T19 | Decky's installer extracts the zip with `ZipFile.extractall` | Decky's own responsibility; our release zips are built deterministically by `scripts/package.py` with safe entry names | accepted, noted |
