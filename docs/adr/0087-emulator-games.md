# ADR-0087: Emulator games between devices

- Status: accepted (R26, Peter's request of 22 November 2026; decided under ADR-0037). Stage 1 (detection, read-only) ships in v0.48.0; stage 2 (copying) follows.
- Date: 22 November 2026
- Deciders: Peter (owner)

## Context

**What Peter asked for.**
- **Detection:** EmuDeck, RetroDECK, standalone emulators and Steam ROM Manager games, with multi-file grouping.
- **Checks on the other device:** its emulators, firmware, BIOS and keys, matched by name or hash, with no contents revealed.
- **A copy plan,** then copying:
  - the game;
  - the emulator;
  - its config, without overwriting;
  - firmware;
  - the shortcut with its artwork.
- **Keeping the two devices in step,** a Device check, and tests.

**His rules for firmware and keys:**
- They travel only directly between his own paired devices, over the encrypted link.
- Never to the cloud, and never in snapshots, Device check exports, logs, the QR summary or AI payloads.
- Only counts and system names are reported.
- On the target they are stored owner-only.
- They are never downloaded.

**The research,** `docs/research/emulators.md`, found:
- **EmuDeck and RetroDECK keep their paths in settings files.** Emulator configs hold absolute paths.
- **Steam ROM Manager writes `shortcuts.vdf` directly,** with Steam closed.
- **AppImages and binaries are plain files.**
- **Flatpaks cannot be copied without the `flatpak` binary.**
- **Keys and firmware can be recognised by name and place.** BIOS files can also be matched against public hash lists.

## Decision

1. **Stage 1 (v0.48.0): detection, read-only** (`keepsake/replication/emulators.py`):
   - **Setups.** EmuDeck from `settings.sh` (or its default folders), and RetroDECK from `retrodeck.json` (or `~/retrodeck`).
   - **Standalone emulators,** found by their AppImage, binary or Flatpak folder.
   - **Games, one unit each:**
     - a `.m3u` claims its discs, which claim their tracks;
     - a `.cue` claims its `.bin` files, and a `.gdi` its tracks;
     - PS3 and Wii U folder games are one unit;
     - a referenced file outside the ROM folder is never included;
     - text, artwork and metadata files are skipped.
   - **Keys, firmware and BIOS files are counted by name and place.** They are never opened, hashed, logged or sent, and a test fails if one is opened.
   - **Screens.** Games and devices, Emulators, in Gaming Mode and the desktop app. Game names are shown on this device only.
   - **The Device check "Emulator setup"** carries counts and system names only.

2. **Decisions for stage 2,** recorded now so the design is fixed:
   - **Protocol.** A new peer message, a summary of the setup with counts and system names only, and copy jobs built on the existing transfer. This is a peer protocol change after slice 18, so its own ADR addendum will record the message format before it ships.
   - **Emulators.** AppImage and binary emulators are copied as the user's own files from their own other device, after a user action, into `~/Applications`, with the executable bit set. This is the same kind of copy as a game's files (P9 is about Keepsake bundling or downloading binaries, not moving the user's own).
   - **Flatpak emulators are not copied.** The page says to install them on the other device. Adding `flatpak` to the System Binary Register stays a separate decision.
   - **Settings.** Emulator configs are copied only where the target has none (never overwritten). Absolute paths are rewritten with the target's own ROM, BIOS and storage folders. SD card labels never travel (P10).
   - **Firmware, BIOS and keys** go only device to device over the encrypted link, after a separate confirmation. They are written with mode 0600 in folders with mode 0700, and never enter snapshots, logs, exports or AI payloads. They are never downloaded.
   - **Shortcuts** are made through `SteamClient` (P15) from the setup's own launch pattern, with artwork copied from the source. Keepsake never runs Steam ROM Manager.
   - **Saves stay with Saves** (P14). The emulators' save folders are left to Saves and to EmuDeck's own sync, which the page names.

## Consequences

- **Stage 1 changes nothing on either device.**
- **Threat model:** T160. **Device run:** step 48.
