# ADR-0068: The desktop app comes with the plugin and starts in the tray

- Status: accepted (Peter's request of 21 November 2026, decided under ADR-0037). Changes ADR-0017's "only when Desktop is enabled" default to on, and brings slices 23 and 24 forward.
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

ADR-0017 planned a Desktop Mode web interface and tray behind a Desktop module that was off by default, and slices 23 and 24 sat at the end of the queue. The desktop interface already exists for PCs (ADR-0039, ADR-0040): a plain TypeScript page served by `keepsake.host` on 127.0.0.1. Peter wants:
- the desktop app on SteamOS and Bazzite to come with the Decky plugin, with no separate install and no switch;
- it to start minimised to the tray at Desktop login;
- clicking the icon to open it, closing the window to leave the tray running, and Quit to stop it until the next login;
- the app menu to bring up the running one, never a second copy;
- the tray to say plainly when the plugin cannot be reached;
- a Device check.

## Decision

1. **Desktop is on by default** (`modules.DEFAULT_FLAGS`), for new and existing installs: nobody could have switched it before, as it was unavailable. It is available on Decky hosts on Linux. On PCs, `keepsake.host` already serves the page. It can still be switched off in Settings, Modules.
2. **The plugin serves the desktop interface.** While Desktop is on, the Decky backend serves the same page and JSON API as the PC host, with `host.Api` and `host.serve`:
   - on 127.0.0.1 only, port 47120 and the nine after it, with the `Host` and `Origin` checks and a per-run token (ADR-0039);
   - the port and token go in `host.json` in the plugin's runtime folder, mode 0600, which is deleted when the page stops;
   - the plugin package now ships `desktop/index.html`, `desktop/app.css` and `desktop/dist/*.js`. The PC installer stays in the PC package only.
3. **Entries written by the plugin** (`keepsake/desktop/entries.py`), the two write-allowlist entries of ADR-0017:
   - `~/.config/autostart/keepsake-tray.desktop` starts `python3 <plugin>/py_modules/keepsake/desktop/tray.py --runtime <runtime>` at login, hidden from menus;
   - `~/.local/share/applications/keepsake.desktop` is the same command with `--open`, in Games and Utility;
   - the icon is the plugin's own `assets/icons/hicolor/256x256/apps/keepsake-tray.png`, so no icon file is written anywhere else;
   - each file carries `X-Keepsake-Version`. They are rewritten whenever the plugin starts with a different version, so after an update the tray always runs the plugin's own code;
   - they are removed when Desktop is switched off and in Decky's `_uninstall`. Decky also calls `_uninstall` before an update, and the new version writes them again when it starts. Only files carrying the key are touched, so a user's own file of the same name is never overwritten or deleted.
4. **The tray** (`keepsake/desktop/tray.py`), run by the system `python3`, a register entry since ADR-0018:
   - **D-Bus:** a pure-Python session D-Bus client and object server (`keepsake/desktop/dbus.py`): the wire format for every type, SASL EXTERNAL, calls, returns, errors and signals. No library or binary (P9). jeepney (ADR-0017's candidate) was not needed.
   - **Icon:** a StatusNotifierItem with `IconThemePath` pointing at the plugin's icons, registered with `org.kde.StatusNotifierWatcher` (Plasma on SteamOS and Bazzite).
   - **Menu:** `com.canonical.dbusmenu` with a status line, **Open Keepsake** (greyed out when the plugin cannot be reached) and **Quit**. Activating the icon opens the window.
   - **Window:** opened through the desktop portal's `org.freedesktop.portal.OpenURI` over D-Bus, else Python's `webbrowser`, as the PC launcher does (ADR-0042). The link's token is in the URL fragment, which never reaches a server. Closing the browser window leaves the tray running.
   - **One per user:** an abstract Unix socket `keepsake-tray-<uid>`. A second start hands `open` to the running tray and exits.
   - **Backend:** `host.json` is trusted only after a token-protected `get_status` call answers. Otherwise the status line says "Keepsake's plugin cannot be reached from Desktop Mode. Is Decky Loader running?". It is checked every 30 seconds and whenever the menu opens.
5. **Health.** The Desktop module reports its page and both entries (present, for this version). Core health warns about entries left behind while Desktop is off (T52).
6. **Device check "Desktop app ready":**
   - both entries exist, name this version, run this plugin's tray, and have their icon;
   - `python3` is present, and the session bus exists, so run it in Desktop Mode;
   - the page is running.

   The manual step in `docs/device-run.md` covers the tray icon itself.

## Consequences

- The desktop app needs nothing from the user. The tray appears at the next Desktop login after installing or updating.
- The loopback page is now on by default on handhelds. Its protections are unchanged (T47), and the token file is 0600 and removed when the page stops (T48). See T127 for the tray.
- If Decky's backend does not run in Desktop Mode (A208), the tray says so and the rest of Keepsake is unaffected.
- A208 to A210 in `docs/assumptions.md`.
