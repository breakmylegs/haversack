# ADR-0027: Installer II implementation

- Status: accepted (slice 22, decided under Peter's delegation), **except point 4, which waits for Peter: the SteamGridDB image host is an escalation item**
- Date: 16 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 6.2, 6.3, 8.3 and 12 (slice 22); `docs/modules/installer.md`; ADR-0015, ADR-0018, ADR-0026

## Decision

1. **CD drive emulation.** On request ("Installer wants a disc drive"), for an ISO install waiting for its installer:
   - Keepsake links `<pfx>/dosdevices/<letter>:` to the disc's mount point and `<letter>::` to its loop device.
   - It sets `HKLM\Software\Wine\Drives` `"<letter>:"="cdrom"` in `system.reg` through the slice 11 registry engine (`set_values`), which keeps a backup, writes atomically and reads back.
   - The first free letter from D: is used. A link that is not Keepsake's is never touched.
   - It is refused until Proton has created the prefix (`system.reg` present), so Proton's first-run setup is never disturbed. It is also refused while the installer shortcut's processes run (P6 and P19).
   - The links are removed when the job ends. Only links still pointing where Keepsake set them are removed. The drive type value stays, which is harmless without a link.
   - Everything written is inside the installing shortcut's own prefix (write allowlist v2 section 6.3).
2. **Already-mounted network sources.** Keepsake reads `/proc/self/mounts` and offers:
   - network shares (CIFS, NFS, sshfs, rclone, gvfs, kio-fuse) mounted anywhere;
   - removable drives under `/run/media` or `/media`.

   These appear as places to browse from on the Install page. Keepsake mounts nothing itself (network mount spike, `docs/research/network-mount-spike.md`).
3. **Container visibility.** A source or library folder outside the user's home folder is passed to the installer shortcut as `STEAM_COMPAT_MOUNTS` (colon separated). Folders inside home are already visible and are left out. A path containing `:`, `"`, `%` or a newline is refused before anything is mounted or created, because Steam launch options cannot carry it. Retargeting clears the option, as before.
4. **SteamGridDB artwork** (user key, `www.steamgriddb.com` allowlisted, v2 section 6.2).
   - **What runs:** the search and the choice of the top image for each kind (capsule, header, hero and logo; PNG or JPEG only).
   - **Waiting for Peter:** the images are on `cdn2.steamgriddb.com`, which is not on the allowlist. Adding it is an escalation item, so `artwork.IMAGE_HOST_APPROVED` is `False`. The Install page hides the artwork controls until that is approved.
   - **When approved:** each image is checked by its first bytes, capped at 8 MB, staged in the runtime folder, and applied with a new `set-artwork` executor operation. The frontend calls `SetCustomArtworkForApp` with the staged file, read through `steam_ops_file` only while the operation is claimed. The staged file is deleted once Steam has it.
   - **Key handling:** the key is a backend secret (`steamgriddb.json`, mode 0600, never returned to the frontend). It is sent only to the API host, never to the image host.
5. **Shortcut removal.** "Remove the installer shortcut" queues a new `remove-shortcut` operation. It is offered only for a failed or cancelled install whose shortcut was never pointed at a game, and only once.
6. **Hand-off.** When the retarget finishes, Core publishes `game_installed` (`gameKey` null, with app ID and title) on the lifecycle bus. Replication can subscribe in slice 18 without reaching into the Installer. "Sync this game's saves" rescans, finds the new shortcut in the Games list and switches its sync on through the normal Saves callable. The user then sees its match in Games. Nothing is switched on without that button (P13, P14).
7. **Health** (module doc): discs still mounted after a job ended or after 12 hours; installer shortcuts left behind; Installer Steam operations waiting more than 15 minutes.

## Consequences

- Games that need the disc while playing (not only during the install) are not covered: the disc is released when the job ends. Mounting a disc for each launch is a possible later feature.
- Artwork does nothing until the image host is approved. When it is, the change is one constant and the allowlist entry in CLAUDE.md.
- Automated network mounting stays a spike. The options and a recommendation are in the spike document.
