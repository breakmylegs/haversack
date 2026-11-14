# ADR-0002: Update hand-off to Decky's installer

- Status: **draft**, waiting for slice 1 on-device results and slice 2 testing
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

Keepsake must update itself from its own menus without the Decky store or Desktop Mode, by handing the install to Decky Loader's own installer (build prompt section 12). A self-updating root backend is not allowed.

## What the source shows (Decky Loader v3.3.1)

See `docs/assumptions.md` A11 to A17.

- Decky's Developer page "Install plugin from URL" calls the websocket route `utilities/install_plugin(url, name)` with version `dev`.
- That route only **requests** an install: Decky shows its own confirmation prompt and installs on confirm.
- Passing a SHA-256 in `hash` makes Decky refuse a zip that does not match.
- The 3.3.0 "plugin update API" is a store-side update check, not a plugin-facing install route. The build prompt's second option does not exist as described.
- `window.DeckyBackend` is a global, so a plugin frontend can call `utilities/install_plugin` directly. This is not in the typed `@decky/api` surface, so it could change without notice.

## Options

- A. Call `window.DeckyBackend.call("utilities/install_plugin", zipUrl, "Keepsake", version, sha256, InstallType.UPDATE)`. Decky shows "Update Keepsake to vX.Y.Z", verifies the hash and reloads the plugin. Side effect: with a real version string Decky POSTs an install-count increment to the Decky store server (threat model T18).
- B. Same call with version `dev`. No store POST, and Decky reads the name from `plugin.json`, but the confirmation shows "dev" instead of the version.
- C. Fallback when `window.DeckyBackend` is missing: show the release zip URL as text and a QR code with short "Install plugin from URL" instructions.

## Results

| Check | Legion Go 2 | Legion Go |
|---|---|---|
| Decky version | | |
| `window.DeckyBackend.call` visible to the plugin | | |
| `DeckyPluginLoader` install methods visible | | |

## Decision

Pending. Provisional: A with C as fallback, subject to Peter's view on the store install-count POST (A) versus a less clear confirmation prompt (B). Slice 2 tests the chosen route on both devices, including rollback.

## Consequences

To be written with the decision.
