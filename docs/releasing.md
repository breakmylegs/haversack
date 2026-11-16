# Releasing Keepsake

There is no CI (ADR-0004) and `main` only accepts pull requests (ADR-0005), so a release is two local steps. You need `gh` signed in, Python, pnpm and SSH access to a device.

## Once: a signing key (recommended)

Releases can be signed with [minisign](https://jedisct1.github.io/minisign/). Without a key, releases still carry `SHA256SUMS`, but the signature is the control that protects against a compromised GitHub account (threat model T10).

1. Install minisign (for example `winget install jedisct1.minisign` or `scoop install minisign`).
2. Generate a key pair outside the repository: `minisign -G -p keepsake.pub -s %USERPROFILE%\.minisign\keepsake.key`.
3. Keep the secret key and its password safe and offline. Never commit it; `.gitignore` blocks `*.minisign.key` and `minisign.key` as a backstop.
4. Set `KEEPSAKE_MINISIGN_KEY` to the secret key path in your shell before publishing.
5. Pin the public key in the plugin: copy the base64 line from `keepsake.pub` (the line after the comment) into `PUBLIC_KEY` in `py_modules/keepsake/release_key.py` and merge that change through a pull request. From the next release, the updater refuses any update without a valid `SHA256SUMS.minisig` made with this key (ADR-0023), so publish that release with `KEEPSAKE_MINISIGN_KEY` set. The public key is not secret; the secret key never leaves your machine.

## Each release

1. Add a section to `CHANGELOG.md` for the new version, for example `## [0.2.1]`, with the notes. It becomes the release notes.
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

   This runs `pnpm run check`, builds `Keepsake-v0.2.1.zip` deterministically, copies it byte for byte to `Keepsake.zip`, writes `SHA256SUMS` with a line for each name, signs it when `KEEPSAKE_MINISIGN_KEY` is set, creates and pushes the tag `v0.2.1`, and creates the GitHub Release with both zips, `SHA256SUMS`, the signature and the changelog notes.

## Release assets and the install URL

| Asset | Used by |
|---|---|
| `Keepsake-v<version>.zip` | The in-plugin updater and the rebuild check below |
| `Keepsake.zip` | First install: `https://github.com/breakmylegs/keepsake/releases/latest/download/Keepsake.zip` |
| `SHA256SUMS` | Both zips, one line each, so one signature covers both names |

First install on a new device: Decky, Settings, Developer, Install Plugin from URL, then paste the URL above. After that, updates come through Keepsake's Updates page.

GitHub's `/releases/latest/` redirect skips drafts and pre-releases, so that URL always gives the newest stable release. Do not rename or drop either zip: the updater only looks for the versioned name, and the install URL only works while every stable release has `Keepsake.zip`.

Use `pnpm release publish --dry-run` to build the assets into `out/release/` without tagging or publishing.

If you choose to publish without running the device tests, use `pnpm release publish --accept-untested` instead of `--device-tested`. The release notes then state that the device tests were not run.

## Pre-releases

Use a version like `0.3.0-beta.1`. It is published as a GitHub pre-release and only offered to devices on the Pre-release channel.

## Mistakes

Tags `v*` cannot be moved or deleted (ADR-0005). If a release is wrong, publish a new patch version. A broken GitHub Release can be edited or deleted on GitHub, but its tag stays.

## Rebuilding a release to check it

The zip has sorted entries, fixed timestamps and fixed modes, and `.gitattributes` forces LF line endings, so the same tag built with the same Node, pnpm lockfile and Python (zlib) versions gives the same bytes. Check out the tag, run `pnpm install --frozen-lockfile`, `pnpm run build` and `python scripts/package.py`, and compare the printed SHA-256 with `SHA256SUMS`. If they differ, compare the zip contents (`python -m zipfile -l`) before drawing conclusions: a different zlib version changes compressed bytes without changing any file.
