# ADR-0089: Keepsake becomes Haversack

- Status: accepted (R27; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

**The request.** Peter asked for a new name, chosen after a thorough search, avoiding Carryover, SideQuest and Tandem. He also asked for:
- settings and data moved across, with a way back;
- existing installs updated through the Updates page, ending as one plugin;
- the repository renamed with redirects, and v0.25.0's updater checked;
- tray and app entries, OAuth app names, signing names, docs, and release notes that say nothing is lost;
- a new full-colour logo and icons.

**`CLAUDE.md` conflicts.** It fixes "Keepsake" as the plugin, settings folder, OneDrive app folder and repository name ("Do not rename it"). Peter's later request overrides it. This ADR records the override, and `CLAUDE.md` is updated.

**Facts from Decky's source** (`SteamDeckHomebrew/decky-loader` main at a1bb3f74d3, 22 November 2026, `backend/decky_loader/browser.py` and `utilities.py`):

1. **Folders follow the zip.** A plugin's folder is its zip's top folder. Settings, data and logs are `<homebrew>/{settings,data,logs}/<plugin folder>`.
2. **Installs passed as `dev`.** For such an install (every Keepsake updater since v0.25.0 passes `dev`), `_install` first sets `isInstalled` from the name it was given ("Keepsake"). Then it reads the real name from the zip's `plugin.json`.
3. **What a "Haversack" zip does to an installed Keepsake:**
   - `isInstalled` is true;
   - the uninstall step looks for "Haversack", finds no folder, and its assertion is swallowed, so Keepsake stays installed;
   - Haversack is unzipped into its own folder and loaded;
   - because `isInstalled` was true, Haversack is not added to `pluginOrder`. The quick menu sorts plugins missing from `pluginOrder` first (`PluginView.tsx`, index -1), so Haversack is shown at the top.
4. **Uninstalling a plugin.** `utilities/uninstall_plugin(name)` is a frontend websocket route. It:
   - unloads the plugin's frontend;
   - stops its backend with `uninstall=True`, which runs its `_uninstall`;
   - removes it from Decky's lists;
   - deletes only its code folder.

   The settings, data and log folders stay.

## Decision

### 1. The name is Haversack

A haversack is a traveller's carry-bag, so games, saves and kit go with you between your handhelds.

- **Why it is clear in this field.** It was checked against the Decky plugin database, PyPI, npm, AUR, Flathub, Steam, GitHub, the app stores and web trademark search (`docs/research/rename.md`). The only trademark is for logistics software, and the other uses are in freight. Nothing is in gaming, Linux or Decky.
- **Runners-up:** Packhorse and Wanderkit.
- **Checks this laptop cannot make:** the UK IPO register (classes 9 and 42), domain lookups and plugins.deckbrew.xyz (blocked here). They are listed for Peter as a recommended confirmation, not a gate.

### 2. One update for existing installs, and never two syncing at once

**The release assets.** From v0.51.0, each release publishes:
- `Haversack-v<version>.zip` and `Haversack.zip`;
- `Haversack-desktop-v<version>.zip` and `Haversack-helper-v<version>.zip`;
- the same bytes again as `Keepsake-v<version>.zip`, `Keepsake.zip` and `Keepsake-desktop-v<version>.zip`.

Every name is listed in the signed `SHA256SUMS`, so every Keepsake updater finds its usual asset and verifies it. That includes v0.25.0's updater and the PC package's self-update.

**The update.** Decky installs Haversack beside Keepsake (fact 3).

**Held while Keepsake is installed.** While `plugins/Keepsake/plugin.json` exists, Haversack's backend starts nothing:
- no sync, lifecycle, listener or tray;
- its frontend starts no background services;
- its quick menu shows one card: "Keepsake is now called Haversack".

Keepsake keeps working meanwhile. The card's button asks for confirmation, then removes Keepsake (and Keepsake Helper, if installed) through `utilities/uninstall_plugin` (fact 4).

**Copied once Keepsake is gone.** Haversack then copies `settings/Keepsake` and `data/Keepsake` into its own folders, so nothing changes under the copy.
- Nothing already in Haversack's folders is overwritten.
- File modes are kept, so sign-in tokens stay owner-only.
- Every file is checked by SHA-256 against the original.
- There must be room for the copy plus 64 MB. Otherwise nothing is copied and the card says why.
- Only after every file checks out does Haversack record the move (`moved-from-keepsake.json`) and start.

A failed copy is not recorded and is tried again. Logs are not copied.

**The way back.** The originals are never changed (only a `moved-to-haversack.json` note is added beside them). To go back, remove Haversack and install an old Keepsake from the releases page, which finds everything as it was.

**Forward again.** If any of Keepsake's files changed after the move was recorded, the user went back to Keepsake and then updated again. Haversack then:
- renames its own folders aside (`Haversack.before-<time>`, never deleted);
- moves Keepsake's newer data in whole, with the same checks, and only when there is room;
- records the move again.

Modification times only detect that Keepsake was used again. They pick no winner between save versions (P4): both copies are kept.

**The helper.** The helper becomes "Haversack Helper" (folder `haversack-helper`). The old helper is removed with Keepsake, and the new one is installed from Device, Reconnect help, as before.
- Its socket path `/run/keepsake-helper` is an internal name and stays.
- The two helpers never run together, because the old one is removed before the new one can be installed.

**Older releases.** Haversack's updater only offers releases that carry a Haversack zip. Installing a Keepsake release from Haversack would add a second plugin beside it.

### 3. What changes name

- The plugin name and folder, the helper, and the SBOM component.
- Every user-visible string: Gaming Mode, toasts, the desktop app, the tray, Desktop Mode entries, sign-in pages, Device checks and messages.
- The release asset names, the release title, the tag message and the signature comment.
- The logo (`assets/logo.svg` and `assets/logo.png`) and the tray icon. They were drawn for this project (a satchel on teal, one geometry written as SVG and as a supersampled PNG) and are BSD-3-Clause with the rest of the repository. No third-party artwork is used.
- The README and docs (R28 rewrites them in full).

### 4. What keeps the Keepsake name, and why

- **The cloud data folder.** The OneDrive app folder (`Apps/Keepsake`), the Google Drive app data and the WebDAV or S3 prefix stay as they are. Changing them would change the cloud layout (an ADR-0014 escalation) and could cut devices off from their snapshots.
- **The OAuth app registrations' display names stay "Keepsake".** OneDrive's app folder is named from the registration, and renaming it is not proven safe for existing folders. Fail closed (P5): keep it. The sign-in screens explain that Microsoft and Google show the registered name, Keepsake. No step for Peter.
- **Internal identifiers.** None of these are visible, and renaming them adds risk without benefit:
  - the Python package `py_modules/keepsake`;
  - `keepsake_*` events and setting keys;
  - the `X-Keepsake-Token` header and the helper's socket folder;
  - the desktop entry file names (`keepsake.desktop`, whose `Name=` is now Haversack);
  - the tray icon file name and the registry fragment marker;
  - the HTTP `Server` and `User-Agent` values.
- **The PC package's internals.** The folder inside the package (`Keepsake-desktop/`) and the install folders (`%LOCALAPPDATA%\Keepsake`, `%APPDATA%\Keepsake`, and the Run value) stay. Installed PCs check the folder before updating, and moving the install folders would strand settings.
- **The release signing key** (ADR-0036). Changing it is an escalation and gains nothing.

### 5. The repository

The repository is renamed `breakmylegs/haversack` after v0.51.0 is published and verified. GitHub redirects the old API and download addresses.
- **After the rename:** the v0.25.0 updater check and the stable install link are run through the redirect. Then the release script, update URLs and docs move to the new name in the next release.
- **If the redirect check fails,** the rename is undone (`gh repo rename keepsake`), and a later ADR decides.

## Consequences

- **For existing users:** one extra prompt (Decky's install prompt, which still says Keepsake) and one confirmation to remove Keepsake. Nothing is lost: the data is copied and checked, and the originals kept.
- **The cloud folder and the sign-in screens still say Keepsake,** and the screens explain why.
- **Known gap:** reinstalling an old Keepsake while Haversack runs makes both run until the next Decky restart, when Haversack holds again. The way-back instructions say to remove Haversack first.
- **Threat model:** T162.
- **Device run:** step 50.
