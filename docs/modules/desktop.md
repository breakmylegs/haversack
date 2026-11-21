# Module: Desktop

Desktop Mode web interface and tray icon covering every module.

| | |
|---|---|
| Flag default | On (ADR-0068) |
| Spec | `docs/build-prompt-v2.md` sections 4 (P7), 6.2 to 6.4 and 8.4 |
| ADRs | 0012, 0014, 0017, 0018, 0068 |
| Code | `py_modules/keepsake/desktop/` (entries, tray, D-Bus client), `desktop/` (the page, ADR-0040), served by the plugin with `keepsake.host` |
| Slices | 23 (Desktop I), 24 (Desktop II), at the end of the feature queue |

## What it does

- First verifies that the Decky backend keeps running in Desktop Mode. If it does not, stop and escalate.
- Loopback HTTP server inside the backend on `127.0.0.1` only, port configurable and outside the avoid list.
- One-time login URL from the tray, exchanged for a session cookie. `Host` header validation against the loopback address. CSRF token on every state-changing request. No CORS.
- Feature parity: Saves (status, conflicts, history, restore, pin, settings, sign-in), Advisor, Replication (peers, pairing, send, queue, pause, resume, policies), Installer (source selection and preparation), Settings, Modules, Updates, Logs and Diagnostics.
- Steam operations created here stay pending until Gaming Mode, shown clearly.
- Tray: StatusNotifierItem over Keepsake's own pure-Python D-Bus client (ADR-0068), started minimised at login. Menu: status line (with the number of conflicts), Open Keepsake, Quit. One tray per user; the app menu brings up the running one. Notifications for conflicts, completed transfers and updates are later work.

## What it writes (spec section 6.3)

`~/.config/autostart/keepsake-tray.desktop` and `~/.local/share/applications/keepsake.desktop`, only while the module is on, rewritten for each new version. Removed when disabled and in `_uninstall`. The icon is the plugin's own; no other file is written.

## Network

`127.0.0.1` loopback HTTP, only while the module is on.

## Health checks

Server listening, tray entry present when on and absent when off (T52), session count.
