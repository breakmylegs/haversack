# S2 report: Replication goes device to device

Peter's hard requirements for slices 16 to 20, recorded in ADR-0045.

## What changed

- **ADR-0045.** The eight requirements are checked against primary sources (Tailscale connection types, systemd inhibitor locks, Python `ssl`, `socket` and `os`, Windows power and path APIs). The open details are decided:
  - **slow or relayed links:** what "slow or relayed" means (under 10 MB/s or over 50 ms);
  - **sparse files:** sent as data ranges plus hole ranges, never transformed;
  - **resume:** re-verifies only chunks that might be incomplete;
  - **clean-up:** limited to what the journal recorded;
  - **space margin:** 5 percent or 2 GiB;
  - **sleep on Linux:** a minimal pure-Python D-Bus client for the logind delay lock, rather than a System Binary Register entry;
  - **speed:** 4 MiB reads, hashing off the event loop, and optional parallel streams;
  - **cross-OS targets:** names Windows forbids are refused, not renamed.
- **`docs/modules/replication.md`** carries the requirements. The slice 16 to 20 rows in `docs/plan.md` carry them as acceptance criteria.
- **Enforced now:**
  - **`keepsake/replication/policy.py`:**
    - `require_no_compression` and `check_uncompressed`;
    - `space_needed`;
    - `link_verdict`.
  - **`tests/test_replication_rules.py`:**
    - **Forbidden imports:** it fails if any module under `keepsake/replication/` imports a cloud store, the sync engine, cloud sign-in, the app, or any compression module, or imports anything dynamically.
    - **The checker:** it is proven against synthetic code.
    - **A real handshake:** a TLS-PSK handshake reports no compression on both ends.
- **`scripts/replication_measure.py`:** the slice 16 measurements, stdlib only.
- **Threat model:** T102 and T103. **Assumptions:** A176 (verified) and A177 (device).

## Test results

- `tests/test_replication_rules.py` (17) and `tests/test_replication_measure.py` (3): all pass on Windows Python 3.14, including a real TLS-PSK handshake.
- Mutation checks: 9 mutations, all killed after one test was tightened.

## Known gaps

The transfer engine, journal, clean-up, sleep inhibitor, progress interface and fault injection are built in slices 16 to 20, as planned.

## Device steps: slice 16 measurements

You need both handhelds on the same Wi-Fi, SSH to each (as for `deploy:device`), and this repository on the laptop.

1. **Copy the script to both devices.** From the laptop:
   ```
   scp scripts/replication_measure.py deck@<legion-go>:/tmp/
   scp scripts/replication_measure.py deck@<legion-go-2>:/tmp/
   ```
2. **Python and TLS-PSK.** On each device:
   ```
   python3 -c "import ssl, sys; print(sys.version, ssl.OPENSSL_VERSION, getattr(ssl, 'HAS_PSK', False))"
   ```
3. **Hashing speed.** On each device, with the charger plugged in and again on battery:
   ```
   python3 /tmp/replication_measure.py hash --gib 4
   ```
4. **Throughput.** On the Legion Go 2 (receiving), start the server and leave it running:
   ```
   python3 /tmp/replication_measure.py serve
   ```
   Then on the Legion Go (sending), using the Legion Go 2's Wi-Fi address (`ip -4 addr show wlan0`):
   ```
   python3 /tmp/replication_measure.py send <go2-address> --gib 4 --read-kib 256
   python3 /tmp/replication_measure.py send <go2-address> --gib 4 --read-kib 4096
   python3 /tmp/replication_measure.py send <go2-address> --gib 4 --read-kib 4096 --streams 2
   python3 /tmp/replication_measure.py send <go2-address> --gib 4 --read-kib 4096 --streams 4
   ```
   Stop the server with Ctrl+C and start it again with TLS:
   ```
   python3 /tmp/replication_measure.py serve --tls
   ```
   Then repeat the four `send` lines with `--tls` added.
5. **Remote link (optional, if you use Tailscale).** Repeat one TLS `send` line to the Legion Go 2's Tailscale address, then:
   ```
   tailscale status
   tailscale ping <go2-tailscale-name>
   ```
6. **Sleep inhibitor.** On one device, start a 60-second delay lock and list the locks:
   ```
   systemd-inhibit --what=sleep --mode=delay --who=keepsake-test --why="slice 16 check" sleep 60 &
   systemd-inhibit --list
   ls -l /run/dbus/system_bus_socket
   ```
   Note whether `keepsake-test` appears and whether any permission prompt or error was shown.
7. **Send back:** every JSON line printed (from both `send` and `serve`), the Python line from step 2, and the step 5 and 6 output.
8. **Tidy up.** On both devices:
   ```
   rm /tmp/replication_measure.py
   ```
