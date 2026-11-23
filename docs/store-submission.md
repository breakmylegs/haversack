# Decky Plugin Store: readiness and submission

Keepsake installs today from its own signed GitHub releases. This page lists what the Decky Plugin Store asks for, how Keepsake meets each point, and the steps for Peter to submit (ADR-0050). The GitHub install URL stays either way.

Sources: the Decky wiki's "Submitting plugins" and "Review and testing" pages (wiki.deckbrew.xyz), and the decky-plugin-template README, read 18 November 2026.

## Requirements and where Keepsake stands

| Requirement | Keepsake |
|---|---|
| A licence file in the repository root (`LICENSE` or `LICENSE.md`) | `LICENSE`: BSD-3-Clause at the top |
| If built from the template, the template's licence kept at the bottom of `LICENSE` | Kept |
| Licences that must travel with the code are included in the zip | `LICENSE` and `THIRD_PARTY_NOTICES.md` are in the zip, and the vendored libraries' licences are in `py_modules/keepsake/_vendor/LICENSES` |
| pnpm 9, so the store's CI builds it | `packageManager` is pnpm 9.15.9 |
| `plugin.json` with name, author, flags and `publish` (tags, description, image) | Present. `flags` is empty: no root (P8) |
| Backend binaries built from source by the store's CI (`backend/src` to `backend/out`) | None needed: the backend is Python (`main.py`, `py_modules`) and nothing is compiled (P9). `bin/keepsake-gate` is a short shell script, the optional launch wrapper |
| Code review by the Decky team | The code is public, with a threat model and ADRs |

## Differences to explain in the pull request

- **Updates:**
  - store installs update through the store;
  - GitHub installs update through Keepsake's own Updates page, which checks Keepsake's release signature (ADR-0036).
  - Both routes hand the install to Decky's own installer (ADR-0002).
- **Network use:** this is listed in [the privacy page](user/privacy.md). Nothing goes to a Keepsake server; there is none.

## Steps for Peter (needs your GitHub account)

1. Fork `SteamDeckHomebrew/decky-plugin-database` on GitHub.
2. In your fork, add Keepsake as a submodule under `plugins/`, pinned to the commit of the release you want listed:
   ```
   git clone https://github.com/<you>/decky-plugin-database
   cd decky-plugin-database
   git submodule add https://github.com/breakmylegs/haversack plugins/Keepsake
   cd plugins/Keepsake
   git checkout v<version>
   cd ../..
   git commit -am "Add Keepsake v<version>"
   git push
   ```
3. Open a pull request to `SteamDeckHomebrew/decky-plugin-database`, filling in its template. Link `docs/user/README.md`, `docs/threat-model.md` and `SECURITY.md`.
4. Answer the reviewers. I can prepare replies and any changes they ask for.
