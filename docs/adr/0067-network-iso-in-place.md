# ADR-0067: Install straight from a network ISO, copying only as a fallback

- Status: accepted. Peter approved `fusermount3` in the System Binary Register on 22 November 2026, so the in-place mount for shares that are not mounted is on from v0.45.0 (`netfuse.FUSERMOUNT_APPROVED`). Peter's request of 21 November 2026, decided under ADR-0037.
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

An ISO on an SMB, WebDAV or HTTP location is downloaded to staging before `udisksctl loop-setup` opens it (ADR-0033). That needs the whole ISO's size free on the device and a full copy's time. Peter wants installs straight from the ISO where possible, within the principles, with copy-to-staging as the automatic fallback, and the same for shares that are already mounted (option A). He also wants the SSH `--loop-test` step replaced by a Device check.

udisks' `LoopSetup` takes a file descriptor (ADR-0033, A158). So the ISO only has to look like a local file to the user. udisksctl opens it and udisks attaches the loop device to that descriptor.

## Options for shares that are not mounted

| Route | What it needs | Gaming Mode? | Verdict |
|---|---|---|---|
| gvfs: `gio mount smb://...`, then the `gvfsd-fuse` path | `gio` and the gvfs daemons, a session D-Bus, the password on stdin; SMB, WebDAV and SFTP only | Unlikely: gvfs is a desktop session service | Rejected: several binaries, session facts we cannot rely on |
| kio-fuse: D-Bus `org.kde.KIOFuse.VFS.mountUrl` | KDE's KIO workers and kio-fuse, a session bus, KDE's password dialog for credentials | No: there is no KDE session in Gaming Mode | Rejected |
| Keepsake's own FUSE file system, mounted in a private user namespace | `ctypes` for `mount(2)` (unproven in Decky's frozen Python, ADR-0030), unprivileged user namespaces (off on some hardened kernels), and udisks handed the descriptor from inside the namespace | Yes, if all hold | Rejected for now: too many unverified parts for something that deletes nothing but must never wedge an install |
| **Keepsake's own read-only FUSE file system, mounted by `fusermount3`** | `fusermount3`, the setuid helper that ships with libfuse 3 so users can mount FUSE without root. Flatpak's document portal and AppImages use it, so it is expected on both SteamOS and Bazzite (A207). `/dev/fuse` open to the user. | Yes: no session bus, no desktop | **Chosen**, once approved |

## Decision

1. **`keepsake/installer/netfuse.py`, pure Python.** It is a one-file, read-only FUSE file system speaking the kernel protocol (`linux/fuse.h`, 7.31 replies) over `/dev/fuse`:
   - it answers lookup, getattr, open, read, readdir, statfs, access and release, and `ENOSYS` for everything else;
   - opening for writing gets `EROFS`;
   - the file is the chosen ISO, mode `0400`, in a `0500` folder under Keepsake's runtime folder.
2. **Reads become range reads** on the share, through the existing code, so every ADR-0033 and ADR-0034 rule applies:
   - `SmbRange`: pysmb `retrieveFileFromOffset` over one connection, reconnecting once;
   - `HttpRange`: HTTP `Range` requests for web servers and WebDAV. A server that does not answer `206` with a matching `Content-Range` is not used in place.

   Reads are cached in 4 MiB blocks, at most 16 (64 MiB of memory), and the next block is read ahead. Range reads run on up to four threads.
3. **The mount.** `fusermount3 -o ro,nosuid,nodev,noexec,fsname=keepsake,subtype=keepsake,auto_unmount -- <runtime>/installer/netmount/<id>`:
   - the descriptor is received over a socket pair (`_FUSE_COMMFD`), as libfuse does;
   - `auto_unmount` makes `fusermount3` unmount if Keepsake stops for any reason;
   - the mount is released with the install's disc (`Installer.on_released`), and `fusermount3 -u -z` is called on close.
4. **Gate.** The `fusermount3` mount is in, but `netfuse.FUSERMOUNT_APPROVED` stays `False` until Peter approves the register entry. Until then nothing mounts and every network ISO is copied as before.
5. **Order for shares that are not mounted** (once approved): try in place, and if anything fails, close the mount and copy as today. The things that can fail are the mount, a server without ranges, a loop setup refused on the FUSE file, or no `/dev/fuse`. In place is attempted only when `fusermount3` is present and `/dev/fuse` is usable.
6. **Already-mounted shares (option A):**
   - an ISO on a network or FUSE file system (from `/proc/self/mounts`: `cifs`, `smb3`, `nfs`, `nfs4`, `9p`, `sshfs`, `davfs`, any `fuse.*`) is opened in place first, as before;
   - if udisks refuses it, the Installer raises `InPlaceFailed` and the app copies the ISO to staging in the background (progress, Stop, free-space check), then installs from the copy;
   - a local ISO that fails is not copied: that is a real error.

   No new binary is needed for this part.
7. **Device check "Network ISO in place".** It replaces `network_mount_probe.py --loop-test`, which is removed. It reports:
   - whether `udisksctl` and `fusermount3` are present, `/dev/fuse` is usable, and in-place mounting is ready or waiting for approval;
   - the result of a read-only loop setup and delete on the first ISO it finds on a mounted network share, by file system type only.

   It passes when that ISO opens in place, warns when it does not (Keepsake then copies), and is skipped when no ISO is on a mounted share.

## Register entry requested (ADR-0018)

| Binary | Module | Use | Why |
|---|---|---|---|
| `fusermount3` | Installer | Mount Keepsake's own one-file, read-only FUSE file system for a network ISO, with `ro,nosuid,nodev,noexec,auto_unmount`, and unmount it (`-u -z`). Fixed arguments, no shell, the mount point under Keepsake's runtime folder. | A user cannot call `mount(2)` for FUSE without root; `fusermount3` is libfuse's setuid helper made for exactly this. It is the only way to use a network ISO in place with no root, no desktop session and no bundled binary. |

Peter's approval flips `FUSERMOUNT_APPROVED` in its own change and records the entry in ADR-0018 with the device verification (A207).

## Consequences

- Until approval: option A's copy fallback and the Device check are live, and network ISOs are copied as before.
- After approval: an install from a share needs no staging space. It does need the share to stay reachable while the installer runs. If the share drops, reads fail (`EIO`), the installer reports an error, and the next try can copy instead.
- T126 in `docs/threat-model.md`; A207 in `docs/assumptions.md`; A158 is answered by the Device check.
