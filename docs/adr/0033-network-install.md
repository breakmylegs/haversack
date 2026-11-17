# ADR-0033: Installing from a network location that is not mounted

- Status: accepted for HTTP and HTTPS (built). SMB recommended through a vendored pure-Python client, to build next. NFS, WebDAV and SFTP as below. Peter's owner decision, 16 November 2026.
- Date: 17 November 2026
- Deciders: Peter (owner)
- Supersedes: the recommendation in `docs/research/network-mount-spike.md` (option A, already mounted shares, stays)

## Context

The Installer (ADR-0026, ADR-0027) installs from an ISO or a folder that the device can already see. Option A of the network mount spike lists shares that are already mounted. Peter wants to install from a NAS or web server that is *not* mounted, from Gaming Mode, within P7 (no terminal, no Desktop Mode step) and P9 (no bundled binary; system binaries only through the register).

A useful fact for every route: the Installer opens ISOs with `udisksctl loop-setup`. udisks' `LoopSetup` method takes an open **file descriptor**, not a path (`LoopSetup (IN h fd, IN a{sv} options, OUT o resulting_device)`, [UDisks2 Manager API](https://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Manager.html)). `udisksctl` opens the file as the calling user and passes the descriptor, so the root daemon never needs to reach the path. A FUSE mount that only the user can read should therefore still work. This is **unverified** until the probe's loop test runs on a device (A158). Wherever a route below says "use in place", the fallback is to copy to staging.

## Options per protocol

| Protocol | Route | Binary or root | Use the ISO in place, or copy? | Verdict |
|---|---|---|---|---|
| HTTP, HTTPS | Python stdlib `urllib`, streamed to staging, resumed with `Range` | None | Copy: HTTP has no file system. | **Built.** |
| SMB 2 | Vendored **pysmb** (zlib/libpng licence, pure Python, needs `pyasn1`, BSD-2-Clause; ships its own MD4, so it does not need OpenSSL's legacy provider). It supports SMB1 and SMB2 only. | None | Copy: there is no mount. Browsing lists the share directly. | **Recommended, next.** Needs a vendored dependency pinned with hashes (P9 allows this), and no register entry. |
| SMB 3 | **smbprotocol** (MIT) | Needs `cryptography`, which is a compiled extension and breaks P9 | | Rejected. |
| SMB through gvfs | `gio mount smb://...`, then the gvfsd-fuse path under `/run/user/<uid>/gvfs/` | The `gio` binary plus the gvfs daemons, and a session D-Bus in the plugin process | In place, if loop-setup works on FUSE (A158) | Possible fallback. Needs a register entry (escalation, ADR-0018) and a probe result showing gvfs in Gaming Mode. The password has to go in on stdin. |
| SMB through kio-fuse | D-Bus `org.kde.KIOFuse` `/org/kde/KIOFuse` `org.kde.KIOFuse.VFS.mountUrl(s) -> s` ([kio-fuse README](https://invent.kde.org/system/kio-fuse/-/blob/master/README.md)) | No binary is run, but the session bus is needed, and KDE's KIO workers must be installed | In place (A158) | Possible on SteamOS Desktop. Unlikely in Gaming Mode, where there is no KDE session and no password dialog. The probe checks it. It would also need a pure-Python D-Bus client or the `gdbus` or `busctl` binary, which is a register entry. |
| NFS | Kernel mount needs root or an `fstab` `user` entry. libnfs is C, and there is no maintained pure-Python NFSv3 or NFSv4 client. | Root, or a bundled binary | | **Not offered.** Honest assessment: NFS shares work only through option A (mounted by `fstab` or Desktop Mode). |
| WebDAV | Python stdlib, using the same `PROPFIND` code as the WebDAV store (`store/httpcall.py`) | None | Copy | Easy follow-on to HTTP: browsing through `PROPFIND Depth: 1`, then download like HTTP. Needs `xml`, which Decky's Python may lack (ADR-0030). If it is missing, it says so and falls back to HTTP links. |
| SFTP | paramiko or asyncssh need `cryptography` (P9). The `sftp` binary would need a register entry and key handling. | Binary | | Not offered now. gvfs `sftp://` comes with the gvfs route if that is ever approved. |

## Decision

1. **HTTP and HTTPS are built now** (`keepsake/installer/remote.py`):
   - **Download:** one file (`.iso`) streamed into the Installer's staging folder (`<runtime>/installer/staging/net/`). A `.part` file grows and is renamed when complete.
   - **Resume:** a dropped connection resumes with `Range: bytes=N-` (a `206` with a matching `Content-Range`). A server that ignores `Range` restarts from zero.
   - **Checks:** the final size must match `Content-Length`. An optional SHA-256 entered by the user must match.
   - **Progress:** bytes, total, rate and a cancel between chunks. Cancel deletes the partial file.
   - **Clean-up:** the staged ISO is deleted when the install job finishes, is cancelled or fails, and when preparing the install fails. Whenever the Installer module starts, it deletes any download that no active install uses, including partial files.
   - **Browsing:** the listing pages that NAS and web servers generate (`autoindex` style) are read for links one level down, without following them, then shown as folders and `.iso` files.
2. **SMB is next**, as vendored pysmb. It is a separate change because the vendoring, hashes and packaging need their own review. It does not depend on the probe, because it mounts nothing. The gvfs and kio-fuse routes stay open, but not chosen: they need register entries and Gaming Mode session facts that only the probe can show.
3. **Option A stays.** Shares that are already mounted are still offered.

## Terms for user-entered addresses (Peter approves user-entered locations on these terms)

**Endpoint allowlist** (proposed addition to build prompt v2 section 6.2):
- Only the host the user typed, for one download or one browse.
- Only while the Installer module is on.
- Only after the user presses Browse or Download.

**Rules for that host:**
- **HTTPS** to any host.
- **Plain HTTP** only to a local address, checked before connecting:
  - RFC 1918 (`10/8`, `172.16/12`, `192.168/16`);
  - shared address space `100.64/10` (Tailscale and similar);
  - loopback, link-local and IPv6 `fc00::/7`.

  A name such as `nas.local` qualifies only if every address it resolves to is local. Python's own `is_private` is not used, because it also counts documentation ranges. If Decky's Python lacks `ipaddress`, plain HTTP is refused (ADR-0030). Over HTTP, Keepsake never sends a password. If the location has credentials, it must be HTTPS.
- **No credentials in the URL.** The user name and password are entered in separate fields and sent as HTTP Basic authentication over HTTPS only.

**Redirects:**
- **Followed by Keepsake itself**, at most 5.
- **Same host and scheme:** followed.
- **HTTPS to HTTP:** always refused.
- **A different host:** refused with "The server sent you to *other.host*". The user can confirm once to allow that one host for this download. Credentials are never sent to the new host.

**Limits:**
- **Size cap:** 128 GiB per file, and the download must also fit in free space.
- **Low-space warning:** if `Content-Length` plus 2 GiB is more than the free space, the user is warned before starting and the download is refused. With no `Content-Length`, the download stops when free space falls under 2 GiB.
- **Timeouts:** 20 s to connect and 60 s between bytes. Up to 5 resumes, then it fails with a retry button.
- **Listing pages:** at most 2 MiB and 5,000 entries.

**Storage:**
- **Locations:** a remembered location (protocol, address, folder, user name) goes in `netlocations.json` (mode 0600) in the settings folder.
- **Passwords:** in the CredentialStore, never returned to the page, never logged (`redact.py` already masks `password`).
- **Forgetting** a location deletes both.

**DNS:** a name is checked when it is resolved, and the connection resolves it again. A local DNS server could answer differently the second time. This matters only for plain HTTP without a password, which carries nothing secret, so it is accepted and recorded in T89.

**Threat model:** T88 (hostile or spoofed server), T89 (credentials leaking to another host or over plain HTTP), T90 (filling the disk). See `docs/threat-model.md`.

## Probe and device runbook

`scripts/network_mount_probe.py` now also reports:
- the session D-Bus;
- `gio`, `gvfsd` and `gvfsd-fuse`;
- whether the kio-fuse service is activatable (its D-Bus `.service` file);
- `/dev/fuse` access;
- free space in the Installer's staging folder.

With `--loop-test FILE` it also runs `udisksctl loop-setup --read-only` on a file you choose, which may be on a FUSE mount, reports whether it worked, then deletes the loop device. It prints no host, share or user names.

From the laptop (PowerShell), once in Gaming Mode and once in Desktop Mode:

```
Get-Content scripts\network_mount_probe.py | ssh deck@<device> "python3 -"
```

For the loop test, open the share in Dolphin (Desktop Mode) and copy the path of a small ISO on it, then:

```
Get-Content scripts\network_mount_probe.py | ssh deck@<device> "python3 - --loop-test '/run/user/1000/kio-fuse-XXXX/smb/.../small.iso'"
```

## Consequences

- HTTP installs need staging space for the whole ISO. The Installer page shows the free space.
- NFS stays "mount it yourself". The page says so plainly.
- SMB without a mount arrives with the pysmb change, and only for SMB2. SMB3-only servers, or servers that require encryption, are reported as such.
