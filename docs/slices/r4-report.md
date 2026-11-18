# R4 report: other launchers and emulators

Slice R4 of the post-v2 roadmap (ADR-0047), recorded in ADR-0051.

## What changed

- **`keepsake/launchers.py`** reads, without writing:
  - Heroic, native and Flatpak (GOG and Epic, Windows games), with each game's Wine or Proton prefix;
  - Lutris Wine games (`games/*.yml`, names from `pga.db`);
  - Bottles programs (`External_Programs`);
  - a small YAML reader for the simple files these write.
- **Emulators.** `data/emulators.json` profiles for RetroArch, Dolphin, PCSX2, DuckStation, PPSSPP, RPCS3 and Cemu. Each found emulator is one entry with the game key `emulator-<id>`. Its save folders become its custom paths, and save states are a toggle.
- **Save roots.** `resolve.logical_roots` handles plain Wine prefixes, with the Linux user in place of `steamuser`, and fails closed when the user is uncertain.
- **Running checks.** `procs.launcher_running` checks the Wine prefix (`WINEPREFIX` or `STEAM_COMPAT_DATA_PATH`), the emulator's `FLATPAK_ID`, or the program name.
- **Sync.**
  - **Idle pulls:** the idle pass brings in newer saves, or the first copy, for these games through the launch decision table.
  - **Fix:** a never-synced device with no files no longer raises an adoption conflict.
- **Interfaces.** Gaming Mode gains "Heroic, Lutris, Bottles" and "Emulators" filters, prefix text, save states on the game page, and "Show other launchers" in Settings. The launch gate shows only for Steam games and shortcuts. Desktop Games labels each kind.
- **Docs:** ADR-0051, T109, A184, A185, the user guide, the changelog and the plan.

## Test results

- `tests/test_launchers.py` (11 new): passed. It includes two devices syncing RetroArch saves, waiting while RetroArch runs.
- Covering tests passed, 237 in all: sync, sync plan, the app (UX, cloud, snapshots), lifecycle, settings, host, resolve, procs, discovery, freeze, R1 to R3. 5 POSIX-only skips.
- Mutation checks: 18 mutations, all killed after two tests were added.
- `tsc` and eslint clean.

## Known gaps

- Emulator folders other than RetroArch's, and the launcher formats, are unverified on a device (A184, A185).
- Heroic's own cloud sync cannot be detected, so a note says to use one or the other.
- Heroic on Windows, and Playnite, are out of scope.

## On-device checklist (Legion Go and Legion Go 2)

1. **RetroArch.** With EmuDeck's RetroArch on both devices, open Games, choose **Emulators** and turn on "Emulator saves: RetroArch" on both. Play a game with battery saves on one device and quit RetroArch. Press **Sync now** there. On the other device, press **Sync now** twice with RetroArch closed, and check that the save arrives.
2. **Running check.** Repeat with RetroArch open on the second device. Nothing should change until it is closed.
3. **Other emulators.** Check which of Dolphin, PCSX2, DuckStation, PPSSPP, RPCS3 and Cemu appear, and tell me any whose saves live somewhere else.
4. **Heroic or Lutris (if you use them).** Check that a Windows game appears under **Heroic, Lutris, Bottles**, that its save data matches, and that a save syncs.
