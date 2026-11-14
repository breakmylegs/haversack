# Slice 1 report: skeleton, development loop and on-device diagnostics

- Branch: `slice/01-skeleton`
- Version: 0.1.0
- Date: 14 November 2026

## What changed

**Repository**
- Public repository `breakmylegs/keepsake`, BSD-3-Clause with the template notice, `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `CLAUDE.md` (sections 1 to 6), `docs/build-prompt.md`.
- `.gitignore` covers local settings, tokens, diagnostics exports, `deploy.local.json` and the secret scan denylist.
- CI on every pull request: ESLint, `tsc`, Rollup build, version consistency, packaging (zip uploaded as an artifact), ruff, mypy (strict), pytest on Python 3.11 and 3.14, and the secret scan. Actions pinned to commit SHAs.
- `scripts/secret_scan.py` with `.githooks/pre-commit` (no third-party scanner, per your standing rule).
- `scripts/package.py` (deterministic Decky zip), `scripts/deploy.py` (SSH deploy), `scripts/check_versions.py`.

**Backend (`py_modules/keepsake`)**
- `app.py`: testable core; `main.py` is a thin forwarder.
- `settings.py`: JSON settings, atomic, mode 0600, device ID and device name.
- `log.py`, `redact.py`: JSON-lines log with rotation, every record redacted.
- `safepath.py`: central path validation (T3, T8).
- `vdf.py`: binary and text VDF readers (no writer).
- `discovery.py`: Steam roots (including Flatpak and `/var/home`), libraries, user IDs, `shortcuts.vdf`, unsigned app ID, compatdata lookup.
- `procs.py`: `/proc` inspection and game process matching (T7).
- `freeze.py`: freeze and release with persisted PIDs, fail-closed persistence, 30 second watchdog thread, start-time check on resume, startup recovery (T6).
- `store/`: `Store` contract and `LocalFolderStore` with atomic create-only writes.
- `diagnostics.py`: environment, Steam probe, process tree, HTTPS test, probe event log, redacted export.

**Frontend**
- Quick Access Menu panel with device name and "Open Keepsake".
- Full-screen route `/keepsake` with Diagnostics, Logs and Settings pages.
- Background probes recording Steam lifetime notifications, game action starts, suspend and resume, running app details and visible Decky install routes.

**Docs**
- `docs/threat-model.md` (T1 to T15 seeded, T16 to T19 added), `docs/assumptions.md` (29 entries), `docs/dev-setup.md`, ADR-0001 and ADR-0002 drafts, ADR-0003 (tooling, accepted).

## Differences from the build prompt (source wins)

1. **The Decky 3.3 "plugin update API" is not a plugin install route.** PR 992 is a store-side update check. The viable hand-off is the websocket route `utilities/install_plugin`, which Decky's "Install plugin from URL" uses. It shows Decky's own confirmation and checks a SHA-256. See ADR-0002 and assumptions A11 to A17.
2. **Decky contacts its store server on install** when a version string other than `dev` is passed (threat model T18). Needs your view in slice 2.
3. **Template build tasks replaced** by Python scripts, because they need bash, rsync and Docker (ADR-0003).

## Test results

Local (Windows, Python 3.14.3):

- pytest: 94 passed, 4 skipped (the skips need a real Linux `/proc`, signals, symlinks or file modes and run in CI).
- ruff check, ruff format, mypy strict: clean.
- ESLint, `tsc --noEmit`, Rollup build: clean.
- `check_versions.py`: consistent. `package.py`: zip built.

Mutation checks (your testing standard): ten guards were broken one at a time and the guarding test failed each time: PID reuse check, fail-closed persistence, in-memory fallback, self and ancestor exclusion, UID filter, sibling-prefix path check, create-only store write, home-path redaction, resume on cancellation, library index. The cancellation test was tightened after its first mutation run showed a timing gap.

CI: see the pull request checks.

## Known gaps

- Nothing has run on a device yet. Python version, `sqlite3`, `aiohttp`, TLS defaults and all Steam payloads are unverified until you run the checklist below.
- ADR-0001 and ADR-0002 are drafts until the exports come back.
- `LocalFolderStore` relies on hard links, which exFAT SD cards lack (A29).
- Discovery only covers what the Diagnostics page needs; slice 3 completes it.
- The build prompt kept in `docs/build-prompt.md` names your device models and two real compatdata IDs. You asked for it to be committed as written; say if you would rather redact those lines.

## On-device checklist

Do this on **both** devices. Use any one Steam game and any one non-Steam shortcut that lives in its own Proton prefix.

1. Install the build from the pull request: download the `plugin-zip` artifact from the CI run (or run `pnpm run build` then `pnpm run deploy:device` with `deploy.local.json`), then in Decky, Settings, Developer, "Install Plugin from ZIP File", or deploy over SSH.
2. Confirm Keepsake appears in the Quick Access Menu and shows "Device:".
3. Open Keepsake, Settings, set a device name, Save. Reload plugins (Decky, Settings, General, or restart Decky). Confirm the name survived.
4. Diagnostics: press **Environment**, **Steam shortcuts**, **Frontend facts** and **Test HTTPS**. Check nothing shows an error.
5. Launch the **Steam game**. While it runs, open Keepsake, Diagnostics, press **Game processes**, then **Freeze test**, confirm. The game should pause for about 5 seconds and resume. Note anything odd (audio, controller, display). Quit the game.
6. Repeat step 5 with the **non-Steam shortcut**.
7. Suspend the device and wake it.
8. Press **Export diagnostics**. Note the file path it shows.
9. Copy the export off the device (`scp deck@<address>:homebrew/settings/Keepsake/diagnostics-*.json .`) or open it locally, and send me the relevant facts. Use generic names for games if you paste anything into the repository.
10. Open Logs and confirm entries are listed, including `freeze.stopped` and `freeze.resumed`.

What I need back from each device to finish ADR-0001 and ADR-0002:

- Decky version, Python version, whether `sqlite3`, `aiohttp` and `certifi` are available, and the HTTPS test result.
- For the shortcut: `appidSigned`, `appidUnsigned`, `compatdataFound` (you can replace IDs with "matches" or "does not match").
- The `app-lifetime` and `game-action-start` probe events for both games (`unAppID`, `appId`, `appIdType`).
- `processes` match reasons for both games, and the freeze test outcome.
- Whether `suspend-request` and `resume-from-suspend` events appear.
- `frontend.decky` facts (`deckyBackendCall`, `deckyPluginLoaderMethods`).
