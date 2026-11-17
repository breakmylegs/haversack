# Keepsake on a PC (preview)

The PC host runs Keepsake's core without Decky, on Windows or Linux (ADR-0038). It is a preview: the desktop interface (P3), the process watcher (P4) and the signed PC package with self-update (P5) come next. Until then, it is for development and for trying the save layout on a real PC.

## Install it from a release

1. Install Python 3.11 or newer. On Windows: `winget install Python.Python.3.13`. On Linux, the system `python3` is enough.
2. Download `Keepsake-desktop-v<version>.zip` from the latest release on GitHub, and unzip it anywhere.
3. Double-click `install.pyw`, or run `python install.pyw` in that folder. Keepsake is copied into your own program folder, set to start when you sign in, and opened in your browser.

Later, open Keepsake by running `keepsake.pyw` in `%LOCALAPPDATA%\Keepsake\app` (Windows) or from your app menu (Linux).

- **Remove Keepsake:** run `python install.pyw --uninstall`. Your settings and saves are kept.
- **Install without starting at sign-in:** add `--no-autostart`.

The zip is listed in the release's signed `SHA256SUMS`.

## Run it from a clone

You need Python 3.11 or newer. On Windows, install it with `winget install Python.Python.3.13`; on Linux, use the system `python3`.

Windows (PowerShell, in the repository folder):

```
$env:PYTHONPATH = "py_modules"; python -m keepsake.host --open
```

Linux:

```
PYTHONPATH=py_modules python3 -m keepsake.host --open
```

`--open` opens the desktop interface in your browser, using a one-time link that carries the access token. Stop the host with Ctrl+C.

Build the desktop interface first, once and after every change, with `npx -y pnpm@9.15.9 run build:desktop`. Without it, the page only says Keepsake is running.

## Where it keeps things

| | Windows | Linux |
|---|---|---|
| Settings | `%APPDATA%\Keepsake\settings` | `$XDG_CONFIG_HOME/keepsake/settings` (usually `~/.config/keepsake/settings`) |
| State | `%LOCALAPPDATA%\Keepsake\runtime` | `$XDG_STATE_HOME/keepsake/runtime` (usually `~/.local/state/keepsake/runtime`) |
| Logs | `%LOCALAPPDATA%\Keepsake\logs` | `$XDG_STATE_HOME/keepsake/logs` |

## Safety

The page and its API answer only on `127.0.0.1`. They refuse other web pages, renamed hosts and other machines, and every call needs a token that only the launcher knows (ADR-0039).

What differs from a handheld:
- The Installer is not available, because it needs Decky to create Steam shortcuts.
- Advisor starts switched off. Its advice is built for handhelds.
