# R12 report: install straight from a network ISO

Recorded in ADR-0067 (Peter's request of 21 November 2026). It asks Peter to approve `fusermount3` in the System Binary Register (ADR-0018).

## What changed

- **`keepsake/installer/netfuse.py`:** a pure-Python, read-only, one-file FUSE file system:
  - the kernel protocol handler;
  - `BlockCache` (4 MiB blocks, 16 kept, read ahead);
  - `SmbRange` (pysmb offset reads) and `HttpRange` (`Range` requests, `206` only);
  - `Mount` (`fusermount3` with `auto_unmount`, the descriptor over a socket pair, four reader threads).

  It is all behind `FUSERMOUNT_APPROVED = False`.
- **`keepsake/installer/inplace.py`:** network file system detection from `/proc/self/mounts`, `copy_iso` (progress, Stop, space check, partial copy removed), and the Device check's ISO finder and loop test.
- **Installer:**
  - an ISO on a network or FUSE mount that udisks refuses raises `InPlaceFailed`;
  - `inPlace` and `netMount` are recorded on the job;
  - `on_released` is called whenever a disc is let go.
- **App:**
  - `installer_start` copies and then installs on `InPlaceFailed` (option A);
  - network downloads try in place first once approved, else copy as before;
  - mounts are closed with the disc.
- **Device check:** `network-iso`, "Network ISO in place". `network_mount_probe.py --loop-test` is removed.
- **Docs:**
  - ADR-0067; ADR-0018 lists `fusermount3` as proposed; ADR-0033's runbook points to the Device check;
  - T126, A207, the installer guide, CHANGELOG, device run part 4 step 5.

## Decisions taken under ADR-0037

- **Route:** Keepsake's own FUSE file system over `fusermount3`. gvfs and kio-fuse were rejected: more binaries, a desktop session, password dialogs, and no Gaming Mode. A user-namespace mount was rejected for now: `ctypes`, unprivileged namespaces and passing descriptors are all unverified.
- **Copying is the automatic fallback everywhere.** A local ISO that fails is a real error and is not copied.

## Needs Peter

- **Approve `fusermount3`** for the register (the table in ADR-0067). Approval then turns `FUSERMOUNT_APPROVED` on in its own change, and the device run checks it (A207).

## Tests

- `tests/test_netfuse.py`, 25 tests:
  - protocol: init negotiation, lookup, getattr, opening and refusal for writing, reads and their limit, errors, readdir with offsets and sizes, the rest;
  - the block cache, HTTP ranges (including a `200` claiming to be a part), and SMB ranges with one reconnect;
  - the approval gate, network file system detection (deepest mount wins, whatever the order), copying, the ISO finder and loop test;
  - the Installer's in-place-or-copy decision, and the device check.
- `tests/test_installer_smb.py`, 4 new app tests:
  - in place once approved, with nothing staged and the mount closed with the disc;
  - copy when the mount fails, and copy until approved;
  - a mounted share that refuses, which is copied and then installed.
- `tests/test_network_probe.py`: rewritten for what the probe still does, with no paths reported.
- **Regression:** `test_installer.py`, `test_installer_network.py`, `test_installer_webdav.py`, `test_devicechecks.py`.
- **Mutation:** 32 mutants of the protocol, the ranges, the cache, detection, copying, the Installer decision and the app's order. All are killed after four sharper tests were added.

## Known gaps

- The mount itself (`fusermount3`, `/dev/fuse`, udisks on a FUSE file) can only be checked on a device after approval (A207). The protocol is tested byte for byte, but not against a live kernel.

## On-device checklist

- `docs/device-run.md` part 4, step 5.
