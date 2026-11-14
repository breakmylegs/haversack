# Slice 2 report: release pipeline and in-plugin updater

- Branch: `slice/02-release-updater`, stacked on `slice/01-skeleton` (slice 1 is not merged yet)
- Version: 0.2.0
- Date: 14 November 2026
- Started before the slice 1 on-device checks, at your request ("keep going and make the best decisions for me"). Nothing is merged or released; both pull requests wait for your device checks.

## What changed

**Repository settings (ADR-0005)**
- GitHub Actions disabled. `main` requires a pull request (applies to admins, no force push, no deletion). Tags `v*` cannot be moved or deleted.

**Backend**
- `net.py`: HTTPS-only client with a host allowlist enforced on every redirect, response size cap, certifi bundle when present.
- `update.py`: GitHub Releases check (at most once a day, ETag, quiet failure on rate limits and offline), Stable and Pre-release channels, release selection, `SHA256SUMS` parsing, `prepare()` returning the arguments for Decky's installer, install type (update, downgrade, reinstall), startup notice after an update.
- `jobs.py`: job and session tracker. Updates are refused while anything is active; an idle event lets the frontend "Update when idle".
- `settings.py`: `updateChannel`; unknown keys preserved so rollbacks never delete settings; read-only safe mode for a newer `schemaVersion`.
- `app.py`: `get_status`, `check_for_updates`, `prepare_update`, `take_startup_notice`, `simulate_sync_job`, global update lock.

**Frontend**
- Updates page: current version, check for updates, release notes, "Update now", "Install this version" for every complete release (rollback), "Update when idle", and the URL plus QR fallback.
- Quick Access Menu: version, "Update available" row, safe mode notice. Toasts "Update available" (once per version) and "Updated to vX.Y.Z".
- Settings: "Include pre-releases" toggle; read-only safe mode notice.
- Diagnostics: "Simulate sync job" (60 seconds) to test the guard.
- `qrcode-generator` 2.0.4 (MIT, no dependencies) for the QR code.

**Release pipeline (section 13, run locally per ADR-0004)**
- `scripts/release.py prepare <version>`: checks clean, current `main` and a changelog section, bumps `package.json` on `release/v<version>` and opens a pull request.
- `scripts/release.py publish --device-tested [--dry-run]`: runs `pnpm run check`, builds the zip, writes `SHA256SUMS`, signs with minisign when `KEEPSAKE_MINISIGN_KEY` is set, tags, pushes the tag and creates the GitHub Release with the changelog notes; `-beta.N` is marked pre-release.
- `.gitattributes` forces LF so builds match across Windows and Linux. Existing files were renormalised.
- `docs/releasing.md`.

## Decisions made for you

1. **Hand-off with version `dev` (ADR-0002 option B).** Decky's prompt says "dev" rather than the version, but Decky then makes no call to its store server (T18). Keepsake's Updates page shows the real version and notes first, and the SHA-256 pins the exact zip.
2. **Two-step release** because `main` is protected: a version-bump pull request, then publish on `main`.
3. **`publish` requires `--device-tested`** so a release cannot skip the Linux tests.
4. **minisign in-plugin verification deferred** to slice 12 (it is a "Should" in the build prompt). Signing is ready now. Recorded as a T10 gap.
5. **Settings rollback safety**: unknown keys are preserved, which goes slightly beyond the build prompt and closes a data-loss path.

## Differences from the build prompt

- Section 13 "on a tag, CI builds and publishes" is replaced by `scripts/release.py publish` (ADR-0004).
- "Decky Loader 3.3 plugin update API" does not exist as a plugin route; `utilities/install_plugin` is used (ADR-0002).

## Test results

Local, Windows, Python 3.14.3:

- New and changed tests run by name: `tests/test_net.py`, `tests/test_update.py`, `tests/test_release.py`, `tests/test_settings.py`, `tests/test_app.py`: all passed (the one skip is a `posix` test).
- `pnpm run check`: all checks passed (ESLint, tsc, build, versions, packaging, ruff, ruff format, mypy, secret scan).
- `scripts/release.py publish --dry-run` on this branch: gate passed, assets built, `SHA256SUMS` matches the zip's SHA-256, no tag or release created. Unsigned (no key configured).
- Mutation checks: 13 guards broken one at a time, each caught by its test with a real failure (syntax errors excluded): busy guard, missing zip in `SHA256SUMS`, disallowed zip host, daily throttle, rate-limit handling, channel and completeness selection, redirect allowlist, safe mode, preserved keys, job tracker, `--device-tested`, failing checks stop publish, beta marked pre-release.

## Known gaps

- Nothing in slices 1 or 2 has run on a device.
- No release exists yet: v0.2.0 and v0.2.1 can only be published after slices 1 and 2 merge.
- In-plugin minisign verification (T10 gap).
- No SQLite state database yet, so "state database migrates forward" is limited to the settings schema check.

## On-device checklist (after slice 1's checklist)

Acceptance needs real releases, so the order is:

1. Confirm slice 1 on both devices and merge PR 1, then merge this PR.
2. (Optional) set up minisign as in `docs/releasing.md`.
3. On `main`: `pnpm run test:device`, then `pnpm release publish --device-tested` to publish **v0.2.0**. Check the GitHub Release has the zip and `SHA256SUMS`.
4. On both devices, install v0.2.0 the first-install way: Decky, Settings, Developer, Install plugin from URL, with the zip URL from the release.
5. Add a `## [0.2.1]` changelog section (any small change), `pnpm release prepare 0.2.1`, merge, then publish.
6. On each device: open Keepsake, Updates, "Check for updates". Expect "Update available: v0.2.1" (and the Quick Access row). Press "Update now", confirm Decky's prompt. Expect the plugin to reload and the toast "Updated to v0.2.1".
7. Updates, v0.2.0, "Install this version". Confirm. Expect "Updated to v0.2.0".
8. Diagnostics, "Simulate sync job", then within 60 seconds Updates, "Update now". Expect "Update after the current sync" and an "Update when idle" button; press it and expect the update to be offered when the job finishes.
9. Settings, "Include pre-releases" on and off: the channel line on Updates changes.
10. Note whether Decky's prompt says "dev", and fill the results table in ADR-0002.
