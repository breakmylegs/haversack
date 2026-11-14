# Releasing Keepsake

There is no CI (ADR-0004) and `main` only accepts pull requests (ADR-0005), so a release is two local steps. You need `gh` signed in, Python, pnpm and SSH access to a device.

## Once: a signing key (recommended)

Releases can be signed with [minisign](https://jedisct1.github.io/minisign/). Without a key, releases still carry `SHA256SUMS`, but the signature is the control that protects against a compromised GitHub account (threat model T10).

1. Install minisign (for example `winget install jedisct1.minisign` or `scoop install minisign`).
2. Generate a key pair outside the repository: `minisign -G -p keepsake.pub -s %USERPROFILE%\.minisign\keepsake.key`.
3. Keep the secret key and its password safe and offline. Never commit it; `.gitignore` blocks `*.minisign.key` and `minisign.key` as a backstop.
4. Set `KEEPSAKE_MINISIGN_KEY` to the secret key path in your shell before publishing.
5. Send me the public key (`keepsake.pub`); it will be pinned in the plugin when in-plugin verification is built.

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

   This runs `pnpm run check`, builds `Keepsake-v0.2.1.zip` deterministically, writes `SHA256SUMS`, signs it when `KEEPSAKE_MINISIGN_KEY` is set, creates and pushes the tag `v0.2.1`, and creates the GitHub Release with the zip, `SHA256SUMS`, the signature and the changelog notes.

Use `pnpm release publish --dry-run` to build the assets into `out/release/` without tagging or publishing.

## Pre-releases

Use a version like `0.3.0-beta.1`. It is published as a GitHub pre-release and only offered to devices on the Pre-release channel.

## Mistakes

Tags `v*` cannot be moved or deleted (ADR-0005). If a release is wrong, publish a new patch version. A broken GitHub Release can be edited or deleted on GitHub, but its tag stays.

## Rebuilding a release to check it

The zip has sorted entries, fixed timestamps and fixed modes, and `.gitattributes` forces LF line endings, so the same tag built with the same Node, pnpm lockfile and Python (zlib) versions gives the same bytes. Check out the tag, run `pnpm install --frozen-lockfile`, `pnpm run build` and `python scripts/package.py`, and compare the printed SHA-256 with `SHA256SUMS`. If they differ, compare the zip contents (`python -m zipfile -l`) before drawing conclusions: a different zlib version changes compressed bytes without changing any file.
