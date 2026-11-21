# R13 report: the desktop app comes with the plugin, in the tray

Recorded in ADR-0068 (Peter's request of 21 November 2026). Slices 23 and 24 are brought forward.

## What changed

- **Desktop module on Decky:** available on Linux Decky hosts and on by default.
  - While on, the plugin serves the desktop page and API on 127.0.0.1 with `host.Api` and `host.serve`, and writes `host.json` (0600), which is deleted when it stops.
  - It writes the tray's two entries for its own version.
  - Switching it off removes them, and so does `main._uninstall`.
- **`keepsake/desktop/entries.py`:** render, install only when they differ, remove only Keepsake's own files, read, and check.
- **`keepsake/desktop/dbus.py`:** a pure-Python session D-Bus client and object server.
- **`keepsake/desktop/tray.py`:** a StatusNotifierItem and dbusmenu with a status line, Open Keepsake and Quit.
  - The window opens through the portal, else `webbrowser`.
  - One tray per user, through an abstract socket.
  - The status line says plainly when the plugin cannot be reached.
- **Health:** the module reports the page and the entries; Core warns about entries left behind (T52).
- **Device check:** `desktop-app`, "Desktop app ready".
- **Package:** the plugin zip now carries the desktop page and the tray icon.
- **Docs:**
  - ADR-0068; ADR-0017's status amended; `docs/modules/desktop.md`;
  - T127, A208 to A210;
  - the getting-started guide, CHANGELOG, device run part 4 step 6.

## Decisions taken under ADR-0037

- **Own D-Bus client instead of vendoring jeepney.** It is small, has no new dependency to pin, and can be tested on Windows.
- **The window opens through the portal first.** No binary is needed; `webbrowser` is the fallback, as on PCs.
- **The icon stays in the plugin folder** (`IconThemePath` and an absolute `Icon=`), so the write allowlist gains nothing beyond ADR-0017's two entries.

## Tests

- `tests/test_desktop.py`, 37 tests:
  - D-Bus: the wire format round-trip for every type used, alignment, bad signatures, whole messages, the session socket address;
  - entries: written per version and refreshed; quoting, including reserved characters; only Keepsake's own files removed and never overwritten; check findings;
  - tray: status lines, properties, menu, events, Quit, unknown methods, group properties; greyed out when unreachable; refresh signals only on change; portal and fallback opening; registration;
  - module: page up and down with the token removed; switch-off removal; leftovers, and none while on; on by default; Decky's uninstall;
  - the device check.
- `tests/test_scripts.py`: the plugin zip carries the desktop page and icon, and not the PC installer.
- **Regression:** `test_host.py`, `test_modules.py`, `test_devicechecks.py`, `test_hosts.py`.
- **Mutation:** 28 mutants of the entries, the tray, the D-Bus framing, the module and the check. All are killed after three tests were added; two did not apply after reformatting and are covered by the round-trip tests.

## Known gaps

- The tray against a real Plasma session (A209), the portal (A210) and Decky in Desktop Mode (A208) are unverified until the device run.
- Notifications for conflicts and transfers are later work.

## On-device checklist

- `docs/device-run.md` part 4, step 6.
