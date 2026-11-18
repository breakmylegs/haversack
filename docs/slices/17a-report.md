# Slice 17a report: Replication's link and pairing

The first part of slice 17, recorded in ADR-0054. ADR-0054 also replaces ADR-0025's proposal and makes slice 16's measurements tuning input rather than a gate.

## What changed

- **`replication/link.py`:**
  - TLS 1.2 `ECDHE-PSK-CHACHA20-POLY1305` contexts from stdlib `ssl`, with compression off and the cipher, version and compression checked after every handshake.
  - Length-prefixed JSON frames of at most 64 KiB.
  - The pairing protocol: a public-key pairing session, committed nonces, and a 6-digit code bound to `tls-unique`, confirmed on both devices before the link key is sent.
  - The listener:
    - it exists only while switched on;
    - the pairing window lasts 120 seconds and allows 3 attempts;
    - an address is blocked after 5 failed handshakes in 60 seconds;
    - at most 8 connections at once;
    - `hello` must match the key's device ID;
    - a removed device's connections are closed.
  - `connect` for paired devices, with ping.
- **`replication/peers.py`:** paired devices and their 256-bit keys in an owner-only file. The public view never carries keys. At most 16 devices.
- **`replication/service.py`:**
  - `Links`: the listener switch, the pairing window, pairing with a typed address, answer and cancel, status, a reachability check with round trip, and remove.
  - Address parsing (host, `host:port`, `[v6]:port`; no scheme, path or user).
  - Recognition of Tailscale ranges.
- **No user interface yet:** the module stays unavailable until 17b.
- **Docs:** ADR-0054, ADR-0025 marked superseded, T112, A188, the module document, the plan (slice 16 no longer a gate; 17 in two parts; R7 direct save sync) and the changelog.

## Test results

- `tests/test_replication_link.py` (35 new, over real loopback TLS) and `tests/test_replication_rules.py` (17): all pass.
- Mutation checks: 27 mutations of the security checks (pairing window, attempts, commitment, code inputs, hello identity, revoke, blocking, self-pairing on both sides, frame limit, cipher check, compression, address parsing, peer limits). All killed after three tests were added.
- `python scripts/check.py`: all checks passed.

## Known gaps

- No discovery, Wake-on-LAN, interface choice, firewall guidance or pages yet (17b).
- TLS-PSK in the devices' Python is unverified (A188).

## On-device checklist (after 17b adds the pages)

1. **TLS-PSK.** On each handheld, run:
   ```
   python3 -c "import ssl, sys; print(sys.version, ssl.OPENSSL_VERSION, getattr(ssl, 'HAS_PSK', False))"
   ```
   It should print `True` at the end. Then check that Keepsake's Replication health check says the encrypted link is available.
2. **Pair.** Pair the two handhelds. Check that both screens show the same code, and that saying no on either device pairs nothing.
3. **Reconnect.** Reboot one device and check it reconnects without pairing again.
4. **Remove.** Remove the device on one side, and check the other is refused and asked to pair again.
