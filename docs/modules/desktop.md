# Module: Desktop

Desktop Mode web interface and tray icon covering every module.

| | |
|---|---|
| Flag default | Off |
| Spec | `docs/build-prompt-v2.md` sections 4 (P7), 6.2 to 6.4 and 8.4 |
| ADRs | 0012, 0014, 0017, 0018 |
| Code (planned) | `py_modules/keepsake/desktop/`, `desktop/` (own SPA build), tray script run by system `python3` |
| Slices | 23 (Desktop I), 24 (Desktop II), at the end of the feature queue |

## What it does

- First verifies that the Decky backend keeps running in Desktop Mode. If it does not, stop and escalate.
- Loopback HTTP server inside the backend on `127.0.0.1` only, port configurable and outside the avoid list.
- One-time login URL from the tray, exchanged for a session cookie. `Host` header validation against the loopback address. CSRF token on every state-changing request. No CORS.
- Feature parity: Saves (status, conflicts, history, restore, pin, settings, sign-in), Advisor, Replication (peers, pairing, send, queue, pause, resume, policies), Installer (source selection and preparation), Settings, Modules, Updates, Logs and Diagnostics.
- Steam operations created here stay pending until Gaming Mode, shown clearly.
- Tray: StatusNotifierItem over D-Bus with a vendored pure-Python D-Bus library (candidate `jeepney`, to verify). Menu: Open Keepsake, Sync now, Pause or resume Replication, status line, conflicts count, Quit tray. Notifications for conflicts, completed transfers and updates.

## What it writes (spec section 6.3)

`~/.config/autostart/keepsake-tray.desktop` and `~/.local/share/applications/keepsake.desktop`, only while the module is on. Removed when disabled and in `_uninstall`.

## Network

`127.0.0.1` loopback HTTP, only while the module is on.

## Health checks

Server listening, tray entry present when on and absent when off (T52), session count.
