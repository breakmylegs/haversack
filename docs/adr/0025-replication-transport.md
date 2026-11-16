# ADR-0025: Replication transport and pairing (spike)

- Status: proposed (slice 16). The choice depends on device measurements not yet taken; see `docs/slices/16-report.md`.
- Date: 16 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 4 (P9, P17), 6.4 and 8.2; ADR-0016; research sections 4.4 and 4.9

## Context

Replication needs authenticated encryption between two paired handhelds using stdlib `ssl`, with no custom cryptography and no bundled binary. The spec names two candidates: (A) self-signed certificates generated at pairing by the system `openssl`, mutual TLS with pinned fingerprints; (B) TLS-PSK through `SSLContext` PSK callbacks, if the device's Python supports them. Pairing is a time-boxed window with a 6-digit code.

## What the spike found so far (development laptop, Python 3.14.3, OpenSSL 3.0.18)

- TLS-PSK works in stdlib `ssl` (TLS 1.2 `ECDHE-PSK-CHACHA20-POLY1305`, forward secret); a wrong key is refused at the handshake.
- SHA-256 runs at about 730 MB/s, so hashing is not the bottleneck.
- TLS-PSK over loopback in one process reached 27 MB/s (both ends share the CPU and interpreter, so this understates a real link but flags cipher cost as the question to answer on the device).
- A user process can join the mDNS group and received 11 replies to a DNS-SD query in 3 seconds.

## A finding that changes the pairing design

A pre-shared key derived from a 6-digit code is weak: anyone who records one pairing handshake can try all million codes offline. So candidate B cannot use the typed code as the key. Two sound designs:

- **B1: TLS-PSK with a random 256-bit key** created on device A and carried to B through a channel the user confirms. Typing 64 hex characters with a controller is not acceptable, and stdlib has no password-authenticated key exchange (writing one would be custom cryptography).
- **A1: mutual TLS with self-signed certificates and a confirmed comparison code.** Each device has a long-term key and certificate; during the pairing window they connect with TLS (ephemeral key exchange, nothing to brute-force offline), and both screens show a 6-digit code derived from the hash of both certificates. The user checks the two codes match and confirms on both. Each side then pins the other's certificate. This is the Bluetooth "numeric comparison" model: an attacker in the middle gets a one-in-a-million chance online and nothing offline.

## Proposed decision (pending device figures)

1. **Transport: candidate A1** (mutual TLS 1.3 with pinned self-signed certificates), if `openssl` is present on SteamOS and Bazzite (System Binary Register, ADR-0018) to create the key and certificate once at pairing. TLS 1.3 also allows AES-GCM, which may be faster than the PSK suites on the Z1 Extreme and Z2 Extreme.
2. **Pairing: a confirmed comparison code instead of a typed code.** Both screens show the same 6 digits; the user confirms on both. This differs from the spec's "6-digit code entered on the other device" and needs Peter's approval (P17 and its escalation rule).
3. **Fallback if `openssl` is missing on either OS:** candidate B1 is not usable from a controller, so stop and escalate, as the spec requires.
4. **Discovery:** mDNS on stdlib sockets is feasible (laptop); confirm on both OSes. Manual address entry stays.
5. **Throughput gate:** if device-to-device throughput is below about 30 MB/s on Wi-Fi with hashing, propose options (larger records, AES-GCM suites, parallel streams, USB4 link) before slice 17.

## Consequences

- Slice 17 builds on this ADR only after Peter approves it with the device figures.
- The measurement kit (`scripts/replication_spike.py`) is a development tool and is not shipped in the plugin.
