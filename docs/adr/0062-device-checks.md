# ADR-0062: Device checks inside the plugin

- Status: accepted (Peter's request of 20 November 2026)
- Date: 20 November 2026
- Deciders: Peter (owner)

## Context

Peter will do the device run by installing the v0.26.0-beta.1 pre-release, with no SSH, terminal or laptop. The checklists of slices 17a to R7 relied on:
- `scripts/test_on_device.py`, for the POSIX tests: links, modes and holes; the D-Bus sleep lock; the carry-over link escape;
- `scripts/replication_measure.py` copied over with `scp`, for hashing and link speed;
- `systemd-inhibit --list`;
- `firewall-cmd --get-default-zone`.

`capture_device.sh` is not in this repository, so there is nothing to port for it. `scripts/desktop_mode_probe.py` and `scripts/network_mount_probe.py` belong to slice 23 and ADR-0033, outside this run.

## Decision

1. **Where the checks live.** A **Device checks** section on the Diagnostics page in Gaming Mode, the tab beside Settings in Keepsake's sidebar.
   - **Each check** has a Run button and shows Pass, Check (a warning), Fail or Skipped, with what it found in plain words.
   - **Run all** runs every check.
   - **Export results:**
     - saves one file, `device-checks-<date>.json`, in Keepsake's settings folder;
     - shows a QR code and a short summary on screen, so Peter can photograph them instead of copying the file.
2. **The checks** (`keepsake/devicechecks.py`):

   | Check | Replaces |
   |---|---|
   | Encrypted link: a real TLS-PSK handshake on this device | A188, `test_on_device.py` |
   | Listening addresses | A190 |
   | Found on the network: mDNS beside avahi | A190 |
   | Firewall: reads firewalld's default zone from its files | A191, `firewall-cmd` |
   | Wake-on-LAN: wired or Wi-Fi only | A190 |
   | File systems and SD card: the real transfer engine copies a synthetic folder into the library and each SD card, and checks the bytes, times, modes, links and holes. FAT, exFAT and NTFS are expected to keep no links, modes or holes | A192, `test_on_device.py` |
   | Staying awake: takes and releases both logind locks | A193, `systemd-inhibit`, the D-Bus test |
   | Battery | A194 |
   | Steam's folders | A195 |
   | Checking speed | `replication_measure.py hash` |
   | Link speed to the other handheld (both) | `replication_measure.py send` and `serve` |
   | Finding the other handheld (both) | A190 |
3. **Redaction (P12).** Findings are redacted as they are made:
   - no device, network or card names;
   - no addresses or hardware addresses;
   - no paths outside `~`, with SD cards shown as `<SD card>`.

   The export adds only the Keepsake version, the host type, the device model (shared by every unit of that model), and the Python and OpenSSL versions. A test checks that the device name never appears.
4. **Test files** are made only under folders named `.keepsake-device-check-`, and removed afterwards. That covers the library, an SD card, and `compatdata` (a folder made and removed at once).
5. **The `speed` request** is a fourth addition to protocol version 1 (ADR-0059's rule). It is the other side of the link speed check:
   - it returns up to 16 MiB of filler;
   - only paired devices reach it.
6. **What stays a written step:** only what Peter has to see, or what needs a real game or the power button:
   - the pairing codes matching;
   - the game starting with the right tool and artwork;
   - a patch arriving;
   - sleep during a transfer;
   - Wake-on-LAN actually waking a device;
   - a Steam restart after a tool copy.

   The combined list is `docs/device-run.md`.

## Consequences

- No new endpoint, binary or permission.
- **T120:** the checks' test writes and the speed request.
- The device checks run on PCs too, where some of them skip (Wake-on-LAN, firewall).
