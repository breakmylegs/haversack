# Slice 16 report: replication spike (in progress)

Branch `slice/16-replication-spike`, stacked on `slice/13-module-framework` (#17). Taken ahead of slices 14 and 15 because slice 14 waits for Peter's sign-off of the Tuning Advisor licence audit (an escalation item) and this spike does not depend on Advisor. Plan order otherwise unchanged.

**Status: waiting for device measurements.** The kit is built and tested; the transport ADR (ADR-0025) is proposed with laptop figures and needs the device figures and Peter's approval, including a change to the pairing design.

## What changed

- `scripts/replication_spike.py`: stdlib-only measurement kit (`probe`, `bench`, `mdns`, `serve`, `send`). Development tool, not shipped in the plugin. `serve` listens only while it runs, on the address given (never every interface), for one transfer, with a one-off key.
- `tests/test_replication_spike.py` (5): probe fields, a verified TLS-PSK transfer, a client without the key refused, `serve` refusing every interface, and the benchmark.
- ADR-0025 (proposed).
- Checks: ruff, ruff format, mypy and the secret scan pass; the frontend is unchanged since slice 13's passing gate. Mutation checks: removing the every-interface refusal and accepting any key identity are both caught (the first only after the listener's 10-minute timeout, since the mutated script then waits for a client).
- No plugin change, so no CHANGELOG entry and no new threat model entry; ADR-0025 strengthens T42 (pairing interception) with a confirmed comparison code.

## Laptop figures (Windows, Python 3.14.3, OpenSSL 3.0.18)

| Measure | Result |
|---|---|
| TLS-PSK available | yes |
| SHA-256 | 730 MB/s |
| TLS-PSK loopback, one process (`ECDHE-PSK-CHACHA20-POLY1305`) | 27 MB/s, 6.6 s CPU for 256 MiB |
| mDNS join and query | works, 11 replies in 3 s |

## Device runbook (Peter, both handhelds)

Copy `scripts/replication_spike.py` to each device (for example `scp scripts/replication_spike.py deck@<address>:`), then on each, with Wi-Fi on the home network:

1. `python3 replication_spike.py probe`: records Python, OpenSSL, TLS-PSK and the system binaries (`openssl`, `systemd-inhibit`, `firewall-cmd`, `udisksctl`).
2. `python3 replication_spike.py bench --mb 512`: hashing and TLS cost on the APU.
3. `python3 replication_spike.py mdns`.
4. Device A: `python3 replication_spike.py serve --bind <A's address>` (prints a one-off key). Device B: `python3 replication_spike.py send <A's address> --psk <key> --mb 2048`. Repeat with A and B swapped. If Bazzite's firewall blocks the port, note it (that is a finding for slice 17's firewall guidance) and run `sudo firewall-cmd --add-port=47110/tcp` for the test only.
5. Suspend: start a `send` of 8192 MB, press the power button on the sender for 10 seconds, wake it, and note what happened (error, stall or resume).
6. Paste each JSON result into this report.

Also run `python scripts/test_on_device.py tests/test_replication_spike.py` once on each device.

## Questions for Peter

| # | Question | Recommendation |
|---|---|---|
| R1 | Approve pairing by a confirmed comparison code (both screens show 6 digits, you confirm both) instead of typing a 6-digit code? | Yes: a typed short code cannot safely be a TLS key, and stdlib has no password-authenticated key exchange |
| R2 | Accept `openssl` from the System Binary Register for certificate creation, if present on SteamOS and Bazzite? | Yes, verified per OS by the probe |
| R3 | Minimum acceptable device-to-device throughput? | About 30 MB/s on Wi-Fi with hashing |
