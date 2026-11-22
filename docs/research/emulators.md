# Emulator games between devices: layouts, keys, grouping and copying

Research of 22 November 2026 for R26. Facts only: EmuDeck, RetroDECK, Steam ROM Manager and most emulators are GPL, and no code is used.

## What matters most

1. **Copying files is not enough.** Emulator configs hold absolute paths, which EmuDeck rewrites when it moves an install. Apps are installed per device and shortcuts are made again.
2. **Steam ROM Manager (SRM) writes `shortcuts.vdf` directly,** with Steam closed. That conflicts with P15, so Keepsake never runs SRM. Shortcuts go through `SteamClient`, built from what the user's setup says.
3. **Keys and firmware are recognised by name and place only.** Keepsake never reads or sends their contents, except copying them device to device when the user asks.

## EmuDeck (GPL-3.0)

- **Settings:** `~/.config/EmuDeck/settings.sh` (legacy `~/emudeck/settings.sh`).
  - Path keys: `emulationPath`, `romsPath`, `toolsPath`, `biosPath`, `savesPath`, `storagePath`.
  - Defaults are `~/Emulation/{roms,tools,bios,saves,storage}`; on an SD card, `/run/media/<label>/Emulation/`.
- **Layout:**
  - `roms/<system>/`;
  - `saves/<emu>/` (symlinks into each emulator's storage);
  - `storage/<emu>/` (NAND, HDD);
  - AppImages and binaries in `~/Applications/`.
- **Launchers:** `Emulation/tools/launchers/<emu>.sh`. They pull the backend with git and run EmuDeck's own cloud save sync, which could clash with Keepsake Saves.
- **SRM:** EmuDeck seeds `~/.config/steam-rom-manager/userData/userConfigurations.json` (78 parsers, mostly glob: ROM folder, launcher, arguments).
- **A second device:** the official route is to run the installer, then SRM. There is no CLI or API.

## RetroDECK (GPL-3.0, Flatpak `net.retrodeck.retrodeck`)

- **Config:** `~/.var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.json` (the path mapping is unverified).
- **Paths:** `rd_home_path` (default `~/retrodeck`), with `roms_path`, `bios_path`, `saves_path` and so on.
- **Emulators** are inside the Flatpak.
- **Launch:** `flatpak run net.retrodeck.retrodeck [-e emulator] [-s system] game`.

## Standalone emulators

| Emulator | Detect | Config | BIOS, firmware or keys | Type |
|---|---|---|---|---|
| Dolphin | Flatpak `org.DolphinEmu.dolphin-emu` | `~/.var/app/<id>/config/dolphin-emu/` | optional GC IPL | Flatpak |
| PCSX2 | `~/Applications/pcsx2-Qt.AppImage`, Flatpak `net.pcsx2.PCSX2` | `~/.config/PCSX2/inis/PCSX2.ini` | `[Folders] Bios`; `.rom0`, `.rom1`, `.nvm`; SHA1 against redump | AppImage |
| RPCS3 | `~/Applications/rpcs3.AppImage` | `~/.config/rpcs3/config.yml` | firmware installed into `dev_flash/`; RAP licences in `exdata` | AppImage |
| Ryujinx (Ryubing) | `~/Applications/publish/`, Flatpak `io.github.ryubing.Ryujinx` | `~/.config/Ryujinx/Config.json` | `~/.config/Ryujinx/system/prod.keys`, `title.keys`; firmware under `bis/system/Contents/registered` | binary or Flatpak |
| Eden | `~/Applications/Eden.AppImage` | `~/.config/eden/` | `~/.local/share/eden/keys/`; `nand/system/Contents/registered/` | AppImage |
| Citron | `~/Applications/citron.AppImage` | `~/.config/citron/` | `~/.local/share/citron/keys/` | AppImage |
| Cemu | `~/Applications/Cemu.AppImage` | `~/.config/Cemu/settings.xml` | `keys.txt` | AppImage |
| DuckStation | `~/Applications/DuckStation.AppImage` | `~/.local/share/duckstation/settings.ini` | `[BIOS] SearchDirectory` | AppImage (licence CC-BY-NC-ND) |
| PPSSPP | Flatpak `org.ppsspp.PPSSPP` | `~/.var/app/<id>/config/ppsspp/` | none | Flatpak |
| RetroArch | Flatpak `org.libretro.RetroArch` | `~/.var/app/<id>/config/retroarch/retroarch.cfg` | `system_directory` | Flatpak |
| xemu | Flatpak `app.xemu.xemu` | `~/.var/app/<id>/data/xemu/xemu/xemu.toml` | MCPX bootrom (MD5 `d49c52a4102f6df7bcf8d0617ac475ed`), flash, HDD | Flatpak |
| Vita3K | `~/Applications/Vita3K/` | `~/.config/Vita3K/config.yml` | firmware in `~/.local/share/Vita3K/` | binary |
| ShadPS4 | AppImage in `~/Applications` | `~/.local/share/shadPS4/config.toml` | `sys_modules` | AppImage |
| Azahar | `~/Applications/azahar.AppImage`, Flatpak `org.azahar_emu.Azahar` | `~/.config/azahar-emu/qt-config.ini` | `~/.local/share/azahar-emu/sysdata` | AppImage |

## Grouping multi-file games

- **.cue and .bin:** each `FILE` line names a .bin.
- **.gdi:** the track lines name the files.
- **.m3u:** one disc per line, relative to the .m3u; follow what each disc references.
- **CHD:** one file.
- **PS3 disc games:** a folder with `PS3_DISC.SFB` and `PS3_GAME/` (title ID in `PARAM.SFO`).
- **Switch:** NSP or XCI files tied by the title ID in their file names (the contents are encrypted).
- **Wii U:** `code/`, `content/` and `meta/` folders, or `.wua` files.
- **Default:** for folder formats the folder is the unit; for playlist formats, the file and everything it references.

## Copying emulators

- **AppImages and binaries** are plain files: copy them and set the executable bit.
- **Flatpaks** cannot be copied as installed folders. They need the `flatpak` binary: `create-usb` sideload, `build-bundle`, or a per-user install from Flathub on the receiver. Each is a System Binary Register and network decision.

## Hash identification sources

- **libretro-database `dat/System.dat`** (CC-BY-SA-4.0): 519 BIOS entries with size, CRC, MD5 and SHA1.
- **libretro-core-info** (MIT): firmware per core.
- **Switch keys and firmware** are recognised by name and place only.

## Safety

- Never download firmware or keys.
- **Where keys live:**
  - Switch: Ryujinx `system/`, the yuzu forks' `keys/`;
  - Wii U: Cemu `keys.txt`;
  - 3DS: Azahar `sysdata`;
  - PS3: RAP files;
  - Xbox: the xemu EEPROM and HDD.
- **DuckStation's licence** forbids redistributing modified packages. Copying the user's own unmodified AppImage between their own devices is the user's own copy.
