# R11 report: find Windows shares on the local network

Recorded in ADR-0066 (Peter's request of 21 November 2026).

## What changed

- **`keepsake/installer/lanfind.py`:**
  - mDNS `_smb._tcp` (legacy unicast), a NetBIOS node status broadcast and a WS-Discovery Probe, run together for 2.5 s;
  - answers merged by source address, local addresses only, names cleaned, at most 64;
  - each way's count, or why it could not run.
- **App:** `installer_net_find_smb` (Installer on, user action), with a fake-socket seam for tests.
- **Device check:** `smb-find`, "Find shares on my network".
- **Interface:** **Find shares** on the Windows share form; picking a server browses `smb://<address>/` with the existing code.
- **Docs:** ADR-0066 (it also adds the local discovery endpoints to the ADR-0033 terms), T125, A206, the installer guide, CHANGELOG, device run part 4 step 4.

## Tests

- `tests/test_lanfind.py`, 14 tests:
  - merging the three ways, the name preference and sorting;
  - a way that cannot run, and only local addresses;
  - well-formed queries;
  - mDNS, NetBIOS and WS-Discovery parsing, including questions, junk, loops, other services, long labels and group names;
  - name lookups only from the server asked;
  - the device check, with no names or addresses in its findings.
- **Regression:** `test_devicechecks.py`, `test_installer_smb.py`, `test_installer_network.py`.
- **Mutation:** 22 mutants of the parsers, the trust rules, merging and the device check. All are killed.
  - The rule refusing forward compression pointers was removed: the depth limit already stops loops, and it was redundant.

## Known gaps

- Whether multicast and broadcast work from the plugin process on the handhelds, and which servers answer (A206), is unverified until the device run.

## On-device checklist

- `docs/device-run.md` part 4, step 4.
