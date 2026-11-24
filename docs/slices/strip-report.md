# The strip (v0.61.0, ADR-0098)

## What changed

Haversack now installs non-Steam games and moves them between handhelds, and nothing else (Peter's direction of 24 November 2026).

- **Kept:** Core, Installer (ISO, folder, mounted shares, SMB, WebDAV, web server, discs, the queue, artwork for installed games, any non-Steam game and streaming tiles) and Replication (pairing, send, get, keep in step, emulators).
- **Deleted:** Saves and everything under it (sync, snapshots, restore, conflicts, history, retention, freeze, the launch gate, playtime, identity, import and export, the cloud stores and sign-in), Advisor, Desktop and the tray, the PC host and package, Device, Looks and the root helper. About 270 files and 50,000 lines. The `full` branch keeps v0.60.0.
- **New:**
  - **Games and devices, Games** (`src/pages/GamesList.tsx`): the device's non-Steam games, each opening Send, Keep in step and Artwork.
  - **Settings, General, Game database:** the Ludusavi manifest's status, an Update now button and its MIT credit.
  - `leftovers.py`: removes v0.60.0's two desktop entries on start, only when they carry Haversack's marker.
- **Changed:**
  - Replication is on by default; its listener is still off until the user switches it on.
  - Steam's start and exit events go to the bus for every game, and open and close update sessions, so updates still wait while a game runs.
  - The menu has four sections, and old addresses redirect.
  - The credential store keeps only the SteamGridDB key and network-location passwords.
- **Releases:** one zip under four names, the SBOM and the signed sums. The packager never ships `client_secrets.json`; publishing no longer needs it.
- **Docs:** the user guide is rewritten for the two jobs, with a "going back to 0.60.0" section. Pages for removed features are deleted, and the Help is rebuilt. Also updated: README, CLAUDE.md, SECURITY.md, the third-party notices, the release guide, the module docs, the threat model (T169), assumptions (A251, A252), the plan and the device run.

## Test results

- Gate (`python scripts/check.py`): all checks passed (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan, docs, help).
- **Whole remaining suite, run once:** the rewrite of `app.py` touches the module nearly every test imports.
  - First run: 1652 passed, 16 skipped, 5 failed, all in Replication.
  - Two failures came from Replication now being on by default: a stale assertion, and a real bug. The bug: Replication starts before the device is named and kept "Unnamed device" until a restart. Fixed: a rename now updates the running link's identity.
  - The other three passed on rerun with the fix (27 passed). One had reported "the battery is below 30 percent", which looks like the laptop's own battery reaching a transfer hold; worth isolating later.
- **Mutation check** (`tmp/mutate.py`): 11 mutations, all caught.
  - The leftovers marker, removal and start call.
  - The game event's app ID, handled count and session open and close.
  - The packager's secrets exclusion.
  - The shortcut registry's duplicate check.
  - The rename reaching the running link.

## Known gaps

- `src/backend.ts` still declares some types only removed pages used. They are harmless; pruning them was left for later.
- **Not recovered on start:** a v0.60.0 restore or freeze interrupted by a crash, followed straight by this update (ADR-0098, T169). Reinstalling v0.60.0 recovers it.
- PCs on the old PC package stay on 0.60.0.
- The `protondb-index` release is no longer refreshed.

## On-device checklist

The steps are in `docs/device-run.md` (v0.61.0):
- the update and its What's new;
- the four sections;
- no tray in Desktop Mode;
- the device checks;
- installing from an ISO and a share, with artwork;
- updates waiting for a running game;
- pairing;
- sending a game with its saves;
- an update that keeps the receiver's newer save;
- Stop and remove, emulators and Get a game;
- going back to 0.60.0 and forward again.
