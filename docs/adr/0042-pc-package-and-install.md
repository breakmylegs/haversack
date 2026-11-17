# ADR-0042: The PC package, install and launcher

- Status: accepted (decided under ADR-0037; P5 of ADR-0038, first part; self-update follows)
- Date: 17 November 2026
- Deciders: Peter (owner)

## Context

ADR-0038 decided that PCs get Keepsake as a signed GitHub release asset, with the same signature checks as the plugin and no administrator rights. ADR-0039 noted that a launcher must not trust a stale `host.json`. The P3 render run proved that need.

## Decision

1. **One more release asset.**
   - **Contents:** `Keepsake-desktop-v<version>.zip` holds:
     - the same `py_modules` (with the vendored libraries);
     - the built desktop interface;
     - `install.pyw`;
     - `VERSION`;
     - the licences;
     - `README-PC.md`.
   - **Build:** `scripts/package.py` builds it deterministically, like the plugin zip.
   - **Signature:** `release.py` lists it in `SHA256SUMS`, so the release's minisign signature covers it (ADR-0036). The plugin updaters only read their own zip's line, so the extra line changes nothing for them.
2. **Install into the user's own folders.** No administrator rights and no binary are needed.
   - **Version folders:** `install.pyw` copies the package into `<app>/<version>`:
     - Windows: `%LOCALAPPDATA%\Keepsake\app`;
     - Linux: `$XDG_DATA_HOME/keepsake/app`.
   - **The switch:** it then writes `current.json` (`version`, `previous`). It keeps the current and previous versions, so an update can switch and roll back, and prunes older ones.
   - **What is left out:** the installer itself, caches and compiled files.
   - **Version names:** a `VERSION` with unexpected characters is refused, so it can never name a path.
3. **Launcher.** `keepsake.pyw`, next to the version folders, reads `current.json`, puts that version's `py_modules` on the path and runs `keepsake.launcher`. The launcher:
   - opens the running host only after the host named in `host.json` answers a token-protected `get_status`;
   - otherwise starts a new host.

   A stopped host's file, or a port now used by another program, never gets the browser or the token. The host also deletes `host.json` when it stops.
4. **Start at sign-in, without shortcut files.**
   - **Windows:** a `HKCU\...\Run` value, `"<pythonw.exe>" "<keepsake.pyw>" --background`. It needs no COM object to create a `.lnk`, and `pythonw` opens no console window.
   - **Linux:** XDG autostart and app-menu `.desktop` files.
   - **Opting out:** `--no-autostart` installs without the start-up entry.
5. **Uninstall.** `python install.pyw --uninstall` removes the program folder and the start-up entries. Settings, state and saves are never touched by installing, updating or uninstalling.
6. **Python.** The package uses the system Python 3.11 or newer, as ADR-0038 decided, so P9 is unchanged.

## Consequences

- A PC install is: download the zip from the release, unzip it, double-click `install.pyw`.
- Smoke-tested on this laptop with its folders in a scratch folder:
  - the built package installed;
  - the installed launcher started the host from the installed copy;
  - the liveness check confirmed it.
- Self-update (P5, second part) will download the next PC package, verify `SHA256SUMS` and its signature, unpack it into a new version folder and switch `current.json`.
