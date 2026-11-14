# Slice 1 report: skeleton, development loop and on-device diagnostics

- Branch: `slice/01-skeleton`
- Version: 0.1.0
- Date: 14 November 2026

## What changed

**Repository**
- Public repository `breakmylegs/keepsake`, BSD-3-Clause with the template notice, `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `CLAUDE.md` (sections 1 to 6), `docs/build-prompt.md`.
- `.gitignore` covers local settings, tokens, diagnostics exports, `deploy.local.json` and the secret scan denylist.
- No GitHub Actions (your decision, ADR-0004). The first push included a workflow; it was removed in this branch. In its place: `pnpm run check` (`scripts/check.py`) runs ESLint, `tsc`, the Rollup build, version consistency, packaging, ruff, mypy (strict) and the secret scan; `pnpm run test:device` (`scripts/test_on_device.py`) runs the Linux-only tests on a handheld over SSH.
- `scripts/secret_scan.py` with `.githooks/pre-commit` (no third-party scanner, per your standing rule).
- `scripts/package.py` (deterministic Decky zip), `scripts/deploy.py` (SSH deploy), `scripts/check_versions.py`, `scripts/device.py` (shared SSH settings).

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
4. **No CI** (your decision, ADR-0004). Pull request checks become `pnpm run check`, Linux tests run on a device, and slice 2 builds releases locally with `pnpm release` and `gh`. This changes the outcome "CI builds every release" and the T10 mitigation: the minisign signature becomes the main release control.

## Test results

Local (Windows, Python 3.14.3):

- pytest: 97 passed, 4 skipped (every test in the repository is new in this slice). The 4 skips are the `posix`-marked tests; they run on a device with `pnpm run test:device` (checklist step 1).
- `pnpm run check`: all checks passed (ESLint, tsc, build, versions, packaging, ruff, ruff format, mypy, secret scan).

Mutation checks (your testing standard): eleven guards were broken one at a time and the guarding test failed each time: PID reuse check, fail-closed persistence, in-memory fallback, self and ancestor exclusion, UID filter, sibling-prefix path check, create-only store write, home-path redaction, resume on cancellation, library index, device test argument quoting. The cancellation test was tightened after its first mutation run showed a timing gap.

No CI (ADR-0004).

## Known gaps

- The 4 `posix` tests have not run anywhere yet; the device run in checklist step 1 is their first run. Whether the device's `python3` can create the test venv is unverified (A31).
- Nothing has run on a device yet. Python version, `sqlite3`, `aiohttp`, TLS defaults and all Steam payloads are unverified until you run the checklist below.
- ADR-0001 and ADR-0002 are drafts until the exports come back.
- `LocalFolderStore` relies on hard links, which exFAT SD cards lack (A29).
- Discovery only covers what the Diagnostics page needs; slice 3 completes it.
- The build prompt kept in `docs/build-prompt.md` names your device models and two real compatdata IDs. You asked for it to be committed as written; say if you would rather redact those lines.

## On-device checklist

Do this on **both** devices. Use any one Steam game and any one non-Steam shortcut that lives in its own Proton prefix.

0. Enable SSH on the device and create `deploy.local.json` (see `docs/dev-setup.md`).
1. Run `pnpm run test:device` from the repository. Expect 4 passed. Send me the output if anything fails or the venv cannot be created.
2. Install the build: `pnpm run build` then `pnpm run deploy:device`. Alternatively copy `out/Keepsake-v0.1.0.zip` to the device and use Decky, Settings, Developer, "Install Plugin from ZIP File".
3. Confirm Keepsake appears in the Quick Access Menu and shows "Device:".
4. Open Keepsake, Settings, set a device name, Save. Reload plugins (Decky, Settings, General, or restart Decky). Confirm the name survived.
5. Diagnostics: press **Environment**, **Steam shortcuts**, **Frontend facts** and **Test HTTPS**. Check nothing shows an error.
6. Launch the **Steam game**. While it runs, open Keepsake, Diagnostics, press **Game processes**, then **Freeze test**, confirm. The game should pause for about 5 seconds and resume. Note anything odd (audio, controller, display). Quit the game.
7. Repeat step 6 with the **non-Steam shortcut**.
8. Suspend the device and wake it.
9. Press **Export diagnostics**. Note the file path it shows.
10. Copy the export off the device (`scp deck@<address>:homebrew/settings/Keepsake/diagnostics-*.json .`) or open it locally, and send me the relevant facts. Use generic names for games if you paste anything into the repository.
11. Open Logs and confirm entries are listed, including `freeze.stopped` and `freeze.resumed`.

What I need back from each device to finish ADR-0001 and ADR-0002:

- Decky version, Python version, whether `sqlite3`, `aiohttp` and `certifi` are available, and the HTTPS test result.
- For the shortcut: `appidSigned`, `appidUnsigned`, `compatdataFound` (you can replace IDs with "matches" or "does not match").
- The `app-lifetime` and `game-action-start` probe events for both games (`unAppID`, `appId`, `appIdType`).
- `processes` match reasons for both games, and the freeze test outcome.
- Whether `suspend-request` and `resume-from-suspend` events appear.
- `frontend.decky` facts (`deckyBackendCall`, `deckyPluginLoaderMethods`).
