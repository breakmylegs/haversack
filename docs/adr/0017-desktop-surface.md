# ADR-0017: Desktop surface

- Status: proposed (slice C0); the default and the tray are amended by ADR-0068: Desktop is on by default, and the tray uses Keepsake's own D-Bus client instead of jeepney
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 4 (P7), 6.2 to 6.4, 8.4 and 12 (slices 23 and 24); research section 6.1

## Context

Peter asked for a Desktop Mode interface and tray covering every feature, scheduled at the end of the build queue. Decky's UI exists only in Gaming Mode and Big Picture, and `@decky/ui` components cannot render outside Steam. A browser page served from the plugin backend is the only route that keeps P8 (no root) and P9 (no bundled binaries).

## Decision

1. **Verify first.** Slice 23 starts by checking that the Decky backend keeps running in Desktop Mode on SteamOS and Bazzite. If it does not, stop and escalate, because the alternative is a separate service.
2. **Loopback only.** An HTTP server inside the backend, bound to `127.0.0.1` only, on a configurable port outside the avoid list (ADR-0016). Off unless the Desktop module is on (default off).
3. **Authentication.** The tray issues a one-time, short-lived login URL that is exchanged for a session cookie. Every request's `Host` header must be the loopback address and port (blocks DNS rebinding). Every state-changing request needs a CSRF token. No CORS headers.
4. **Feature parity.** Saves, Advisor, Replication, Installer, Settings, Modules, Updates, Logs and Diagnostics. Steps that need the Steam client queue in the Steam Operations Executor (ADR-0015) and show as pending until Gaming Mode.
5. **Separate SPA.** `desktop/` with its own build and component set. It shares only TypeScript types and the API client with the Decky frontend.
6. **Tray.** A StatusNotifierItem over D-Bus using a vendored pure-Python D-Bus library (candidate `jeepney`, licence and purity to verify in slice 24), run by system `python3` in the desktop session (ADR-0018). Started by `~/.config/autostart/keepsake-tray.desktop`, which the plugin writes when Desktop is enabled and removes when it is disabled and in `_uninstall`. A health check reports a tray entry left behind. The tray talks to the backend only through the authenticated loopback API.
7. **Notifications** through `org.freedesktop.Notifications` for conflicts, completed transfers and available updates.

## Consequences

- Two new write allowlist entries (the autostart and application desktop files) and one new network surface (loopback HTTP), each conditional on the module.
- Threats T47, T48 and T52 cover the loopback UI, login token leakage and a tray left after uninstall.
- Desktop work stays at the end of the queue (slices 23 and 24), before only the v2 hardening release.
