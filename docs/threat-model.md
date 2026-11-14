# Threat model

Seeded from build prompt section 18 in slice 1 and extended every slice. Each entry has a mitigation or an accepted risk signed off by the owner before v1.0.0.

Status values: **planned** (mitigation designed, not built yet), **partial** (some of it built), **in place** (built and tested), **accepted** (risk accepted by the owner).

| ID | Threat | Mitigation | Status | Since |
|---|---|---|---|---|
| T1 | Token theft from disk | Mode 0600 token files, no logging, minimal scopes | planned (slice 6). Settings file already written 0600 through `fsutil.atomic_write_*` | 1 |
| T2 | Device code phishing | Flows start only from a user action and show the app name and expected domain | planned (slice 6) | 1 |
| T3 | Malicious or wrong manifest paths | Root confinement, traversal rejection, preview before first sync | partial: `safepath.validate_relative`, `join_within` and `ensure_within` with tests | 1 |
| T4 | Zip slip during restore | Validate every entry before extraction | planned (slice 5). Keys and relative paths already validated by `safepath` and `store.validate_key` | 1 |
| T5 | Cloud tampering or corruption | Hash verification of blobs and metadata. Encryption is a later option | planned (slices 5 to 7). `LocalFolderStore.put_new` returns SHA-256 | 1 |
| T6 | A game left frozen | Watchdog, `finally` blocks, resume on start | in place for the slice 1 freeze test: `freeze.Freezer` persists PIDs before stopping, fails closed if it cannot persist, runs a 30 second watchdog thread independent of asyncio, keeps an in-memory copy if the state file is corrupt, and `KeepsakeApp.start` resumes leftovers. Tested in `tests/test_freeze.py` and `tests/test_app.py` | 1 |
| T7 | The wrong process frozen | Environment matching, user ownership, ancestry checks | in place for the freeze test: `procs.find_game_processes` matches `STEAM_COMPAT_DATA_PATH`, `SteamGameId` or `SteamAppId`, filters by UID, never selects the plugin or its ancestors; resume checks process start time so a reused PID is never signalled | 1 |
| T8 | Writes outside the allowlist | Central path validation used by every write | partial: `safepath` and `PluginPaths.write_roots`; settings and store writes go through it. Slice 5 routes save writes through it | 1 |
| T9 | Secrets or personal data in logs or diagnostics | Redaction tests | in place: `redact.redact` on every log record and on the diagnostics export; non-stock usernames hidden; tests in `tests/test_redact_log.py` and `tests/test_diagnostics.py` | 1 |
| T10 | Malicious update via compromised repository or release | Protected tags, SHA-256 checks, signature verification. **Changed by ADR-0004:** no CI, so releases are built locally from a deterministic zip and the minisign signature with a key held only by the owner becomes the main control; anyone can rebuild a tag and compare hashes | partial: `main` protected and `v*` tags immutable (ADR-0005), Actions disabled. Release build and verification in slice 2 | 1 |
| T11 | Personal data committed to the public repository | Synthetic fixtures, `.gitignore`, pre-commit secret scan | in place: `scripts/secret_scan.py` (plain in-repo script, no third-party scanner), `.githooks/pre-commit`, `pnpm run check`, optional local denylist, `.gitignore` for settings, tokens and diagnostics | 1 |
| T12 | GitHub API rate limits | Caching and quiet failure | planned (slice 2) | 1 |
| T13 | Two devices racing | Create-only writes and fork detection | partial: `LocalFolderStore.put_new` is atomic create-only (hard link), tested with 8 racing writers | 1 |
| T14 | Clock skew | Hashes and parents decide | planned (slice 7) | 1 |
| T15 | A registry merge corrupting a prefix | Backup, key-level scope, re-parse validation | planned (slice 11) | 1 |

## Slice 1 additions

| ID | Threat | Mitigation | Status |
|---|---|---|---|
| T16 | Diagnostics export reveals the game list or device facts if shared | Export stays in the device settings folder, is redacted, and the slice report summarises it with generic names. Peter decides what to copy off the device | in place |
| T17 | Development deploy script runs `sudo` on the device | Development only, prompts for the password interactively, never stored; the plugin itself has no root flag | accepted for development; owner to confirm |
| T18 | Decky's installer reports installs to the Decky store server when a version string other than `dev` is passed | Decided in ADR-0002 during slice 2. Affects privacy, not integrity | open |
| T20 | Device test runner executes repository code on the device | Runs as the device user in a temporary folder under `~/.cache`, deleted afterwards; never touches the installed plugin or Decky; only run by the owner against their own device | accepted for development |
| T19 | Decky's installer extracts the zip with `ZipFile.extractall` | Decky's own responsibility; our release zips are built deterministically by `scripts/package.py` with safe entry names | accepted, noted |
