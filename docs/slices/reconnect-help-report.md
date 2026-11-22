# Controller reconnect help, without root (R22, v0.40.0)

## What changed

- New generic feature, **Reconnect help** (ADR-0082), for Bluetooth Classic controllers that pair but do not reconnect:
  - `py_modules/keepsake/device/reconnect.py`: addresses and the registered-manufacturer flag, the rules keyed by adapter and device, the append-only action log and dry run, the journal read and its signs, the classifier.
  - `py_modules/keepsake/device/bluez.py`: the BlueZ client over the system bus: device list, Reconnect assist (Design E), the reconnect watch, and the watcher thread for pair and commit (Design B) and passive suggestions.
  - `py_modules/keepsake/device/cable.py`: the cable pairing providers. The DualShock 4 provider reads in this release; its write steps are defined and tested for the root helper.
  - `py_modules/keepsake/device/reconnect_service.py`: the service the app calls; every blocking step runs in a worker thread.
- **Device, Reconnect help** tab (`src/pages/ReconnectPanel.tsx`) and the quick menu entries (`src/pages/ReconnectQam.tsx`).
- **The Device check "Controller reconnect help".**
- **`journalctl` added to the System Binary Register** (read-only, with a timeout).
- **Docs:**
  - ADR-0082;
  - threat model T147 to T149;
  - assumptions A225 to A228;
  - user guide (Device, Reconnect help);
  - device run steps 31 to 34;
  - CHANGELOG and plan.

## Research confirmations (22 November 2026)

- **BlueZ versions.**
  - SteamOS 3.9.5 stable: BlueZ version unpublished. The 3.9.2 beta shipped 5.87 (SteamOS issue 2886).
  - Bazzite stable 45.20261117: Fedora 45 ships 5.88. Bazzite's own build is unconfirmed.
- **BlueZ PR 2858** is open, unmerged and in no release.
- **Steam's Game Mode agent and the sixaxis prompt:** no evidence that it answers. Reports point to Desktop Mode only.
- **hidraw access:** Valve's `60-steam-input.rules` gives uaccess to 054C:05C4 and 09CC over USB and Bluetooth. Whether it is installed on each system is unverified.
- **Decky's root flag** is `"root"`; `"_root"` is the template placeholder.

## Tests

- `tests/test_reconnect_help.py`: 53 tests, all passing.
  - The fake BlueZ bus and fake hidraw nodes cover an unknown family, the DualShock 4 provider, and must-stay-unaffected controls (a genuine DualShock 4, an Xbox pad, an 8BitDo, and the same pad on a second adapter).
- Regressions: `tests/test_devicechecks.py`, `tests/test_host.py`, `tests/test_device_performance.py`, `tests/test_device_controllers.py`, `tests/test_device_extras.py`, `tests/test_device_battery.py`. 149 passed, 2 skipped (POSIX only).
- Mutation tests: 19 mutations on the gate, the adapter key, the identity check, discovery stop, dry run, the collision guard, masking and redaction. All 19 are caught; two survived the first run and gained tests.

## Known gaps

- O2 and O3 share one outcome until the HCI capture arrives with the root helper (R23).
- Cable pairing writes, the SSP gate and Restore backup wait for R23.
- The desktop app shows no reconnect help yet. It follows with R23.
- When the quick menu shortcuts (R25) land, the quick menu entries become registered shortcuts.

## On-device checklist

Device run steps 31 to 34 in `docs/device-run.md`. Every address in the repository is made up.
