# ADR-0056: Finding, choosing and waking devices (slice 17b)

- Status: accepted (decided under ADR-0037) The code comparison step is superseded by ADR-0070 (request, accept, type the code).
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

Slice 17a (ADR-0054) built the encrypted link and pairing without a user interface. Slice 17b makes Replication usable, and Peter asked on 18 November 2026 for sync that "just runs on the devices", without SSH or keys to manage and without being tied to one pair of devices.

## Decision

1. **The module is available on every host**: handhelds, Linux PCs and Windows PCs. It stays off by default (P13), and its listener is a second switch, also off (P17). Sending games into Steam still needs Decky (slice 19).
2. **Discovery with mDNS, stdlib only.**
   - **The service type:** Keepsake answers DNS-SD queries for its own `_keepsake._tcp.local`, only while the listener is on.
   - **The answer:** a PTR, SRV and TXT record. TXT carries `v=1`, the random device ID and the device name; the address is the answer's source. No user name, path or account.
   - **Looking for devices:** "Find devices" sends one query from a temporary port and collects answers for 2 seconds. RFC 6762 section 6.7 has responders answer such queries directly to that port, so browsing needs no access to port 5353.
   - **The responder:**
     - It binds UDP 5353 with address reuse, so it can sit beside `avahi-daemon`, and joins 224.0.0.251. Multicast can only be received on the wildcard address, which is why only this socket binds it; the link listener never does.
     - It answers one-shot queries directly, and multicast queries at most once a second.
     - If it cannot bind, discovery is reported in Health, and typing the address still works.
   - **Nothing found is trusted:** a found device still has to pass pairing or its link key.
3. **Which addresses the listener binds** (ADR-0016's "selected LAN interfaces"):
   - **By default:** every private LAN address (RFC 1918 and IPv6 ULA) and every overlay address (Tailscale's `100.64.0.0/10` and `fd7a:115c:a1e0::/48`).
   - **Never:** public, loopback or link-local addresses.
   - **One address only:** the user can choose a single address instead. If it is no longer on the device, the listener does not start and says why.
   - **How addresses are read:** from `/proc/net/fib_trie` and `/proc/net/if_inet6` on Linux, and from the host name's addresses on Windows. No binary is used.
4. **Wake-on-LAN.**
   - **What is shared:** each device sends the hardware addresses of its physical adapters (at most 4) in its `hello`.
   - **Waking:** "Wake" broadcasts the standard magic packet to UDP port 9, only from a user action.
   - **Limits:** a handheld asleep on Wi-Fi usually cannot be woken this way, and the page says so. A PC on a cable usually can, if its firmware allows it.
   - **Allowlist:** this is the Wake-on-LAN that ADR-0047 accepted into slice 17. It goes only to the local broadcast address.
5. **Firewall guidance, never firewall changes.**
   - **What Keepsake does:** it changes no firewall. Health says what to allow, using TCP 47110 and UDP 5353:
   - **Windows:** Windows asks whether Python may use the network the first time; allow it on private networks.
   - **firewalld running (Bazzite and other Fedora-based systems):** the default zone allows ports above 1024 on home networks (A191).
   - **Otherwise:** no firewall was found.
6. **The pages.**
   - **Where:** a **Devices** tab in Gaming Mode and a **Devices** page on the desktop.
   - **What they offer:**
     - the listener switch and the address choice;
     - "Let a device pair with this one", showing the window's seconds left;
     - "Find devices", and pairing by a typed address;
     - the code to compare, with "The codes match" and "They differ";
     - paired devices with Check (round trip, and the slow or relayed-link note), Wake and Remove (confirmed).
   - **Telling the user:** when a pairing request arrives, a toast says so and the page refreshes. A page follows a running pairing every second.
7. **Settings:** `replicationListener` (off) and `replicationAddress` (empty means all). The listener comes back after a restart only if the user left it on.

## Consequences

- No new endpoint beyond those already allowed while the module and listener are on: the LAN peer port, mDNS, and the local broadcast for Wake-on-LAN.
- **T114:** discovery and Wake-on-LAN.
- **A190 and A191:**
  - A190: mDNS beside `avahi-daemon` and Wake-on-LAN on the handhelds;
  - A191: the Bazzite firewall default.
- **Device checks:** in `docs/slices/17b-report.md`.

## Sources

- [RFC 6762](https://www.rfc-editor.org/rfc/rfc6762) (Multicast DNS), section 6.7 (one-shot queries are answered directly).
- [RFC 6763](https://www.rfc-editor.org/rfc/rfc6763) (DNS-Based Service Discovery).
- AMD, "Magic Packet Technology" white paper (publication 20213): 6 bytes of `FF`, then the hardware address 16 times.
- Fedora's FedoraWorkstation firewalld zone allows TCP and UDP 1025 to 65535: [Fedora discussion](https://discussion.fedoraproject.org/t/firewall-default-settings-config-after-fresh-install-fedora-37-ws/80568) and [the 2014 devel thread](https://lists.fedoraproject.org/pipermail/devel/2014-December/205015.html). Bazzite's default is unverified (A191).
