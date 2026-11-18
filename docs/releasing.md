# Releasing Keepsake

There is no CI (ADR-0004) and `main` only accepts pull requests (ADR-0005), so a release is two local steps. You need `gh` signed in, Python, pnpm and SSH access to a device.

## Once: the signing key (ADR-0036)

Releases are signed with [minisign](https://jedisct1.github.io/minisign/). The signature over `SHA256SUMS` is the control that protects devices against a compromised GitHub account (threat model T10).

The key is encrypted with a long random passphrase. The passphrase is sealed with Windows DPAPI for your account, so releases sign without anyone typing it. Both files live in `%LOCALAPPDATA%\Keepsake\signing`, a folder only your account can open.

1. Install minisign: `winget install --id jedisct1.minisign --exact --scope user`.
2. Create the key: `python scripts/signing.py setup`. It prints the public key, which is not secret. This laptop's security policy blocks Claude from handling key files, so you run this step.
3. Back it up (next section) before the key is pinned.
4. Pin the public key: its base64 line goes into `PUBLIC_KEY` in `py_modules/keepsake/release_key.py`, merged by pull request. From the release that carries it, devices refuse any update without a valid `SHA256SUMS.minisig` from this key. `release.py` refuses to publish unsigned once the key is pinned.

`python scripts/signing.py status` shows the public key, checks the folder is private and signs a test file with the plugin's own verifier, without showing anything secret.

### Back up the signing key

A pinned key that is lost locks every installed device out of in-place updates. The only way back is a reinstall from the first-install URL, so keep two offline copies, in two places.

1. Plug in a USB stick that you keep offline, and run `python scripts/signing.py backup E:\keepsake-signing`, using your stick's drive letter. This copies the encrypted secret key and the public key. The encrypted key is useless without the passphrase.
2. Run `python scripts/signing.py show-passphrase`, type `SHOW`, and write the passphrase on paper, or store it in your password manager. Keep it apart from the USB stick. Close the window afterwards.
3. Eject the stick and store it offline. Optionally, repeat on a second stick kept elsewhere.

### Restore it on another laptop

1. Install minisign (step 1 above).
2. Run `python scripts/signing.py restore E:\keepsake-signing` and type the passphrase when asked. It re-seals the passphrase for this laptop's account, locks the folder and runs a signing check.
3. Run `python scripts/signing.py status`. The public key must match `release_key.py`.

## Once: the Google sign-in secrets (ADR-0055)

The built-in Google clients' secrets ship in the release packages but are never committed. They live in the git-ignored file `py_modules/keepsake/client_secrets.json`, and `publish` refuses to run without it. To recreate it on another laptop:

1. Sign in to https://console.cloud.google.com with the Keepsake Google account, and open the `Keepsake` project.
2. Open **Google Auth Platform**, then **Clients**. For each client, open it and copy its secret. If the secret is no longer shown, use **Add secret**.
3. Create the file with exactly these two names:
   ```json
   {
     "googleClientSecret": "<secret of the TVs and Limited Input client>",
     "googleDesktopClientSecret": "<secret of the Desktop app client>"
   }
   ```
4. Run `git status`. The file must not be listed.

## Each release

1. Add a section to `CHANGELOG.md` for the new version, for example `## [0.2.1]`, with the notes. It becomes the release notes.
   - **User guide (ADR-0046).** Regenerate the screenshots and check the guide. Commit any changed images and pages in the same pull request as the changelog:
     ```
     npx -y pnpm@9.15.9 run build:desktop
     python scripts/docs_screenshots.py
     python scripts/check_docs.py
     ```
   - **Page updates.** Update the pages in `docs/user/` for anything the release changes for users.
2. On an up-to-date `main` with a clean tree:

   ```
   pnpm release prepare 0.2.1
   ```

   This bumps `package.json` on `release/v0.2.1`, pushes it and opens a pull request. Merge it on GitHub.

3. Back on `main`, pull, then run the device tests on that commit:

   ```
   git switch main && git pull
   pnpm run test:device
   ```

4. Publish:

   ```
   pnpm release publish --device-tested
   ```

   This runs `pnpm run check`, builds `Keepsake-v0.2.1.zip` deterministically, copies it byte for byte to `Keepsake.zip`, writes `SHA256SUMS` with a line for each name, signs it with the laptop's key (checked with the plugin's own verifier against the pinned key), creates and pushes the tag `v0.2.1`, and creates the GitHub Release with both zips, `SHA256SUMS`, the signature and the changelog notes.

## Release assets and the install URL

| Asset | Used by |
|---|---|
| `Keepsake-v<version>.zip` | The in-plugin updater and the rebuild check below |
| `Keepsake.zip` | First install: `https://github.com/breakmylegs/keepsake/releases/latest/download/Keepsake.zip` |
| `Keepsake-desktop-v<version>.zip` | The PC package for Windows and Linux PCs (ADR-0042) |
| `Keepsake-v<version>.sbom.cdx.json` | The software bill of materials: every shipped third-party component (ADR-0050) |
| `SHA256SUMS` | Every asset above, one line each, so one signature covers them all |

First install on a new device: Decky, Settings, Developer, Install Plugin from URL, then paste the URL above. After that, updates come through Keepsake's Updates page.

GitHub's `/releases/latest/` redirect skips drafts and pre-releases, so that URL always gives the newest stable release. Do not rename or drop either zip: the updater only looks for the versioned name, and the install URL only works while every stable release has `Keepsake.zip`.

Use `pnpm release publish --dry-run` to build the assets into `out/release/` without tagging or publishing.

If you choose to publish without running the device tests, use `pnpm release publish --accept-untested` instead of `--device-tested`. The release notes then state that the device tests were not run.

## The ProtonDB index (monthly, separate from plugin releases)

Advisor's optional ProtonDB source reads the `protondb-index.json.gz` asset of the rolling release `protondb-index` (ADR-0035). Refresh it after ProtonDB publishes a new monthly dump (usually on the 1st or 2nd):

1. Find the newest dump: `gh api repos/bdefore/protondb-data/contents/reports --jq ".[].name"`.
2. Download it into its own empty folder, for example `tmp/pdb-dl/reports_nov1_2026.tar.gz` (about 70 MB). Keep the file name; the build reads the dump name from it.
3. Build: `python -I scripts/protondb_index.py build tmp/pdb-dl/reports_nov1_2026.tar.gz --out tmp/pdb-out`. It refuses a cut-off dump and an index over 30 MB.
4. Publish: `python scripts/protondb_index.py publish tmp/pdb-out/protondb-index.json.gz`. It replaces the asset in the same release, keeps the ODbL notes, and never marks the release latest, so the install URL above keeps serving the plugin.
5. Delete the download and the build folder.

The `protondb-index` tag is not a `v*` tag. The updater ignores it, and `v*` tag protection does not apply (ADR-0005).

## Pre-releases

Use a version like `0.3.0-beta.1`. It is published as a GitHub pre-release and only offered to devices on the Pre-release channel.

## Mistakes

Tags `v*` cannot be moved or deleted (ADR-0005). If a release is wrong, publish a new patch version. A broken GitHub Release can be edited or deleted on GitHub, but its tag stays.

## Rebuilding a release to check it

The zip has sorted entries, fixed timestamps and fixed modes, and `.gitattributes` forces LF line endings, so the same tag built with the same Node, pnpm lockfile and Python (zlib) versions gives the same bytes. Check out the tag, run `pnpm install --frozen-lockfile`, `pnpm run build` and `python scripts/package.py`, and compare the printed SHA-256 with `SHA256SUMS`. If they differ, compare the zip contents (`python -m zipfile -l`) before drawing conclusions: a different zlib version changes compressed bytes without changing any file.

The software bill of materials can be rebuilt from the same tag with `python scripts/sbom.py`. It has no timestamp, so it matches the release asset byte for byte.

## Signing key: rotation and compromise

Devices trust exactly one release key, the one built into `py_modules/keepsake/release_key.py` (ADR-0036). Any change of key reaches devices only through a release signed with the key they already trust.

**Planned rotation** (for example, a new laptop):

1. Create the new key with `python scripts/signing.py setup` on the laptop that will sign from now on, and back it up as above.
2. In one pull request, put the new public key in `release_key.py` and note the change in the changelog.
3. Release that version signed with the **old** key. Devices accept it, and from then on they trust only the new key.
4. Sign every later release with the new key. Keep the old key's offline backup until every device has updated, then destroy it.

**Lost key** (no backup works):

1. Devices refuse anything not signed with the lost key, so they cannot be moved to a new key by an update.
2. Create a new key, put its public key in `release_key.py`, and release.
3. Tell users plainly, in the release notes and the README, to install that release by hand from the first-install URL. Decky's own installer does not check Keepsake's signature. From then on, updates work again.

**Exposed key** (someone else may have it):

1. Stop releasing with it at once.
2. Create a new key and follow "Lost key", step 2 onwards. A release signed with the exposed key could be forged, so do not rely on step 3 of the planned rotation.
3. Say in a GitHub security advisory which versions were signed with the exposed key, and that releases are only genuine if they come from this repository's Releases page.
4. Check the published releases' `SHA256SUMS` against a fresh rebuild of each tag.
