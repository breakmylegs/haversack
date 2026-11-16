# Slice 23 report: Desktop I (in progress, step 0)

Branch `slice/23-desktop-1`, stacked on `slice/22-installer-2` (#20). The Desktop surface must cover every module, so it sits on top of the latest one.

## Step 0: verify the backend in Desktop Mode (A79)

The v2 spec (section 8.4, slice 23) says to verify first that the Decky backend keeps running in Desktop Mode. If it does not, slice 23 stops and escalates, because the alternative needs a separate service. Nothing else in this slice is built until the answer is in. The loopback server, sign-in and the desktop app are all wasted work if the backend is not there to serve them.

Added: `scripts/desktop_mode_probe.py`. It is read-only, uses the standard library only and prints no names. It reports:
- whether Decky's `PluginLoader`, `gamescope`, `plasmashell` and `steamwebhelper` are running;
- whether Decky's port 1337 is listening;
- how long ago Keepsake last wrote to its log and data folders.

### Device runbook

On each device (SteamOS, and Bazzite if available):

1. In Gaming Mode, run `ssh deck@<device> python3 - < scripts/desktop_mode_probe.py`. Expect `PluginLoader`, `gamescope` and `deckyListening` to be true.
2. Switch to Desktop Mode, wait two minutes and run it again.
3. Optionally leave it in Desktop Mode past the background sync interval (Settings, default 30 minutes) and run it a third time. A small `keepsakeLogAgeSeconds` then shows that Keepsake's own loop is still running.
4. Paste the outputs below.

### Decision rule

| Desktop Mode result | Meaning | Next step |
|---|---|---|
| `PluginLoader` true, `deckyListening` true, and the Keepsake log age stays fresh | A79 holds | Build slice 23 as specified (ADR-0017): loopback server, sign-in, desktop app, pending Steam operations |
| `PluginLoader` false, or the port closed | A79 is false | **Stop and escalate.** The options are a user `systemd` service started from Keepsake (writes outside the allowlist and adds autostart) or dropping full Desktop Mode parity. Both are owner decisions. |
| `PluginLoader` true but the Keepsake log goes stale | Decky runs but stops plugin backends | Escalate as above, with the log attached |

### Results

(waiting for the device runs)

## Tests

- `scripts/desktop_mode_probe.py` is a device-only probe with no unit tests, like the slice 16 and 22 probes. `ruff` and `ruff format` pass.
- `python scripts/check.py`: see the pull request.

## Known gaps

Everything else in slice 23 waits for the step 0 results.
