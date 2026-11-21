# ADR-0054: Replication link and pairing, built for any connection speed

- Status: accepted (decided under ADR-0037, after Peter's direction of 18 November 2026). Supersedes ADR-0025's proposal. Points 4.5 to 4.7 (confirming on both devices, the pairing window, comparing instead of typing) are superseded by ADR-0070, pairing by code.
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0025 left the transport open until slice 16 measured the two handhelds' Wi-Fi. Peter decided on 18 November 2026:
- the design should not depend on his Wi-Fi: it should suit fast and slow connections alike;
- BitTorrent should be considered, for games and for saves;
- direct save sync between devices with no cloud (option C) is wanted, beside one-button cloud sign-in under a dedicated Keepsake account (option A).

ADR-0025 also found that a key derived from a 6-digit code can be brute-forced offline. It proposed certificates made by the system `openssl` with a comparison code. That needs a System Binary Register entry (ADR-0018), and stdlib `ssl` cannot make certificates itself.

## Decision

1. **Slice 16 is no longer a gate.** Its device figures become tuning input, gathered with the device checks of slice 17 onwards. Speed is handled by design (point 6), not by a threshold.
2. **Transport: TLS-PSK from stdlib `ssl`.**
   - **Cipher:** TLS 1.2 with only `ECDHE-PSK-CHACHA20-POLY1305`. Each connection makes a fresh key exchange, so it is forward secret. ChaCha20-Poly1305 is fast in software on any CPU.
   - **No system binary:** `openssl` is not needed, and nothing is added to the register.
   - **Checks on every connection:**
     - compression off and checked (ADR-0045);
     - the cipher and version checked after the handshake.
   - **Fail closed:** `SSLContext` PSK callbacks need Python 3.13 or later built with PSK support. Without them Replication stays off and says why. The device's Python is checked in the device run (A188).
3. **Link keys.**
   - **The key:** each paired device has a random 256-bit key, made by the device that started the pairing and sent once over the pairing session.
   - **Storage:** in `replication-peers.json`, owner-only (mode 600). Keys are never shown, logged or sent anywhere else.
   - **Identity:** the PSK identity is the connecting device's ID. The listener looks the key up by that ID, and after the handshake the device's `hello` must name the same ID.
4. **Pairing: a confirmed comparison code, protected against a device in the middle.**
   1. **The session:** pairing uses the same cipher with a key that is public on purpose. That makes it an ordinary unauthenticated key exchange, encrypted against anyone listening.
   2. **Nonces, commit first:**
      - the starting device commits to a random nonce by sending its SHA-256;
      - the other device sends its own nonce;
      - the first then reveals its nonce, and the commitment is checked.
   3. **The code:** both screens show a 6-digit code derived from the TLS session's `tls-unique` binding, both nonces and both device IDs.
   4. **Why this order matters:** it is the short authenticated string method (Vaudenay 2005; the same idea as Bluetooth numeric comparison).
      - A device in the middle runs a separate TLS session with each side, so the bindings differ.
      - The commitment means it cannot pick a nonce after seeing the other one.
      - So it gets one chance in a million per attempt, and nothing to try offline.
   5. **Confirming:** the user confirms the codes match on both devices. Only then is the link key sent. A "no" on either device, or 120 seconds without an answer, pairs nothing.
   6. **The pairing window:** it opens from a user action, for 120 seconds and at most 3 pairing handshakes. Outside it, the pairing key is refused during the handshake.
   7. **Why not a typed code:** the spec's typed 6-digit code would be brute-forceable offline. Comparing codes needs no typing and is stronger (P17's escalation, decided here).
5. **The listener.**
   - **Off by default:** no socket exists while it is off.
   - **Who is served:** only paired devices after authentication, apart from the pairing window above.
   - **Limits:**
     - at most 8 connections at once;
     - a 10-second handshake limit;
     - frames of at most 64 KiB;
     - an address with 5 failed handshakes in 60 seconds is refused for the rest of that time.
   - **Removing a device** deletes its key and closes its open connections. The other device's next connection is refused, and it says to pair again.
   - **Addresses:** the port defaults to TCP 47110. The user can type an address, such as a LAN or a Tailscale address with an optional port. No scheme, path or user name is accepted.
   - **Overlay links:** Tailscale ranges (`100.64.0.0/10`, `fd7a:115c:a1e0::/48` and `*.ts.net`) are recognised, so a slow link can be explained as possibly relayed (ADR-0045).
6. **Fast and slow connections (built in slice 18, recorded here).**
   - **Streams:** start with one, and add more up to 4 only while the measured rate keeps rising.
   - **Pieces:** fixed 4 MiB, each verified on arrival and against the root hash before promote.
   - **Resume:** from the journal, so a slow or broken link loses at most the pieces in flight.
   - **Bandwidth cap:** optional.
   - **Shown to the user:** speed, time left and the link verdict.
7. **BitTorrent: not used, though some of its ideas are.**
   - **Why not:**
     - **It needs a compiled library.** No maintained pure-Python implementation exists; libtorrent is compiled C++ (P9).
     - **Its encryption does not authenticate.** Message Stream Encryption only hides traffic; it does not prove who the other end is (P17).
     - **It reaches the internet.** Trackers, the DHT and peer exchange exist to find strangers, which breaks the direct-only rule (ADR-0045).
     - **Swarming gains little here.** With two or three of the user's own devices there are almost no other peers to share the load.
   - **What is borrowed:**
     - fixed pieces verified against a SHA-256 hash tree (as in BitTorrent v2, BEP 52);
     - resume from the set of verified pieces;
     - in slice 18, pulling pieces from more than one paired device at once.
   - **Saves:** BitTorrent offers saves nothing. They are small, and what matters for them is history, conflicts and an off-site copy.
8. **Option C, direct save sync, becomes slice R7.**
   - **What it is:** saves go device to device over this link, with no cloud account. It uses Saves' own snapshot and conflict rules.
   - **When:** after slice 18, because it reuses the transfer engine.
   - **Rules:** it has its own ADR when built. Saves still owns save data (P14), and Replication's engine never writes Saves paths.
9. **Slice 17 is built in two parts.**
   - **17a (this change):** the link, pairing, the peer store and the service, without a user interface. The module stays unavailable.
   - **17b:** mDNS discovery, Wake-on-LAN, the listener's interface choice, firewall guidance, and the pages in Gaming Mode and on the desktop. The module becomes available.

## Consequences

- **Network:** no new endpoint. The LAN peer port and mDNS are already allowed while the module and listener are on.
- **Device checks (A188):**
  - TLS-PSK in the device's Python;
  - pairing between the two handhelds;
  - a reconnect after a reboot.

## Sources

- Python `ssl`: [SSLContext.set_psk_client_callback and set_psk_server_callback](https://docs.python.org/3/library/ssl.html#ssl.SSLContext.set_psk_client_callback) (new in 3.13); [SSLSocket.get_channel_binding](https://docs.python.org/3/library/ssl.html#ssl.SSLSocket.get_channel_binding).
- [RFC 5929](https://www.rfc-editor.org/rfc/rfc5929): channel bindings for TLS (`tls-unique`).
- [RFC 7905](https://www.rfc-editor.org/rfc/rfc7905): ChaCha20-Poly1305 cipher suites for TLS, including `ECDHE-PSK`.
- S. Vaudenay, "Secure Communications over Insecure Channels Based on Short Authenticated Strings", CRYPTO 2005.
- BitTorrent: [BEP 3](https://www.bittorrent.org/beps/bep_0003.html) (protocol), [BEP 52](https://www.bittorrent.org/beps/bep_0052.html) (v2 hash trees); libtorrent is C++ ([libtorrent.org](https://www.libtorrent.org/)).
- The laptop check of 18 November 2026: Python 3.14.3 with OpenSSL 3.0.18 negotiates `ECDHE-PSK-CHACHA20-POLY1305` on TLS 1.2, with no compression and matching `tls-unique` on both ends, over asyncio streams.
