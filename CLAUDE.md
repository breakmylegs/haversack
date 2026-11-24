# Haversack (formerly Keepsake)

Decky Loader plugin that installs non-Steam games on SteamOS and Bazzite handhelds (from ISO, folders and network locations) and moves them between the user's own handhelds on request, operated entirely from Gaming Mode.

**The strip (v0.61.0, ADR-0098).** Only Core, Installer and Replication remain. Save sync, Advisor, Desktop, the PC host, Device, Looks and the root helper were deleted; the `full` branch keeps v0.60.0 with all of them. Replication copies a game's saves on its first send and leaves every manifest-listed save and config file out of later updates. Where this file or the build prompts describe removed features, ADR-0098 wins; their principles stay for the `full` branch and any later save plugin.

This file holds the objective, principles, escalation rules and conventions from sections 1 to 6 of the build prompt. The full detail (architecture, canonical model, sync model, lifecycle, auth, updates, UX, slices) is in [docs/build-prompt.md](docs/build-prompt.md). Read the relevant section there before working on a slice.

**v2 (slice C0).** Keepsake becomes one plugin with five modules: Saves (v1 save sync), Advisor, Replication, Installer and Desktop. [docs/build-prompt-v2.md](docs/build-prompt-v2.md) extends the v1 prompt: it is authoritative for everything after v1 slice 12 and amends the remaining v1 slices (its section 10). Where v1 and v2 conflict, v2 wins (ADR-0014). Module documents are in [docs/modules/](docs/modules/), the full queue in [docs/plan.md](docs/plan.md), the replication research (partly superseded, see spec section 11) in [docs/research/replication-research.md](docs/research/replication-research.md).

## Fixed names

- Plugin name **Haversack** (renamed from Keepsake in v0.51.0, ADR-0089). It is the plugin folder, the settings folder and, once renamed after v0.51.0, the repository name. The cloud data folder (OneDrive `Apps/Keepsake`), the OAuth registrations' names, the Python package `keepsake` and internal identifiers keep the Keepsake name (ADR-0089). Do not rename either set again.
- Repository: `breakmylegs/haversack` (public). Commits use the GitHub noreply identity configured in the local git config.

## 1. Objective

Outcomes:
- A Windows game installs from an ISO, a folder or a network location into its own shortcut and Proton prefix, with no Desktop Mode step.
- A non-Steam game set up on one handheld appears on the other on request, playable, even though shortcut app IDs and compatdata folders differ on each device.
- Saves travel with a game's first send, and no later update ever replaces a save or settings file.
- The plugin updates itself from its own menus in a few clicks.
- Source lives in the owner's public GitHub repository. Releases are built locally by `pnpm release` and published with `gh` (ADR-0004: no GitHub Actions).
- A sent game keeps its compatibility tool, artwork and launch options.

## 2. Context

- Two handhelds running SteamOS, user `deck`: a Legion Go (2560x1600 144 Hz IPS, Z1 Extreme) and a Legion Go 2 (1920x1200 144 Hz OLED with VRR, Z2 Extreme), both with two USB4 ports and Wi-Fi 6E (v2 section 3). Bazzite must stay supported, including `/var/home` symlinked to `/home` and usernames other than `deck`.
- SD card labels differ between devices. The two devices have different screens.
- Many non-Steam games are installed from ISO into the shortcut's own Proton prefix, so the game folder usually sits inside the prefix.
- Non-Steam shortcut app IDs, and therefore `compatdata/<appid>` folders, differ per device. Ludusavi, rclone plugins, decky-ludusavi and Spool all fail this case or need manual redirects.
- Save sync is outside this plugin since the strip (ADR-0098); the Ludusavi cutover in build prompt section 19 applies to the `full` branch only.
- Design basis: snapshot DAG with canonical logical roots, native cloud APIs, device code sign-in, pull before launch and push after exit.

## 3. Non-negotiable principles

1. **Never silently overwrite.** Whenever local and cloud have both changed, the user resolves a conflict.
2. **Snapshots are immutable.** Cloud objects are written once and never modified. Only retention deletes, within the protection rules in build prompt section 9.
3. **Every restore is reversible.** A local pre-restore snapshot is taken and verified before any local save file is replaced or removed.
4. **Hashes decide, timestamps inform.** Decisions about save data use content hashes and parent links. Timestamps are displayed but never pick a winner, except under the opt-in "Take the newest" setting and its clock guard (ADR-0080).
5. **Fail closed.** If discovery, resolution, hashing, auth or network is uncertain, do nothing destructive, tell the user and keep the game playable.
6. **Never write saves under a running game.** Restores happen only before launch, while the game is frozen, or after exit.
7. **Gaming Mode first** (amended in v2, ADR-0014). Every feature is fully operable from Gaming Mode with the controller alone. Desktop Mode surfaces are additional and never required. No feature may need a terminal or a separately installed app.
8. **No root.** The backend runs as the user. `plugin.json` carries no root flag.
9. **No bundled binaries** (amended in v2, ADR-0018). Python stdlib first, vendored pure-Python libraries second. System binaries already on SteamOS and Bazzite only if listed in the System Binary Register, verified on both and handled when missing. Never bundle, download or install a binary.
10. **Canonical paths.** Cloud data, Replication manifests and peer messages never contain absolute device paths, device usernames, compatdata IDs or SD card labels.
11. **A frozen game is always released.** A watchdog resumes any process the plugin pauses, whatever errors occur.
12. **Nothing personal in the public repository.** No tokens, account names, device names, real save files or the owner's game list. Test fixtures are synthetic. Use synthetic app IDs in tests, never the real ones quoted in the build prompt.

v2 principles (summary; full text in build prompt v2 section 4):

13. **Module isolation.** Modules depend on Core, never on each other's internals. Each has its own flag, settings, health checks, state tables and job queue. A failing module disables itself without affecting the others (ADR-0012).
14. **Saves owns save data.** Only Saves writes save files after initial replication. Every Saves-resolved path and every manifest path tagged `save` is off-limits to the other modules.
15. **Steam writes through the Steam client only.** Shortcut, launch option, compatibility tool and artwork changes go through `SteamClient` from the frontend, only after an explicit user action, originals stored first, every field read back. Never write `shortcuts.vdf`, `config.vdf` or `localconfig.vdf` (ADR-0015).
16. **Advisor is read-only.** It displays recommendations and can copy text. Any "apply" capability is an escalation item (ADR-0019).
17. **LAN exposure is opt-in.** The Replication listener is off by default and serves only paired peers over authenticated encryption. Only discovery and a rate-limited, time-boxed pairing handshake are unauthenticated (ADR-0016).
18. **AI is opt-in and minimal.** User-supplied key and per-provider opt-in. Requests carry only game title, hardware profile, tool versions and the settings discussed (ADR-0019).
19. **One lock per game.** A per-`gameKey` lock spans all modules. No module writes game files, prefixes or saves while another holds it or the game runs.

## 4. Escalation rules

**Standing delegation (ADR-0037, 17 November 2026).** For every item below, decide what is best for the app yourself and record it in an ADR with your reasoning and sources, then carry on. Stop only for what you genuinely cannot do:
- physical device runs;
- signing in to the owner's accounts;
- anything needing the owner's credentials;
- anything this laptop's security policy blocks.

When you stop, give exact step-by-step commands for the owner to run and report back on.

The items that each need a recorded decision (formerly "stop and ask"):

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

v2 additions (build prompt v2 section 5, ADR-0014):

- Enabling the Replication listener by default, or binding it beyond the selected LAN interfaces.
- Changing the Replication manifest format or peer protocol after slice 18 merges.
- Any Steam write outside principle 15, or any direct VDF write.
- Any Advisor capability that writes anything.
- Adding a system binary to the register, or relying on one that failed verification.
- Adding a network endpoint outside build prompt v2 section 6.2, or sending AI providers more than principle 18 allows.
- Any write outside the amended write allowlist (build prompt v2 section 6.3), or any Replication write against a path Saves manages.
- Network share mounting that needs root or a bundled binary.
- Porting any code from the owner's `decky-plugins` repository before the licence audit (ADR-0013; the audit document is on the `full` branch) is signed off. That repository and the v2 input folder are read-only: never modify them.
- Copying code from CapyDeploy (AGPL-3.0) or any GPL project.

## 5. Working conventions

- **One slice at a time** in the order of [docs/plan.md](docs/plan.md), each on its own branch. Merge to `main` by pull request only, once the gate and the change's tests pass (ADR-0037). The on-device checks go in the report for the owner's next device run.
- **End of slice:** open a pull request, write `docs/slices/NN-report.md`, merge, and continue with the next item that does not need a device (ADR-0037).
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

**Network allowlist** (in use since the strip, ADR-0098)
- `raw.githubusercontent.com` (Ludusavi manifest)
- `api.github.com` and GitHub release asset downloads (update checks)
- Only while their module and feature are on: LAN peer port (default TCP 47110) and mDNS for Replication; `www.steamgriddb.com` with the user's key, and its image host `cdn2.steamgriddb.com` (ADR-0027; never sent the key); user-entered Installer network locations, only the typed host after a user action, on the terms in ADR-0033. Avoid ports 8080, 8384, 27040 and 1714 to 1764
- The cloud, Advisor, AI and loopback endpoints approved earlier (ADR-0008, build prompt v2 section 6.2) are no longer used; they stay approved for the `full` branch only. Using any of them again here is an escalation item.

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
python scripts/vendor.py                # rebuild py_modules/keepsake/_vendor from pinned wheels (ADR-0034)
python scripts/deploy.py                # install the build on the device
python scripts/release.py prepare X.Y.Z # version bump pull request (see docs/releasing.md)
python scripts/release.py publish --device-tested   # on main after merge; --dry-run to test
```
