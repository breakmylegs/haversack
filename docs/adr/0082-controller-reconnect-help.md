# ADR-0082: Controller reconnect help

- Status: accepted (Peter's requests of 22 November 2026, the clone DualShock 4 fix and its generic addendum, decided under ADR-0037)
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

Some non-official and clone Bluetooth Classic (BR/EDR) controllers pair once and then never reconnect with their normal button on SteamOS. Peter's research report traced five faults to BlueZ issues 2678, 2679 and 2380:

| Fault | What happens |
|---|---|
| F1 | The pairing is never committed on the controller, so it pages its old host |
| F2 | The controller opens HID before encryption is up and is refused (SSP timing race) |
| F3 | BlueZ's cable pairing gives the controller an all-zero key |
| F4 | BlueZ browses SDP during the reconnect and the controller hangs up |
| F5 | Host and controller open HID at the same moment |

They show as outcomes O1 to O7. Peter first asked for a DualShock 4 fix, then replaced its scope with a generic one: any BR/EDR controller, with the DualShock 4 as the first family that has a cable pairing protocol. Bluetooth LE is out of scope, because the SSP gate and cable pairing only affect BR/EDR.

The work comes in two releases. This one holds the parts that need no root. The root helper (ADR-0075 tier 1, approved) brings the HCI capture, cable pairing and the SSP gate in R23.

Facts checked on 22 November 2026 (A225 to A228):
- **BlueZ versions.** SteamOS 3.9.5 is stable; its BlueZ version is not published. The 3.9.2 beta shipped 5.87 (SteamOS issue 2886). Fedora 45, which Bazzite stable 45.20261117 is built on, ships 5.88. Bazzite's own build was not confirmed.
- **BlueZ PR 2858** (a `SecureSimplePairing` option in `main.conf`) is open, unmerged and in no release. The SSP gate is still needed.
- **Steam's Game Mode agent and the sixaxis prompt.** No source shows Steam's agent answering the sixaxis "Authorize service" prompt. Community reports point to Desktop Mode only. Keepsake never answers it either.
- **hidraw access.** Valve's `60-steam-input.rules` gives the signed-in user access (`MODE="0660"`, `TAG+="uaccess"`) to Sony 054C:05C4 and 09CC over USB and Bluetooth. A clone with other IDs gets no access, and reading it needs the helper.
- **The Decky root flag** is `"root"`; `"_root"` is the template's disabled placeholder (decky-loader `sandboxed_plugin.py`). This is for R23. Keepsake's own `plugin.json` stays without it (P8).

## Decision

### 1. One generic feature, "Reconnect help"

It lives under **Device**, **Reconnect help**, with a quick menu entry, and belongs to the Device module.
- **Every paired device is listed**, from BlueZ over the system bus, with:
  - its name, class, modalias and adapter;
  - whether it is Classic or LE;
  - its last diagnosis;
  - an "address not from a registered manufacturer" flag.
- **Help is turned on per device.** A rule is keyed by **adapter address plus device address**, because bonds are per adapter. A device with no rule is only ever read.
- **The adapter can be chosen** when there is more than one.

### 2. The registered-manufacturer flag

A device is flagged when the first byte of its address has the group bit (0x01) or the locally administered bit (0x02) set.
- IEEE assigns MA-L, MA-M and MA-S prefixes with both bits clear, so such an address cannot come from a registered manufacturer.
- The report's "first octet odd" covers only the group bit; this rule covers both bits.
- The flag is information for the user only. Nothing acts on it, and nothing infers identity from a name, class or modalias, because clones copy them.

### 3. No-root modules (this release)

- **Passive detection: suggest, never act.**
  - A watcher thread holds its own system bus connection.
  - It notes any device that connects and drops within 5 seconds. The screen then asks "may need help, run a diagnosis?".
  - It reads nothing more and does nothing to the device.
- **Pair and commit (Design B).**
  - For a helped device with the option on (the default), when BlueZ reports Paired, Keepsake calls `ConnectProfile(HID)` at once.
  - It acts once per pairing, and never if the device is already connected (F5).
- **Reconnect (Design E).**
  - After a user action: discovery for at most 30 seconds, with a BR/EDR filter.
  - Discovery stops the moment the device is seen, and then `ConnectProfile(HID)` runs on the existing bond.
  - Discovery is stopped on every path, and BlueZ also ends it when Keepsake's connection closes.
  - It never removes a device.
- **Diagnosis.**
  - The screen says: turn the controller off, wait 10 seconds, select Start and press the controller's button once.
  - Keepsake watches BlueZ for 45 seconds, stopping early after one attempt, then reads bluetoothd's and the kernel's journal lines for that window.
  - It classifies the result as O1, O2, O4, O5, O6 or O7, plus "reconnected", "stores a different host" and "stores this handheld", and recommends a step.
  - O2 and O3 cannot be told apart without the HCI capture, so they share "the handshake fails" until R23.
- **Read stored host over USB.**
  - Through a cable pairing provider (section 4).
  - Only a controller whose address read over USB matches the chosen device counts. Any other is reported as a mismatch and left alone.
  - The screen is told only whether the controller stores this handheld.
- **Full report mode.** An off-by-default DualShock 4 option: Keepsake reads feature report 0x02 when the helped pad connects.
- **Export report bundle.**
  - A zip of `report.json` (device details, bond state, events, outcome) and `journal.txt`, for sharing on BlueZ or community issues.
  - This handheld's adapter address is replaced. The API can keep it if asked, but the screen always redacts.
  - It is separate from the Device checks export. The HCI capture joins the bundle in R23.

### 4. Cable pairing as providers

Each controller family is a `Provider` with:
- `matches(usb_node)`;
- `read_identity()`, giving the controller's own address and its stored host;
- `write_pairing(host, key)`, `commit()` and `verify()`;
- `key_type`, the BlueZ key type.

The provider is chosen from the USB vendor and product, and identity is then confirmed by address. The providers:
- **DualShock 4** (054C:05C4 and 09CC, which clones copy), using feature reports 0x12, 0x13 and 0x14, with BlueZ key type 4. This release only reads with it. The write steps are defined and tested now, so that R23's helper uses the same code.
- **DualShock 3 and DualSense** are candidates, built only after their formats are verified (DS3 against BlueZ's `plugins/sixaxis.c`).
- **Any other family** shows "Cable pairing is not supported for this controller".

R23 adds the BlueZ steps as root:
- stop bluetoothd;
- back up the device's `info` file and change only `[LinkKey]` and `Trusted`, keeping every other line byte for byte;
- write it atomically, root-owned, mode 0600;
- start bluetoothd after a warning and confirmation, never during a game;
- offer "Restore backup";
- an advanced key byte order toggle;
- re-verify against the sixaxis zero-key gotcha;
- never `RemoveDevice`.

### 5. Safety

- **One gate.** Every action passes it: the rule for exactly this adapter and device. Mutation tests prove each check (19 mutations, all caught).
- **Dry run.** A switch logs what would be done, without scanning or connecting.
- **An append-only action log.** `reconnect-actions.log` in the settings folder, timestamped, with masked addresses.
- **No blocking.**
  - Every blocking step runs in a worker thread.
  - `journalctl` runs with a 5 second timeout and a line limit.
  - There is no continuous discovery, no connect polling, no agent, and no setting changed.
- **No `/etc` writes.** Files go only to the settings folder: the rules, the action log and the report bundles.
- **The desktop tray is untouched.**

### 6. A new System Binary Register entry: `journalctl`

`journalctl` is part of systemd on both SteamOS and Bazzite. systemd gives the `wheel` group read access to the journal, and the default user is in `wheel` on both. It is used read-only, with `--since` and `-n`, for bluetoothd and the kernel.
- When it is missing or unreadable, the diagnosis says "journal unavailable" and still classifies from D-Bus.
- The Device check "Controller reconnect help" verifies it on each device (A227).

## Consequences

- **What it fixes without root.** It can fix F1 (pair and commit) and work round any fault (Reconnect after pairing mode). It can diagnose most outcomes. The lasting fixes for F2 and F3 wait for R23.
- **No new network endpoint, OAuth scope, root, or bundled binary.** One register entry is added (`journalctl`).
- **The quick menu.** It shows a Reconnect button per helped, disconnected device, and a note when a device may need help. When the quick menu shortcuts (R25) land, these become registered shortcuts.
- **Threat model:** T147 to T149.
- **Device run:** steps 31 to 34. The checks run inside the plugin (the diagnosis and Device checks), not over SSH.
- **Known gap.** The desktop app does not show reconnect help yet. It is Gaming Mode first (P7), and the desktop page follows with R23.
