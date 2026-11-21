# ADR-0066: Find Windows shares on the local network

- Status: accepted (Peter's request of 21 November 2026, decided under ADR-0037). Adds local discovery endpoints to the terms of ADR-0033.
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

Install, then From a network location, then Windows share (SMB), needs the server's address typed in. Peter wants a **Find shares on my network** list above the address field:
- it discovers SMB servers with no binary and no root;
- picking one lists its shares through the existing pysmb code (ADR-0034), then folders as today;
- it is local network only and read only, on the endpoint rules of ADR-0033.

## Options

| Way | Who answers | Pure stdlib? | Verdict |
|---|---|---|---|
| mDNS `_smb._tcp.local` (RFC 6762, DNS-SD RFC 6763) | NAS boxes (Synology, QNAP, TrueNAS), Macs, Linux with Avahi and Samba | Yes: one UDP query; legacy unicast (a query from an ordinary port) makes responders answer straight back, so port 5353 never has to be bound | **Used** |
| NetBIOS node status (RFC 1002, UDP 137 broadcast) | Windows PCs with NetBIOS over TCP/IP on (the default on private networks), Samba | Yes | **Used** |
| WS-Discovery Probe (UDP 3702 multicast) | Windows 10 and 11 (Function Discovery), Samba servers running `wsdd` | Yes, the answer is read with a pattern, so `xml` is not needed (ADR-0030) | **Used**, with the name then asked by NetBIOS directly |
| LLMNR, SSDP | Name lookup only, or media devices | | Not useful for listing shares |
| `smbclient -L`, `avahi-browse`, `nmblookup` | | Binaries | Rejected (P9) |

## Decision

1. **`keepsake/installer/lanfind.py`.** It runs all three ways together for 2.5 seconds, only when the user presses **Find shares**, and merges the answers by address. The name comes from mDNS, then NetBIOS, then WS-Discovery's NetBIOS reply, else the address itself. It is the Installer's own code: it shares nothing with Replication's mDNS (P13).
2. **Trust.** A server's address is always the **source address of its answer**, never an address written inside an answer. Only local addresses are kept: the ADR-0033 list of RFC 1918, `100.64/10`, loopback, link-local and `fc00::/7`. Names are cleaned (letters, digits, spaces and a few marks, at most 63 characters). At most 64 servers.
3. **Picking a server** browses `smb://<address>/` with the existing code: every ADR-0033 and ADR-0034 rule applies, including SMB 2 only, the local-address check, and credentials only from their own fields. Nothing is sent to a server until the user picks it.
4. **Endpoints added to the ADR-0033 terms.** Each is used only while the Installer is on, only after the press, and with a multicast TTL of 1, so nothing leaves the local network:
   - `224.0.0.251:5353` (mDNS);
   - `255.255.255.255:137` (NetBIOS broadcast);
   - `239.255.255.250:3702` (WS-Discovery);
   - UDP 137 on a local host that answered WS-Discovery, to ask its name.

   This is an addition to the network allowlist, decided under ADR-0037: no data leaves the device except the fixed questions.
5. **Device check:** "Find shares on my network" runs the search and reports how many servers each way found, or why a way could not run. It passes when any server answers, warns when the searches went out but nothing answered, and fails when no search could be sent. No names or addresses appear in its findings.

## Consequences

- On networks that block multicast or broadcast (some mesh Wi-Fi and guest networks), nothing is found. Typing the address still works, and the page says so.
- A device on the network can answer with any name. It still has only its own address, which must be local, and the user chooses it. See T125.
- A206 in `docs/assumptions.md`.
