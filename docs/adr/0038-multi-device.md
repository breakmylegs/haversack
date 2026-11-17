# ADR-0038: Multi-device architecture: handhelds, Linux PCs and Windows PCs

- Status: accepted (Peter's owner decision of 17 November 2026 to support PCs and laptops; the architecture is mine under ADR-0037)
- Date: 17 November 2026
- Deciders: Peter (owner)
- Amends: P9 wording for the PC package (below), the plan for slices 16 to 25

## Context

Keepsake must work on:
- handhelds running Decky (SteamOS, Bazzite and other Linux handhelds);
- laptops and desktop PCs running Linux, with or without Decky;
- Windows PCs.

P7 (Gaming Mode first) stays for handhelds. On PCs a normal desktop UI is fine. Non-Decky machines get signed GitHub release assets only, with the same update and signature checks.

The facts this decision rests on, read from the code on 17 November 2026:
- **The backend does not depend on Decky.** Everything lives in `py_modules/keepsake`, with `KeepsakeApp(paths, emit=...)` at the centre. Only the thin `main.py` imports `decky`.
- **The cloud store is already device-neutral (P10).** Snapshots record files under logical roots taken from the Ludusavi manifest: `winAppData`, `winLocalAppData`, `winLocalAppDataLow`, `winDocuments`, `winSavedGames`, `base`, `home`, `xdgData`, `xdgConfig`, `steamUserdata` and `registry` (`resolve.py`). Only `logical_roots()` turns them into folders, and today it knows two layouts: a Proton prefix (`drive_c/users/steamuser/...`) and native Linux. A native Windows layout is a third mapping, not a new data model.
- **Steam's own files** (`libraryfolders.vdf`, `appmanifest_*.acf`, `shortcuts.vdf`, `userdata/<id>`) have the same format on Windows. Only their locations differ.
- **`SteamClient`**, the only route P15 allows for Steam writes, exists only inside Steam's own CEF, which Decky reaches. A machine without Decky has no permitted way to add shortcuts, set launch options or apply artwork. P15 forbids writing the VDF files directly.

## Options for machines without Decky

| Option | What it is | For | Against |
|---|---|---|---|
| A | The planned Desktop Mode surface (slices 23 and 24) only | Already planned | Needs Decky, so no Windows and no Linux PC without Decky |
| B | A separate desktop app with its own code | Native look | Two code bases; breaks "one core" |
| **C** | **The same Python core run headless on the PC as a user service, serving the slice 23 desktop web UI on loopback** | **One core, one UI, one protocol; handhelds in Desktop Mode use the same UI** | **The desktop UI must not use `@decky/ui`; lifecycle hooks differ per platform** |

## Decision: option C, one core and three hosts

1. **Hosts.** The same `keepsake` package runs under one of three hosts, chosen at start and reported as `host`:
   - `decky`: today's plugin. The frontend is the Decky UI, controller-first (P7). Desktop Mode adds the loopback desktop UI (slice 23).
   - `linux-desktop`: a Linux PC or laptop without Decky. `python3 -m keepsake.host` runs as a systemd user service (or an XDG autostart entry) and serves the desktop UI on `127.0.0.1`.
   - `windows`: the same host on Windows, started from the user's Startup folder. It serves the same desktop UI.
2. **The desktop UI** is the slice 23 single-page app: plain React with no `@decky/ui`, talking to the host over the loopback API. It authenticates with a per-session token and is protected against DNS rebinding and CSRF (the slice 23 acceptance). The same UI serves handhelds in Desktop Mode and PCs, so there is one UI to keep in parity.
3. **Save sync on every host.**
   - **Windows layout:** `logical_roots()` gains a third layout, `windows`:
     - `winAppData`, `winLocalAppData`, `winLocalAppDataLow`, `winDocuments` and `winSavedGames` map to the user's Windows known folders, read with `SHGetKnownFolderPath` through `ctypes`. Documents may be redirected to OneDrive, so `%USERPROFILE%\Documents` is never assumed.
     - `<osUserName>` is the real user name.
     - `registry` is the real `HKEY_CURRENT_USER`, through the stdlib `winreg`. On Proton it is the prefix's `user.reg`.
   - **Native Linux PCs** use the existing native layout.
   - **Steam discovery** finds the Steam root per platform:
     - on Windows, `HKCU\Software\Valve\Steam\SteamPath`, then `libraryfolders.vdf`;
     - on Linux, the existing search.
   - **Proton to native Windows** needs no translation step. A snapshot taken in a Proton prefix under `winAppData/Game/Save` restores on Windows into `%APPDATA%\Game\Save`, and the reverse, because both are the logical root `winAppData`. Matching games across devices (ADR-0011) is already device-neutral.
   - **Lifecycle on PCs** has no Decky hooks, so:
     - **push after exit:** a process watcher (`/proc` on Linux; `EnumProcesses` and `QueryFullProcessImageNameW` through `ctypes` on Windows) sees the game exit, and Keepsake pushes;
     - **pull before play:** a "Sync now" action and an idle pass while no game runs;
     - **the opt-in launch wrapper:** Steam launch options are set by the user on PCs, as P15 requires.
   - **Never silently overwrite (P1):** every pull still goes through conflict detection, so a missed launch never overwrites a save.
   - **P6 on Windows:** saves are written only while the game is not running (checked by the watcher). The freeze and thaw path (P11) stays Linux-only until a Windows suspend is built and tested. Until then the Windows host never freezes.
4. **Device identity.**
   - **The device record** in the cloud registry gains an optional `platform` field (`decky-linux`, `linux`, `windows`) and an optional `formFactor` (`handheld`, `laptop`, `desktop`). Both are optional and older devices ignore them, so this is backward compatible and not a schema change under the slice 6 rule.
   - **The Ludusavi `when.os` filter** follows the layout: Proton and Windows apply Windows paths, native Linux applies Linux paths.
5. **Replication (slices 16 to 20).**
   - **Where it works:** between Decky devices as planned.
   - **To Linux PCs and Windows,** the peer protocol and manifests stay platform-neutral (canonical paths, P10). Translation happens at the receiving end:
     - **Proton to Windows:**
       - the game folder inside the prefix (`drive_c/...`) becomes a folder in the user's chosen library;
       - registry entries the game needs come from `user.reg` into the real `HKCU` (a write outside the old allowlist, decided in the Replication I ADR when built);
       - the exe path is mapped across.
     - **Windows to Proton:** the reverse, into a new prefix.
     - **Shortcuts** on machines without Decky cannot be created (P15: no `SteamClient`, no VDF writes). The receiving desktop UI shows "Add this game to Steam: Games, Add a Non-Steam Game, then choose `<exe>`", with the exe path to copy. Saves adoption works once the shortcut exists.
6. **Advisor.**
   - **On handhelds** it works as built (device profiles for handhelds).
   - **On PCs and laptops** the module is off by default and hidden from the desktop UI's main menu. Its advice is built on handheld power and screen profiles, which do not fit a desktop.
   - **Gaming laptops** can be added later as profiles in `data/devices.json`, with DMI facts on Linux and `GetSystemFirmwareTable` SMBIOS reads on Windows, all stdlib.
7. **Installer.**
   - **Decky hosts only.** It needs `SteamClient` for the installer shortcut and retargeting (P15), and udisks for ISOs.
   - **Windows** runs installers natively, so there is nothing for Keepsake to add.
   - **Linux PCs without Decky** have no permitted way to create the shortcut.
   - **Otherwise** the module reports itself unavailable, with that reason.
8. **Distribution and updates for PCs.**
   - **The package:** each release adds `Keepsake-desktop-v<version>.zip`, a pure-Python package of the same `keepsake` code, the desktop UI build and a launcher. It is listed in the signed `SHA256SUMS`, so it has the same signature check (ADR-0036).
   - **Python:**
     - Linux PCs use the system `python3` (3.11 or newer).
     - Windows needs Python 3.11 or newer from python.org or `winget install Python.Python.3.13`. That is a one-time step on a PC, which is acceptable there (P7 applies to handhelds).
     - P9 stays as written: no bundled interpreter. Shipping the signed CPython embeddable distribution later would be its own ADR.
   - **Updates** cannot hand off to Decky's installer (ADR-0002), because there is none. The desktop host updates itself:
     1. download the versioned zip;
     2. verify `SHA256SUMS` and its minisign signature with the same `Updater` code;
     3. unpack into a new versioned folder;
     4. switch the launcher to it, keeping the previous folder for rollback.
   - **Settings and state** live in the platform's own place: `%APPDATA%\Keepsake` on Windows and `$XDG_CONFIG_HOME/keepsake` on Linux. That is the PC write allowlist (an amendment to build prompt v2 section 6.3, recorded here).

## What this means for the plan

Slices 16 to 25 are re-planned in `docs/plan.md`. Work that needs no device moves forward and is built first:

1. **P1, Platform layer:** host detection, Windows known folders, the `windows` layout in `logical_roots()`, `winreg` for the registry root, and Steam discovery on Windows.
2. **P2, Headless host:** `keepsake.host` runs `KeepsakeApp` without Decky, with platform paths and the loopback API (slice 23's server, moved forward).
3. **P3, Desktop UI:** slice 23's single-page app, served by the host.
4. **P4, PC lifecycle:** the process watcher and push after exit.
5. **P5, PC package and self-update:** the desktop zip, signed, and self-update.

Replication (16 to 20) still waits for the slice 16 device measurements. Its PC endpoint translation is added to slices 19 and 20.

## Consequences

- One code base for every device. Most of the PC work is testable on this Windows laptop without a handheld.
- PCs get save sync first, then Replication as its slices land. Advisor and Installer stay where they help.
- Peter needs a PC run for the Windows host's real Steam library and games (steps in each report).
