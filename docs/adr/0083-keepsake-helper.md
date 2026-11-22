# ADR-0083: The Keepsake Helper, a separate root plugin

- Status: accepted (ADR-0075 tier 1, option B, approved by Peter on 22 November 2026; details decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

**Approval.** Peter approved ADR-0075 tier 1 as recommended: "a separate signed, version-locked helper plugin with an authenticated minimal interface and an allow-list". He asked first for:
- a check of whether Decky's root flag is `"root"` or the template's `"_root"`;
- the reconnect help root jobs (ADR-0082) as the helper's first work: HCI capture, cable pairing and the SSP gate.

**Facts checked on 22 November 2026:**
- **The root flag.** decky-loader's `sandboxed_plugin.py` runs a plugin as root when `"root" in self.flags`. The template's `"_root"` is a disabled placeholder.
- **The management socket.** The kernel's Bluetooth management interface (MGMT) needs CAP_NET_ADMIN:
  - Set Secure Simple Pairing is opcode 0x000B on `HCI_CHANNEL_CONTROL`;
  - the monitor channel (`HCI_CHANNEL_MONITOR`) carries every HCI packet, as btmon reads it.
- **BlueZ's files.** BlueZ keeps each device's pairing in `/var/lib/bluetooth/<ADAPTER>/<DEVICE>/info`, root-owned, mode 0600. bluetoothd reads it only at start.
- **No `/etc`.** SteamOS keeps `/etc` changes only through a keep list. The helper needs nothing there.

## Decision

### 1. A second plugin, "Keepsake Helper"

**What it is.**
- Its own `plugin.json` has `"flags": ["root"]`. Keepsake's own `plugin.json` stays without it (P8). A test checks both.
- It is Python stdlib only, a few hundred lines, with no network code. It reuses an exact copy of Keepsake's pure-Python D-Bus client (`dbus.py`), and a test checks that the two files are byte-identical.
- Its quick menu entry only says it is used by Keepsake. Keepsake shows its state and offers its jobs under **Device**, **Reconnect help**.

**How it ships.**
- **Signed:** `Keepsake-helper-v<version>.zip` is built by `scripts/package.py` and published with every release. It is listed in `SHA256SUMS` under the release signature (ADR-0036).
- **Installed by Decky:** Keepsake verifies the signature and hash, refusing an unsigned release outright. It then hands the zip to Decky's own installer, the same route as updates (ADR-0002), and Decky asks the user to confirm.
- **Version-locked:** the helper reads its `VERSION` and refuses any request from another Keepsake version. When Keepsake updates, the screen offers "Update helper".

### 2. The interface

**The socket.** `/run/keepsake-helper/helper.sock` is owned by the Decky user, mode 0600, in a root-owned 0755 folder.

**Three checks on every connection:**
1. `SO_PEERCRED`: the caller's user ID is the Decky user.
2. The caller's executable (`/proc/<pid>/exe`) is the helper's own, Decky's plugin loader. Another program run by the user cannot connect.
3. The request carries the per-boot token from `/run/keepsake-helper/token` (owner-only), compared in constant time.

**Framing.** One request per connection: a 4-byte length, then JSON, at most 64 KB. Each request carries Keepsake's version, and replies are JSON.

**The jobs.** Nothing else is accepted:

| Job | What it does | Limits |
|---|---|---|
| `ping` | Version, and the adapters where the helper turned SSP off | |
| `hid.get` / `hid.set` | Feature reports to a controller on USB | Only `/dev/hidrawN` nodes on USB whose vendor and product are a cable pairing provider's (054C:05C4, 054C:09CC), checked in sysfs each time. Only GET 0x12 (16 bytes), SET 0x13 (23 bytes) and SET 0x14 02 (17 bytes) |
| `bt.state` | Whether BlueZ has a record, a key, trust and a service cache for a device | Never returns the key |
| `bt.install` | Back up the device's `info` file, change only `[LinkKey]` (Key, Type, PINLength=0) and `[General]` Trusted=true, keeping every other line byte for byte | bluetoothd is stopped and started through systemd over D-Bus, and always started again. The write is atomic, root-owned, mode 0600, with no symbolic links. The record must exist. At most 5 backups |
| `bt.restore` | Put back the newest backup | Same restart |
| `ssp.set` / `ssp.renew` / `ssp.release` | SSP on or off through MGMT | Off needs a lease of at most 5 minutes |
| `hci.capture` | The monitor channel for at most 60 s, as btsnoop | At most 8 MB, returned to Keepsake, never written by the helper |

### 3. SSP is never left off

- **The lease.** Turning SSP off needs a lease, and Keepsake's gate renews it every 30 s. If renewals stop (Keepsake unloaded, crashed, disabled or uninstalled), the helper turns SSP back on within seconds of expiry.
- **Recorded state.** The helper records the adapters it turned off, so it reconciles on start: SSP goes back on after a helper restart or a reboot.
- **On unload and uninstall,** the helper restores SSP.
- **Through Keepsake.** Keepsake also releases the gate when the gate is switched off and when the Device module stops.

### 4. Keepsake's side

`keepsake/device/helper.py` (client), `sspgate.py`, `hcilog.py` and the reconnect service.

**Cable pairing** (Design C, through ADR-0082's providers):
- **Preconditions:** the user's rule for that device; no game running; BlueZ's record and service cache present (otherwise "use Reconnect once in pairing mode first").
- **Identity:** the identity read over USB must match the chosen device, or nothing is written.
- **The writes:** a random 16-byte key, written with 0x13 then committed with 0x14 02. The stored host is read back, and if it is not this adapter nothing is written on the handheld. Only then does `bt.install` run, with the provider's key type.
- **Key order.** An advanced "reversed key order" toggle stores the key in reverse byte order, for one controlled experiment.
- **The sixaxis gotcha.** After the write, the journal is checked for BlueZ's sixaxis plugin. If it acted while the pad was plugged in, the screen says to unplug and run again. Keepsake never answers "Authorize service". It never calls `RemoveDevice`.
- **Restore backup** is offered whenever a backup exists.
- **Confirmation.** Every restart asks twice, and says that all Bluetooth devices drop for a few seconds.

**The SSP gate** (Design A):
- **Off by default.** It is offered when a helped device's diagnosis is O3, or when the gate is already on.
- **Turning it on** takes a toggle, then the adapter-wide security warning, then "I understand". The backend also requires that exact text.
- **The rule:** SSP is on while the adapter is Discovering or a pairing is armed, and off otherwise, after a 1.5 s debounce.
- **Re-applied** when bluetoothd restarts (`NameOwnerChanged` for `org.bluez`) and when the adapter powers on.
- **Power cycle.** If the kernel refuses SSP off while powered, the gate cycles the adapter's power only when no device is connected. Otherwise it asks ("Restart Bluetooth").
- **No `btmgmt`.** MGMT is spoken directly through `socket` (with `ctypes` for `bind` only if this Python's `bind` does not take a channel), so `btmgmt` is not needed and the System Binary Register is unchanged. The research suggested `btmgmt` first with raw MGMT as a fallback; the raw command alone avoids a binary dependency.

**HCI capture.**
- **In the diagnosis.** When the helper is ready, the diagnosis captures for 40 s alongside its D-Bus watch.
- **Classification.** `hcilog.py` reads the btsnoop for a connection request, a link key reply or negative reply, encryption, an L2CAP security block and an authentication failure. That separates O2 (cable pairing) from O3 (SSP gate), and confirms O1 and O4.
- **In the report bundle,** the capture is added as `hci.btsnoop` only when the user keeps the adapter address. The raw packets contain it, so a redacted bundle leaves the capture out.

### 5. Write allowlist additions (helper)

| Path | Who | Condition |
|---|---|---|
| `/run/keepsake-helper/` (socket, token) | Helper | Always while it runs |
| `/var/lib/bluetooth/<ADAPTER>/<DEVICE>/info` and `info.keepsake-<time>` backups | Helper | A user's cable pairing or restore, for a device with a rule |
| The helper's own settings folder (`state.json`, the SSP gate's adapters) | Helper | Always |

## Consequences

- **Principles.**
  - P8 holds for Keepsake: only the helper runs as root, with a narrow interface.
  - P9 holds: no binary. MGMT and the monitor channel are spoken directly.
- **Faults and evidence.** Reconnect help now covers F1 to F3 on the device, and the diagnosis has the HCI evidence.
- **ADR-0075** tier 1 is accepted, with option B.
- **Threat model:** T150 to T153. **Assumptions:** A229 to A233. **Device run:** steps 35 to 38.
- **Still to verify on the device:**
  - that Keepsake's backend and the helper share Decky's executable (A229);
  - whether SSP off works with the adapter powered (A231);
  - that Decky installs a second plugin from this zip layout (A232).
- **Not built yet.** The other jobs the helper will carry (fans, power limits, RGB, controller settings, LED) come in R24, each with its own allow-list entries in this ADR.
