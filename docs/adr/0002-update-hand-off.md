# ADR-0002: Update hand-off to Decky's installer

- Status: **accepted, pending on-device confirmation** (decided in slice 2 under the owner's delegation, 14 November 2026)
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

Keepsake must update itself from its own menus without the Decky store or Desktop Mode, by handing the install to Decky Loader's own installer (build prompt section 12). A self-updating root backend is not allowed.

## What the source shows (Decky Loader v3.3.1)

See `docs/assumptions.md` A11 to A17a.

- Decky's Developer page "Install plugin from URL" calls the websocket route `utilities/install_plugin(url, name)` with version `dev`.
- That route only **requests** an install: Decky shows its own confirmation prompt and installs on confirm.
- Passing a SHA-256 in `hash` makes Decky refuse a zip that does not match.
- The 3.3.0 "plugin update API" is a store-side update check, not a plugin-facing install route. The build prompt's second option does not exist as described.
- `window.DeckyBackend` is a global, so a plugin frontend can call `utilities/install_plugin` directly. This is not in the typed `@decky/api` surface, so it could change without notice.
- An update uninstalls the old version first (calling `_unload` and `_uninstall`) and deletes only the plugin folder.

## Options

- A. `install_plugin(zipUrl, "Keepsake", "X.Y.Z", sha256, installType)`. Decky's prompt shows the version, but Decky also POSTs an install-count increment to the Decky store server, an endpoint outside Keepsake's allowlist (threat model T18).
- B. The same call with version `dev`. No store POST; Decky reads the name from `plugin.json`. Decky's prompt shows "dev" instead of the version, but Keepsake's own Updates page has already shown the version and release notes, and the hash pins the exact zip.
- C. Fallback when `window.DeckyBackend.call` is missing: show the release zip URL as text and a QR code with "Install plugin from URL" instructions.

## Decision

**B, with C as the fallback.**

- The backend (`keepsake.update.Updater.prepare`) refuses while a sync job or session is active, requires a complete release (zip named `Keepsake-v<version>.zip` and `SHA256SUMS`), checks both URLs against the network allowlist, downloads `SHA256SUMS` and takes the zip's hash from it.
- The frontend (`src/update.ts`) passes `(artifact, "Keepsake", "dev", sha256, installType)` to `utilities/install_plugin`, with install type `UPDATE`, `DOWNGRADE` (rollback) or `REINSTALL`. Decky shows its confirmation, downloads the zip, checks the hash and reloads the plugin.
- If the route is missing, the Updates page shows the URL and a QR code.

Not yet done (build prompt "Should"): verifying a minisign signature over `SHA256SUMS` inside the plugin. Release signing exists in `scripts/release.py`; in-plugin verification is planned for slice 12 hardening unless brought forward.

## Results

To be confirmed on device in slice 2.

| Check | Legion Go 2 | Legion Go |
|---|---|---|
| Decky version | | |
| `window.DeckyBackend.call` visible to the plugin | | |
| Decky confirmation shown, update installs, toast "Updated to v0.2.1" | | |
| Rollback to v0.2.0 works the same way | | |
| Update refused during "Simulate sync job" | | |

## Consequences

- Decky's confirmation prompt names the version "dev". The Updates page explains what is being installed before the prompt appears.
- Keepsake depends on an untyped Decky route. A Decky change that removes it degrades to the QR fallback rather than breaking.
