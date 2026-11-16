# Network mount spike (v2 slice 22)

Status: **options for Peter.** Nothing beyond option A is built. The research flagged automated SMB and NFS mounting as a spike, not a feature (replication research section 6.2), and it is an escalation item if it needs root or a binary.

## The question

Can the Installer reach an installer or ISO on a NAS from Gaming Mode, with no terminal, no root and no bundled binary?

## What slice 22 delivers (option A)

Keepsake reads `/proc/self/mounts` and offers shares that are **already mounted** as places to browse from. These are SMB and NFS kernel mounts, gvfs and kio-fuse mounts, sshfs and rclone mounts. A source outside the home folder is passed to the installer with `STEAM_COMPAT_MOUNTS`. Keepsake mounts nothing itself.

## Options

| | Option | How | Root or binary | Principles | Unknowns |
|---|---|---|---|---|---|
| A | Use what is already mounted (built) | The user opens the share once in Desktop Mode (Dolphin) or has an `fstab` entry | None | Meets all | Whether Desktop Mode kio-fuse or gvfs mounts survive the switch back to Gaming Mode. If they do not, A needs Desktop Mode each time. |
| B | `gio mount smb://...` from the plugin | gvfs, with credentials passed on stdin | System binary `gio` plus the gvfs daemons | Needs a System Binary Register entry (escalation, ADR-0018). P7 holds only if gvfs runs in the Gaming Mode session. | Is `gio` on SteamOS and Bazzite? Is there a session bus in the plugin process? Where do the mounts appear? |
| C | Vendored pure-Python SMB client, copy to staging | For example pysmb (licence to confirm). Copies the chosen folder or ISO to local staging, then installs from there | None | Meets P8 and P9 if the library is pure Python and its licence allows it. Needs free space for a full copy. | Licence (escalation if unconfirmed), SMB3 support, speed over Wi-Fi 6E, NFS not covered |
| D | `fstab` entry with the `user` option | One-time root edit | Root, once | Breaks "no terminal" (P7) | |
| E | rclone or another FUSE tool | | Bundled binary | Breaks P9. Rejected. | |
| F | udisks | | | udisks does not mount network filesystems | |

## Recommendation

1. **Keep A** (built) and measure with `scripts/network_mount_probe.py`, once in each mode on both devices.
2. If the probe shows `gio` and gvfs on both systems with a session bus in Gaming Mode, choose **B**. This needs your approval of a register entry.
3. Otherwise choose **C** for SMB only, after a licence check of the chosen library. This needs your approval as a vendored dependency.

Either way the result goes into a new ADR before anything is built.

## Device runbook

1. Desktop Mode: open the NAS share in Dolphin, then run `ssh deck@<device> python3 - < scripts/network_mount_probe.py` from the laptop.
2. Switch to Gaming Mode and run it again. Open Keepsake, Install, and see whether the share is listed.
3. Repeat on the second device (Bazzite if available).

The probe prints filesystem types and folder depth only, never host, share or user names, so its output can go into the slice report.
