# R27: Keepsake becomes Haversack (v0.51.0)

## What changed

**The name** is Haversack (ADR-0089, research in `docs/research/rename.md`).

**The update from Keepsake:**
- **Release assets.** Every release also publishes `Keepsake-v<version>.zip`, `Keepsake.zip` and `Keepsake-desktop-v<version>.zip`: the same bytes, all in the signed `SHA256SUMS`. Every Keepsake updater, v0.25.0's included, finds its usual asset, and Decky installs Haversack beside Keepsake.
- **Held, then moved.** `py_modules/keepsake/rename.py` and `main.py`:
  - Haversack starts nothing while `plugins/Keepsake/plugin.json` exists.
  - Once Keepsake is removed, it copies `settings/Keepsake` and `data/Keepsake` without overwriting, keeping file modes and checking every file by SHA-256. It needs room plus 64 MB, records the move, then starts.
  - A failed copy is not recorded, and Haversack stays held until it succeeds.
  - After a way back to Keepsake and forward again, Haversack's folders are set aside (never deleted) and Keepsake's newer data moves in.
- **The quick menu card.** `src/pages/RenameCard.tsx` and `src/rename.ts` show "Keepsake is now called Haversack" with **Remove the old Keepsake**. After a confirmation, it removes Keepsake and Keepsake Helper through Decky's `utilities/uninstall_plugin`, then finishes the move. The frontend's background services start only once the backend has started.
- **The updater.** Haversack's updater offers only releases with a Haversack zip.

**The renaming:**
- **Strings and names.** Every user-visible string in Gaming Mode, the desktop app, the tray, Desktop Mode entries, sign-in pages, Device checks and messages. Also the plugin and helper names (`haversack-helper`), the release asset names, the release title, the tag and signature comment, and the SBOM.
- **What stays Keepsake:** the cloud folder (`Apps/Keepsake`), the OAuth registrations, the Python package, internal identifiers, and the PC package's internal folder and install folders (ADR-0089 section 4). The sign-in screens explain that Microsoft and Google show the registered name, Keepsake.

**The logo and icons:** a satchel on teal, in `assets/logo.svg` and `assets/logo.png`, plus the tray icon.

**Research:** `docs/research/decky-plugins.md`, the catalogue of 128 store plugins with feature verdicts, for R29.

**Docs:**
- ADR-0089;
- T162;
- A241 to A244;
- `CLAUDE.md` fixed names;
- CHANGELOG ("nothing is lost");
- device run step 50;
- README heading and install link.

## Tests

**New:**
- `tests/test_rename.py`: 12 tests, plus one POSIX-only test for file modes;
- `test_keepsake_releases_are_never_offered_to_haversack` in `tests/test_update.py`;
- the old-name assets and their sums lines in `tests/test_release.py`.

**Updated** for the new names and wording: the tests of the touched files, 31 files, all passing (600 tests).

**Out of date before this branch:** `tests/test_app_cloud.py` expected the sign-in event without its `method` field. That field was added in an earlier release, and the expectation is now corrected.

**Mutation testing** (`tmp/mutate.py`): 26 mutants of `rename.py`, the updater, the release assets and the PC package folder. All are killed except one. A copy that drops file modes survives on Windows; the POSIX test `test_owner_only_files_stay_owner_only` kills it on the device.

**Checks:** `tsc` (Gaming Mode and desktop) and eslint on the changed files pass. The gate result is in the pull request.

## Known gaps

- Reinstalling an old Keepsake while Haversack runs makes both run until the next Decky restart, when Haversack holds again. The way back says to remove Haversack first.
- Decky's install prompt still says "Keepsake" (it shows the name the updater passes).
- The repository is renamed after the release, then checked through GitHub's redirect.
- Peter's manual name checks: the UK IPO (classes 9 and 42), domains, and plugins.deckbrew.xyz.

## On-device checklist

Device run step 50 (`docs/device-run.md`):
- the hold;
- **Not now**;
- the removal and the move (games, sign-in and History all intact, with no new sign-in);
- only Haversack left in Decky's list;
- Haversack Helper installed from Device;
- the optional way back and forward again.

Also run `pnpm run test:device tests/test_rename.py` for the file-mode test.
