# Replication: your devices

Replication links your own devices directly: handhelds, Linux PCs and Windows PCs. It pairs them, then sends non-Steam games between them: a game you set up on one handheld appears on the other, playable, with the same Proton version, artwork and launch options.

```mermaid
flowchart LR
    A[Handheld A] -- "direct, encrypted, uncompressed" --> B[Handheld B]
    A -- "direct" --> P[PC]
    B -- "direct" --> P
    A -. "never" .-> C[(Cloud storage)]
```

## Switch it on

1. Open Keepsake, then Settings, then **Modules**, and switch on **Replication**. A **Devices** tab appears. On a PC, it is the **Devices** page.
2. On **Devices**, switch on **Let other devices reach this one**. Until you do, nothing on your network can connect to this device.

Do this on each device you want to link. You need no SSH, keys or accounts.

## Pair two devices

1. On the first device, press **Let a device pair with this one**. It accepts pairing for two minutes.
2. On the second device, press **Find devices** and choose the first one. If it is not listed, for example over a VPN, type its address under **Pair by address**.
3. Both screens show a 6-digit code. Check that they are the same, and press **The codes match** on both.
   - If the codes differ, press **They differ**. Another device on the network may be trying to listen in, and nothing is paired.

Each device you pair is linked to every other one you pair, so a group such as two handhelds and a PC works.

## Paired devices

- **Check** connects and shows the round trip. Over a VPN it says when the link looks slow, which can mean the VPN is relaying it.
- **Wake** sends a Wake-on-LAN signal. It usually wakes a PC on a cable. A handheld asleep on Wi-Fi usually cannot be woken this way.
- **Remove** forgets a device. It can no longer connect until you pair it again.

## Send a game

1. On the device that has the game, open it in Keepsake's **Games** and press **Send to <device>**. Keepsake checks every file first, which takes a few minutes for a large game. If Saves syncs the game, the newest saves go first.
2. On the other device, open **Devices**. Under **Games between devices**, press **Accept**.
   - If that device lacks the game's compatibility tool (a GE-Proton version, for example), Keepsake offers to copy it too. Steam finds a copied tool after a restart.
   - Launch options that only make sense on the first device, such as a mounted disc, stay behind, and Keepsake lists them.
3. Keepsake copies the game, adds it to Steam with the same name, program, launch options, Proton version and artwork, and says when it is ready. If Saves synced the game, it carries on with the same saves, with no conflict.
4. **Clear from this list** tidies a finished game away. The game stays.

**Stop and remove** on a game being received deletes everything that copy made on this device: its folder, its prefix, a copied tool and its Steam shortcut. Nothing else is touched.

On the sending device, **Withdraw** an offer once the game has arrived, to free the space Keepsake keeps for it.

## Firewalls

Keepsake never changes your firewall. Settings, **Health** says what to allow, if anything: TCP 47110 and UDP 5353.
- On Windows, allow Python on private networks when Windows asks.
- On Bazzite, the default settings already allow it.

## Promises

- **Device to device only.** Game files go straight between your own devices, on your home network or over your own VPN (WireGuard, Tailscale or ZeroTier). They never go through cloud storage, or through any server or relay run by Keepsake.
- **Paired devices only.** Every connection is encrypted with a key only your two devices know. Devices you have not paired are refused.
- **Exact copies.** Files arrive exactly as they were, with their sizes, permissions, times and links. Nothing is compressed, at any layer.
- **Pause and resume.** You can pause a transfer and resume it later. It also carries on by itself after errors, a lost network, the other device going away and coming back, a restart, sleep, or a power cut. Nothing already checked is sent twice.
- **Stop means clean.** **Stop and remove**, which asks you first, deletes everything the transfer made: partial files, the shortcut, the prefix and any tool copy. Your existing install is never touched.
- **Room to spare.** Keepsake checks there is enough free space before it starts, and keeps the device awake while it copies.
- **Honest speed.** It shows the speed, time left and progress for each file, and says plainly when a link looks slow.
- **Saves stay with Saves.** Replication never touches save files. Keepsake's save sync looks after them.
