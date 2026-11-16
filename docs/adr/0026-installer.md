# ADR-0026: Installer I implementation

- Status: accepted (slice 21, decided under Peter's delegation; the accepted risk in point 7 still needs Peter's sign-off, T51)
- Date: 16 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 8.3 and 12 (slice 21); ADR-0015, ADR-0018, ADR-0024; tandem research section 2.1

## Context

Slice 21 is taken ahead of slices 14 to 20 because they are blocked (14 and 15 on the licence audit sign-off, 17 to 20 on the slice 16 device results). The Installer depends only on Core (the module registry, the lifecycle bus, the state database and the Steam Operations Executor), so it can be built now. Advisor's compatibility tool recommendation is not available yet.

## Decision

1. **The community method, automated.** A temporary shortcut `Install: <Title>` runs the installer program in a new prefix of its own. The user installs into the suggested folder and quits. Keepsake lists the new executables, the user picks the game's, and **the same shortcut** is retargeted to it (name, exe, start folder, launch options). The prefix the installer wrote stays the game's prefix, so nothing is copied or moved.
2. **Sources.** An `.iso` file or a folder (an extracted disc or a GOG offline installer folder), chosen with Decky's file picker. Zip, rar and 7z are not supported in this slice: unpacking needs a binary or a large pure-Python library.
3. **ISO mounting through `udisksctl`** (register entry, A85): `loop-setup --read-only --no-user-interaction` and `mount --no-user-interaction`. No root and no bundled binary (P8, P9). When mounting fails, the loop device is deleted at once. When the job finishes, fails or is cancelled, the disc is unmounted and the loop device deleted. Without `udisksctl`, the ISO button is disabled and folders still work. For an ISO, the installer shortcut gets `STEAM_COMPAT_MOUNTS="<mount point>" %command%` so the disc is visible inside the Steam Linux Runtime container. Retargeting clears that again.
4. **Steam writes** go only through the executor (P15), each one from a user action: "Use setup.exe" queues `add-shortcut`, and choosing the game's program queues the four retarget operations. `add-shortcut` is a new executor kind. It needs no app ID, and its result carries the app ID Steam assigned. The frontend calls `AddShortcut`, waits, sets every field again (A70, A71) and picks the compatibility tool. The exe is never pre-quoted (A72). The job is `done` only when every retarget operation reads back. Any mismatch marks the job failed and tells the user to check the shortcut's properties.
5. **Compatibility tool.** The newest installed `GE-Proton*`, else `proton_experimental`, else the first tool Steam offers. Advisor's recommendation replaces this once slice 14 lands.
6. **Detecting the end of the install.** Core now publishes `game_exited` with `gameKey: null` for apps Saves does not manage. The Installer listens for the installer shortcut's app ID. "I have finished installing" is the manual fallback when the event is missed.
7. **Candidates.** New files under the target folder (compared with a listing taken before the install), plus every executable under the prefix's `drive_c` except Wine's own folders (`windows`, `users`, `ProgramData`, `Common Files`). Uninstallers, redistributables, crash reporters, helpers and anticheat programs are excluded by name. The rest are ranked by how many title words they share, then by size, with a penalty for depth and for launcher names. Candidates are offered for confirmation and never picked automatically. **A Windows installer runs with the user's rights in a prefix, which is not a sandbox. This is an accepted risk (T51)**, stated on the Install page and in the README.
8. **Library folder.** The setting `libraryRoot` (an absolute path, or empty for `~/Games`). The Installer itself writes no files: the installer program writes into the prefix and the chosen folder (v2 section 6.3).
9. **State.** The `installer_jobs` table (migration namespace `installer`), with the most recent 20 jobs shown. The Install tab appears only while the Installer module runs.

## Consequences

- A failed or cancelled install leaves the `Install: <Title>` shortcut in Steam for the user to remove. Removing it automatically would be a Steam write without a fresh user action; a "Remove the installer shortcut" button can come in slice 22.
- Multi-disc ISOs and disc swaps are not handled.
- Everything that touches Steam or udisks is unverified until the on-device checks (A70 to A76, A85).
