# Slice 22 report: Installer II

Branch `slice/22-installer-2`, stacked on `slice/21-installer-1` (#19). v2 spec slice 22. Decisions: ADR-0027. Network mount spike: `docs/research/network-mount-spike.md`.

## What changed

- **CD drive emulation** (`installer/cdrom.py`): for an ISO install waiting for its installer, the disc gets the first free letter from D: in the installer's own prefix. That means `dosdevices` links to the mount point and the loop device, plus the drive type `cdrom` in `system.reg` through the registry engine (backup, atomic write, read-back). It is refused before Proton has created the prefix and while the installer runs. Keepsake's own links are removed when the job ends.
- **Already-mounted network sources:**
  - `/proc/self/mounts` is read, so mounted network shares (CIFS, NFS, gvfs, kio-fuse, sshfs, rclone) and the user's removable drives appear on the Install page as places to browse from;
  - sources and library folders outside the home folder go into `STEAM_COMPAT_MOUNTS`;
  - paths Steam launch options cannot carry are refused before anything is mounted.
- **SteamGridDB artwork** (`installer/artwork.py`): built and tested, but downloads are **off** until Peter approves the image host (see below). The key is a backend secret, sent only to the API host.
- **Executor:** new `remove-shortcut` and `set-artwork` operations, plus `steam_ops_file` for staged images of a claimed operation.
- **Hand-off:**
  - Core publishes `game_installed` on the lifecycle bus when a retarget finishes, and announces it once;
  - "Sync this game's saves" finds the new shortcut in the Games list and switches its sync on through the Saves callable.
- **Clean-up and health:**
  - "Remove the installer shortcut" for an install that stopped or was cancelled;
  - health checks for discs left mounted, installer shortcuts left behind and Steam changes still waiting.
- **Spike:** `scripts/network_mount_probe.py` (read-only, prints no names), with the options and a recommendation in the spike document.
- **Docs:**
  - ADR-0027;
  - threat model: T50 updated, new T75 to T78;
  - assumptions A135 to A141;
  - README, CHANGELOG 0.22.0, and the module doc.

## Needs Peter (escalation)

**Update, 16 November 2026:** Peter decided item 1 ("pick the best option"), so the recommendation below was taken and artwork is on. Item 2 still waits for the probe results.

1. **SteamGridDB image host `cdn2.steamgriddb.com`.** The spec allowlists the `www.steamgriddb.com` API, but SteamGridDB serves its images from `cdn2.steamgriddb.com`. That host is outside v2 section 6.2, so adding it is an escalation item.
   - Recommendation: approve it, under the same conditions as the API host (only with a user key and while the Installer is on; the key is never sent to it).
   - Approval is one constant, `artwork.IMAGE_HOST_APPROVED`, plus the CLAUDE.md allowlist line.
2. **Network mounting:** choose between options B (`gio`, needs a System Binary Register entry) and C (a vendored pure-Python SMB client, needs a licence check) after the probe results. Option A is built.

## Tests

- `tests/test_installer.py`: 21 passed and 1 skipped (`posix`: real symlinks, runs on the device). The 12 new tests cover:
  - the CD drive: links, drive type, backups, refusals, idempotence, leaving others' links alone, and clean-up;
  - mounts: network and removable sources, and the compat mounts;
  - shortcut removal;
  - health;
  - artwork: off by default, the flow when approved, the key going only to the API host, non-images refused, and validation;
  - the app hand-off, with a single `game_installed` announcement.
- Existing tests updated for the new behaviour: the ISO launch options for a disc inside home, and the app tests now keep their source inside the device home.
- Re-run because they cover touched code: `test_modules`, `test_backends`, `test_app_backends`, `test_app_ux`, `test_lifecycle`, `test_app`: 75 passed, 1 skipped.
- Mutation checks: 25 guards broken one at a time.
  - 21 were caught on the first run.
  - 3 were caught after new tests: disc idempotence, changed-link protection and the single announcement.
  - 1 was removed rather than tested: a `..` check that the file name pattern already made redundant.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan).

## Known gaps

- Games that need the disc while playing are not covered, because the disc is released when the install ends.
- Artwork is on since Peter approved the image host on 16 November 2026.
- There is no Replication hand-off button yet. Replication arrives in slices 17 to 20 and can subscribe to `game_installed`.
- Everything touching Wine, Proton, Steam and udisks is unverified until the device checks: A135 to A141, plus slice 21's A70 to A76, A85 and A131 to A134.

## On-device checklist

1. Slice 21's checklist first (#19).
2. **Disc drive:** start an ISO install, then start and quit the installer shortcut once.
   - Press "Installer wants a disc drive" and start the installer again. The installer sees drive D: as a CD-ROM.
   - After Done or Cancel, `ls -l ~/.local/share/Steam/steamapps/compatdata/<appid>/pfx/dosdevices` shows no Keepsake link left.
3. **Network source:** open a NAS share in Dolphin in Desktop Mode, then return to Gaming Mode.
   - Install lists it, or it does not (note which).
   - Run the probe in both modes (spike runbook) and paste the output here.
4. **Library on the SD card:** use "Change folder" to choose a folder on the SD card. The installer can write there, which proves `STEAM_COMPAT_MOUNTS` works.
5. **Shortcut removal:** cancel an install after its shortcut was created and press "Remove the installer shortcut". The shortcut disappears from the library.
6. **Hand-off:** when an install is done, press "Sync this game's saves". The Games page opens with the game switched on.
7. **Health:** Settings, Modules, Installer shows the three new checks.
8. Run `pnpm run test:device`, which includes the real-symlink CD test.
