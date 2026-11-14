# Keepsake

Decky Loader plugin that syncs PC game saves between SteamOS and Bazzite handhelds through cloud storage, operated entirely from Gaming Mode.

This file holds the objective, principles, escalation rules and conventions from sections 1 to 6 of the build prompt. The full detail (architecture, canonical model, sync model, lifecycle, auth, updates, UX, slices) is in [docs/build-prompt.md](docs/build-prompt.md). Read the relevant section there before working on a slice.

## Fixed names

- Plugin name **Keepsake**. It is the plugin folder, the settings folder, the OneDrive app folder and the repository name. Do not rename it.
- Repository: `breakmylegs/keepsake` (public). Commits use the GitHub noreply identity configured in the local git config.

## 1. Objective

Outcomes:
- Saves follow the player between devices with no Desktop Mode step at any point, including setup and cloud sign-in.
- Non-Steam shortcuts installed into their own Proton prefixes sync correctly, even though their compatdata IDs differ on each device.
- No save version is ever silently overwritten or lost.
- The plugin updates itself from its own menus in a few clicks.
- Source lives in the owner's public GitHub repository. Releases are built locally by `pnpm release` and published with `gh` (ADR-0004: no GitHub Actions).

## 2. Context

- Two Lenovo Legion Go handhelds running SteamOS, user `deck`. Bazzite must stay supported, including `/var/home` symlinked to `/home` and usernames other than `deck`.
- SD card labels differ between devices. The two devices have different screens.
- Many non-Steam games are installed from ISO into the shortcut's own Proton prefix, so the game folder usually sits inside the prefix.
- Non-Steam shortcut app IDs, and therefore `compatdata/<appid>` folders, differ per device. Ludusavi, rclone plugins, decky-ludusavi and Spool all fail this case or need manual redirects.
- An interim Ludusavi plus rclone setup to OneDrive must coexist with Keepsake during cutover, then be replaced (build prompt section 19).
- Design basis: snapshot DAG with canonical logical roots, native cloud APIs, device code sign-in, pull before launch and push after exit.

## 3. Non-negotiable principles

1. **Never silently overwrite.** Whenever local and cloud have both changed, the user resolves a conflict.
2. **Snapshots are immutable.** Cloud objects are written once and never modified. Only retention deletes, within the protection rules in build prompt section 9.
3. **Every restore is reversible.** A local pre-restore snapshot is taken and verified before any local save file is replaced or removed.
4. **Hashes decide, timestamps inform.** Decisions about save data use content hashes and parent links. Timestamps are displayed but never pick a winner.
5. **Fail closed.** If discovery, resolution, hashing, auth or network is uncertain, do nothing destructive, tell the user and keep the game playable.
6. **Never write saves under a running game.** Restores happen only before launch, while the game is frozen, or after exit.
7. **Gaming Mode only.** No feature may need Desktop Mode, a terminal or a separately installed app.
8. **No root.** The backend runs as the user. `plugin.json` carries no root flag.
9. **No bundled binaries by default.** Python stdlib first, vendored pure-Python libraries second.
10. **Canonical paths.** Cloud data never contains absolute device paths, device usernames, compatdata IDs or SD card labels.
11. **A frozen game is always released.** A watchdog resumes any process the plugin pauses, whatever errors occur.
12. **Nothing personal in the public repository.** No tokens, account names, device names, real save files or the owner's game list. Test fixtures are synthetic. Use synthetic app IDs in tests, never the real ones quoted in the build prompt.

## 4. Escalation rules

Stop and ask the owner before doing any of the following. Record each decision in an ADR in `docs/adr/`.

- Adding the root flag, a bundled binary or a `remote_binary` entry.
- Loosening any principle above or any safety gate default (build prompt section 9).
- Changing the cloud layout or snapshot schema after slice 6 merges.
- Writing anywhere outside the write allowlist (build prompt section 8).
- Editing `shortcuts.vdf`, launch options or any Steam setting, except the explicit per-game opt-in launch wrapper (build prompt section 10).
- Deleting cloud data outside retention.
- Adding network endpoints beyond the allowlist below.
- Adding OAuth scopes beyond those in build prompt section 11.
- Using code from a GPL project or a project whose licence is unconfirmed.
- Changing repository visibility, branch protection or release signing.
- Installing updates by any route other than the hand-off to Decky's own installer (build prompt section 12).

## 5. Working conventions

- **One slice at a time** from build prompt section 16, each on branch `slice/NN-short-name`. Merge to `main` by pull request only, after the owner confirms the on-device checks.
- **End of slice:** open a pull request, write `docs/slices/NN-report.md`, and stop. Do not start the next slice until the owner confirms.
- **Commits:** conventional commits.
- **Docs every slice:** update `docs/threat-model.md` (new entries, or "no change" with a reason), `docs/assumptions.md`, `CHANGELOG.md`, and add an ADR for any design decision.
- **Slice report** covers what changed, test results, known gaps and the on-device checklist.
- **Language:** UK English in UI strings, docs, comments and commit messages. Never use em dashes or en dashes anywhere.
- **Verify before relying.** When unsure of a Decky or Steam client API, read the decky-loader source, the `@decky/ui` and `@decky/api` type definitions (in `node_modules`) or the template. Record it in `docs/assumptions.md` as verified or unverified. Never guess API names. Where the build prompt conflicts with the source, the source wins: record the difference in `docs/assumptions.md` and tell the owner.
- **Quality bar:** all backend logic has tests. No slice is done with failing tests, type errors, lint errors or a broken build.
- **No GitHub Actions (ADR-0004).** Never add `.github/workflows`. Before every pull request run `pnpm run check` (lint, types, build, versions, packaging, ruff, mypy, secret scan) and record the result. Run `posix`-marked tests on a device with `pnpm run test:device` at the end of every slice and before every release.

### Owner's standing rules (from the owner's global instructions)

- **Testing:** run the new or changed tests plus the existing tests that cover the files and behaviour touched, named one by one, then prove new tests by breaking the code they guard. Do not run whole suites by habit. Run the full suite locally only when asked, or for shared foundations (dependencies, build config, a module nearly everything imports), and say why first.
- **Never use gitleaks** in any form. Secret scanning uses the in-repo script `scripts/secret_scan.py` and the `.githooks/pre-commit` hook.

## 6. Repository, stack and constraints

**Repository**
- Public. GitHub Actions is disabled. `main` is protected (pull request required, applies to admins, no force push) and `v*` tags cannot be moved or deleted (ADR-0005). Changing these is an escalation item.
- Licence BSD-3-Clause with the decky-plugin-template notice kept at the bottom of `LICENSE`. Attribute the Ludusavi manifest (MIT) wherever its data is used.

**Stack**
- decky-plugin-template base, pnpm 9, TypeScript, React, `@decky/ui`, `@decky/api`.
- Python backend: `main.py` is a thin entry point; all logic is in `py_modules/keepsake`. `py_modules/keepsake/app.py` holds the testable core.
- Python: Decky Loader 3.3.1 builds with Python 3.14 (verify on device; see `docs/assumptions.md`). Ruff targets 3.11 syntax; tests run on Windows Python 3.14 and the device's Python.
- Stdlib first (`asyncio`, `sqlite3`, `hashlib`, `hmac`, `zipfile`, `json`, `urllib`, `ssl`), JSON fallback if `sqlite3` is missing. Vendored pure-Python libraries only, pinned with hashes.
- HTTP via stdlib in worker threads unless slice 1 proves `aiohttp` is importable from plugin processes.

**Network allowlist**
- `login.microsoftonline.com`, `graph.microsoft.com`
- `oauth2.googleapis.com`, `www.googleapis.com`
- `raw.githubusercontent.com` (Ludusavi manifest)
- `api.github.com` and GitHub release asset downloads (update checks)
- User-configured WebDAV and S3 endpoints

**Development environment**
- The owner develops on Windows. WSL does not start on this laptop (policy) and Docker is not installed, so backend tests run locally on Windows Python where possible; Linux-only tests are marked `posix`, skipped there, and run on a device over SSH with `pnpm run test:device`. See `docs/dev-setup.md`.
- pnpm is run through `npx -y pnpm@9.15.9` when it is not installed globally.
- Deploy to devices over SSH with `pnpm run deploy:device` (see `docs/dev-setup.md`).

## Commands

```
npx -y pnpm@9.15.9 install --frozen-lockfile
python scripts/check.py                 # full local quality gate, no tests
.venv/Scripts/python -m pytest -q tests/test_x.py   # named tests only
python scripts/test_on_device.py        # posix-marked tests on the device
python scripts/test_on_device.py tests/test_x.py
python scripts/package.py               # zip into out/
python scripts/deploy.py                # install the build on the device
python scripts/release.py prepare X.Y.Z # version bump pull request (see docs/releasing.md)
python scripts/release.py publish --device-tested   # on main after merge; --dry-run to test
```
