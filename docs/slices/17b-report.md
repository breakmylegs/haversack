# Slice 17b report: finding, choosing and waking devices

The second part of slice 17, recorded in ADR-0056. With 17a (ADR-0054), Replication can now be switched on and used to pair devices. Sending games follows in slice 18.

## What changed

- **`replication/discovery.py`:** mDNS for Keepsake's own `_keepsake._tcp.local`, stdlib only.
  - The responder answers only while the listener is on: directly to one-shot queries, and at most once a second by multicast. It binds UDP 5353 with reuse, beside `avahi-daemon`.
  - `browse` sends one query from a temporary port and collects answers for 2 seconds.
  - Packet parsing has length, count and pointer-loop guards.
- **`replication/netinfo.py`:**
  - the device's LAN and VPN overlay addresses, from `/proc/net/fib_trie` and `if_inet6`, or the host name on Windows;
  - the bind choice: all of them by default, or the one the user chose; never public, loopback or link-local;
  - physical adapters' hardware addresses, and the Wake-on-LAN magic packet.
- **Link and peers:** `hello` carries the hardware addresses for Wake-on-LAN, and the peer store keeps them. The listener binds several addresses. A pairing announces itself once its code is ready.
- **Service:** listen addresses, discovery, find, wake, health checks and firewall advice. Keepsake never changes a firewall.
- **App:**
  - the Replication module is available on every host, and off by default;
  - 12 new calls (`replication_*`), kept equal in `main.py` and the PC host;
  - two settings, `replicationListener` and `replicationAddress`;
  - a toast and an event when a pairing request arrives.
- **Pages:** a **Devices** tab in Gaming Mode (`ReplicationPage.tsx`) and a **Devices** page on the desktop. Both offer the listener switch, the address choice, the pairing window, Find devices, pairing by address, the code to compare, and paired devices with Check, Wake and Remove.
- **Docs:** ADR-0056, T114, A190, A191, the user guide (`docs/user/replication.md`), the module document, the plan and the changelog.

## Test results

- `tests/test_replication_devices.py` (24 new): pass. They cover:
  - discovery packets, the responder's answers and rate limit, and browsing over loopback;
  - addresses and bind choice, hardware addresses and the magic packet;
  - firewall advice and settings;
  - two whole apps pairing through their calls, then check, wake and remove;
  - the listener coming back after a restart only when it was left on, and the module off by default.
- Covering tests also pass: `test_replication_link.py`, `test_replication_rules.py`, `test_host.py`, `test_hosts.py`, `test_settings.py` and `test_modules.py`. One expectation in `test_modules.py` changed on purpose: Replication is now available.
- Mutation checks: 25 mutations across discovery, addresses, wake, the service, the app wiring and settings. All killed after three tests were added and one was extended.
- `tsc`, the desktop build and eslint are clean.

## Known gaps

- No transfers yet (slice 18).
- On the devices, it is unverified whether mDNS works beside `avahi-daemon`, and how Wake-on-LAN behaves (A190). Bazzite's firewall default is also unverified (A191).

## On-device checklist

1. **TLS-PSK:** check the encrypted link is available on each handheld, under Settings, Health, Replication (A188).
2. **Switch on:** in Modules, switch on Replication on both handhelds. On **Devices**, switch on **Let other devices reach this one**. Check that Health shows the listening address and "Other devices can find this one".
3. **Find and pair:** on one device, press **Let a device pair with this one**. On the other, press **Find devices** and choose it. Check:
   - the same code shows on both;
   - **They differ** pairs nothing;
   - **The codes match** on both pairs them.
4. **Reconnect:** reboot one device and press **Check** on the other. It should be reachable without pairing again.
5. **By address:** pair a PC or a device on Tailscale by typing its address.
6. **Wake:** with a PC on a cable asleep, press **Wake**.
7. **Remove:** remove a device on one side. Check that the other side's **Check** says to pair again.
8. **Bazzite firewall:** run `firewall-cmd --get-default-zone` and report the zone (A191).
