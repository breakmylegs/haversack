# R17 report: the Desktop Mode taskbar freeze (v0.30.1)

Peter's report of 21 November 2026, on the Legion Go after the release that added the tray. In Desktop Mode, plasmashell (taskbar and start menu) stopped responding while KWin and Konsole kept working. `sudo systemctl stop plugin_loader` restored it at once. New on that device: EmuDeck 2.7.1 with its Emulation folder and a Steam library on an external USB disk behind a dock, which logged "device offline" errors.

## Root cause

- **The tray blocked Plasma.** Plasma calls a StatusNotifierItem synchronously (properties, GetLayout, AboutToShow) and waits for each answer. The tray answered on one thread, and that same thread made a synchronous HTTP call to the plugin, with a timeout of up to 3 seconds:
  - on `AboutToShow`;
  - every 30 seconds.

  While the plugin was slow, each call held plasmashell. Stopping plugin_loader made the HTTP call fail at once, which unblocked the tray, matching the symptom.
- **A second path.** Clicking the icon opened the window from another thread, which held the tray's lock while it waited on the shared D-Bus socket, the socket the D-Bus thread also reads.
- **Why the plugin was slow.** Its status was served through the event loop, and game scans and identity probes touch library and save folders. A disk that is slow, spinning up or offline can hold such a call in the kernel, and with it the loop or the shared thread pool.

## The fix

- **Tray (`desktop/tray.py`):**
  - every D-Bus call is answered at once from cached state;
  - one refresher thread checks the plugin (1-second limit, at most one check at a time); `AboutToShow`, clicks and the instance socket only ask it to;
  - the window opens over a separate, short-lived D-Bus connection, so one thread alone reads the main socket;
  - LayoutUpdated and NewToolTip go out only on a change, at most every 2 seconds, and the first change goes out at once.
- **Plugin:**
  - `status_now()` is from memory, and the desktop page answers `get_status` with it without touching the event loop;
  - game discovery runs on dedicated low-priority disk threads (per-thread nice 10), one scan at a time, and after 20 seconds the last list is used, with `scanSlow` in the status;
  - identity probing (roots and folder checks) moved off the event loop onto the disk threads;
  - save scans already never follow symlinked folders and record links that leave the root; this is now covered by a test with a loop.
- **Device check:** `tray-responsive`, "Desktop tray responsive", times the tray's D-Bus reply and the page's `get_status` and fails above 200 ms.
- **Perf gate:** "1,000 get_status calls during a scan", with a scan held on a disk thread and the event loop stopped.

## Not done, and why

- **I/O priority:** an idle I/O class needs `ioprio_set`, which the standard library does not offer; per-thread CPU niceness is set.
- **A thread held in the kernel by an offline disk** cannot be interrupted from Python. It is left behind on its own disk thread, and nothing waits on it.

## Tests

- `tests/test_responsive.py`, 13 tests (plus 1 POSIX-only):
  - every D-Bus method answers within 100 ms while the plugin hangs for 30 seconds, with one check in flight;
  - a refused plugin is reported and Open greyed out; answers never call the plugin;
  - signals only on change, at most every 2 seconds; a click opens the window from the refresher;
  - `get_status` from the page with the event loop stopped;
  - a scan held by a slow disk uses the last list, with `get_status` staying fast and one scan at a time;
  - a manifest vanishing mid-scan; a symlink loop and links leaving the save root (POSIX);
  - the device check.
- `tests/test_desktop.py`: updated for the refresher, fake portals (no real browser), and the portal's own connection.
- **Regression:** `test_host.py`, `test_devicechecks.py`, `test_discovery.py`, `test_discovery_games.py`, `test_identity.py`, `test_app.py`, `test_app_ux.py`, `test_lifecycle.py`, `test_remote_copies.py`.
- **Mutation:** 13 mutants of the tray's non-blocking rules, signal limits, timeout, the page's fast path and the scan bounds. All are killed after two sharper tests were added.

## On-device checklist

- `docs/device-run.md` part 4 step 9.
