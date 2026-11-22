# The Keepsake Helper and reconnect help's root jobs (R23, v0.41.0)

## What changed

- **The Keepsake Helper** (ADR-0083), a separate plugin in `helper/`:
  - `plugin.json` has the root flag; Keepsake's own `plugin.json` still has none.
  - Python stdlib only, with no network code.
  - `server.py`: the socket, the three caller checks (user ID, Decky's executable, per-boot token), the version lock, the job list and the SSP lease.
  - `bluetooth.py`: BlueZ's `info` file, with backups, an atomic write and the bluetoothd stop and start through systemd over D-Bus.
  - `keyfile.py`: changes only `[LinkKey]` and Trusted.
  - `hid.py`: USB provider nodes and three feature reports only.
  - `mgmt.py`: SSP through the kernel's management channel, and the HCI capture as btsnoop.
- **Packaging and install.**
  - `scripts/package.py` builds `Keepsake-helper-v<version>.zip`, and `scripts/release.py` lists it in the signed `SHA256SUMS`.
  - Keepsake verifies it (`Updater.prepare_helper`, which refuses unsigned releases) and hands it to Decky's installer.
- **Keepsake's side.**
  - `device/helper.py` (client), `device/sspgate.py`, `device/hcilog.py`.
  - Cable pairing, Restore backup, the SSP gate and the capture in `reconnect_service.py`.
  - The classifier uses the capture to tell O2 from O3.
- **Screens.** In Device, Reconnect help (`src/pages/ReconnectHelper.tsx`):
  - the helper card (install or update);
  - cable pairing with a two-press confirmation;
  - Restore backup;
  - the reversed-key-order toggle;
  - the SSP gate with its two-step warning.
- **Docs:**
  - ADR-0083, and ADR-0075 tier 1 accepted;
  - threat model T150 to T153;
  - assumptions A229 to A233;
  - write allowlist rows in the v2 build prompt;
  - user guide, device run steps 35 to 38, CHANGELOG and plan.

## Tests

- `tests/test_root_helper.py`: 42 passed, 1 skipped (the symbolic link test is POSIX, marked `posix` for the device run).
- `tests/test_reconnect_help.py`: 53 passed.
- Regressions: `tests/test_update.py`, `tests/test_scripts.py`, `tests/test_pcupdate.py`, `tests/test_fuzz_parsers.py`, `tests/test_everyday_polish.py`, `tests/test_host.py`, `tests/test_devicechecks.py`. All passed with the new tests (226 passed, 2 skipped).
- Mutation tests: 28 mutations on the token, version lock, job list, peer checks, request size, lease, hidraw allow-list, the restart-always rule, backup-first, the record check, address validation, in-place key edits, power-cycle consent, unsigned refusal, identity, verify-before-write, no-game, dry run, the confirmation text and the gate's adapter path. All 28 are caught; one survived the first run and gained a stronger test.

## Known gaps

- On-device only:
  - the shared executable (A229);
  - `bind` with a channel (A230);
  - SSP off while powered (A231);
  - Decky installing a second plugin from this zip (A232).
- The desktop app's reconnect help page moves to R24.
- DualShock 3 and DualSense providers are still candidates.

## On-device checklist

Device run steps 35 to 38 in `docs/device-run.md`, after steps 31 to 34.
