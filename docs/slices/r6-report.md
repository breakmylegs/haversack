# R6 report: Installer III

Slice R6 of the post-v2 roadmap (ADR-0047), recorded in ADR-0053.

## What changed

- **Disc sets.**
  - `files.sibling_discs` lists the other ISOs beside the first disc. `Installer.swap_disc` mounts the chosen one and repoints Keepsake's own drive links through `cdrom.repoint`, which checks every link first, then releases the old disc.
  - `STEAM_COMPAT_MOUNTS` now passes the folder discs are mounted under.
  - The Install page shows **Swap to <disc>**.
- **Queue.**
  - `start(..., queue=True)` adds a `queued` install. `promote` starts the oldest one when none is active; it runs after every finished install and at startup.
  - `resume` mounts the discs of active installs again after a restart, and fails an install whose disc moved.
  - The Install page queues a new install automatically while one is under way.
- **Runtime hints.** `files.find_runtimes` runs when the installer closes. The Install page lists what was found as guidance.
- **Docs:** ADR-0053, T111, A187, the user guide (installer), the changelog and the plan.

## Test results

- `tests/test_installer_3.py` (10 new): passed.
- Covering tests passed, 322 in all: the installer, network, SMB, WebDAV, remote and host tests. One expectation in `test_installer.py` changed on purpose: the runtime container now gets the mount folder.
- Mutation checks: 16 mutations, all killed after one test was tightened.
- `tsc` and eslint clean.

## Known gaps

- A real two-disc install, and a restart part-way through, are unverified until the device run (A187).

## On-device checklist (handheld)

1. **Two discs.** Put both ISOs of a two-disc game in one folder. Install from disc 1, add the disc drive, and run the installer. When it asks for disc 2, press **Swap to <disc 2>** and continue. Check that the install finishes and the game starts.
2. **Queue.** Start one install, then pick a second ISO or folder. It should say "queued". Cancel or finish the first, and check that the second starts by itself.
3. **Restart.** Restart the device in the middle of an ISO install, before its shortcut is made. Open Install and check that the install is still there and its disc is mounted again.
4. **Runtimes.** For a game that ships `_CommonRedist`, check that the runtimes are listed when you choose its program.
