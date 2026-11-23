# Changelog

All notable changes to Haversack (called Keepsake until v0.51.0) are listed here. Versions follow [Semantic Versioning](https://semver.org/). Each release uses its section below as release notes.

## [Unreleased]

## [0.59.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **What is on each SD card** (Device, Storage). Every card and drive Steam knows, with its games by name, even when the card is out of the device.

## [0.58.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Pause game** in the quick access menu's Now playing. It stops the running game where it is until you press **Resume game**. It always carries on by itself after an hour, or if Haversack stops or the device restarts.

## [0.57.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Changed

- **A tidier menu.** Haversack's page has seven sections in its sidebar (Play, Saves, Games and devices, Device, Install, Settings and Diagnostics), each with its own colour.
  - Highlight a section to see its pages, and press A to open one. On a section's page, L1 and R1 move between its pages (Steam's own tabs), and B goes back to the sidebar. Each section opens where you left it.
  - Some pages moved:
    - Reconnect help is now in Device, Controllers;
    - Battery is in Device, Power and battery;
    - More device settings is in Device, Status;
    - Disk use is now Device, Storage;
    - the quick menu's shortcuts are in Settings, General.

    Old links and quick menu shortcuts still go to the right place.
  - The desktop app has the same sections and pages, as groups you can open and close.

### Fixed

- A game's Artwork section no longer disappears if checking it fails once.
- **The desktop app opens again.** From 0.52.0 it stayed on "Loading", because two of its files have capitals in their names and the app's own server refused them.

## [0.56.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Artwork for any non-Steam game** (its page in Saves, Games). When a game is missing a cover, wide cover, background or logo, Find artwork adds just those from SteamGridDB, through Steam. Artwork you already set is never replaced.
- **ProtonDB on the library badge.** With Advisor's ProtonDB source on, a Steam game's page in your library also says how many ProtonDB reports say it works. It reads only the index already on your device.

## [0.55.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Send your looks to your other handheld** (Device, Looks, then Send to your other handheld). Send your CSS Loader themes, Audio Loader sound packs and the animations you chose. The other handheld keeps everything it has: only what it lacks is added, and videos arrive as choices on its Looks page. Both handhelds need Looks and Replication switched on.

### Fixed

- When the other handheld turned down an emulator game, its reason is now shown, not just "refused it".

## [0.54.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Changed

- **No changes from 0.53.0.** A slip in publishing released this version before its changes were merged. They are in 0.55.0.

## [0.53.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Boot and sleep animations** (Device, Looks, in Gaming Mode and the desktop app). Choose one of your own WebM videos for when the device starts or goes to sleep. **Use Steam's own** goes back, and a video that was there before is kept and brought back. Switch on **Looks** in Settings, Modules first. While Animation Changer is installed, Haversack leaves the videos to it.
- **Themes and sounds at a glance:** the same page lists what CSS Loader and Audio Loader have installed.

## [0.52.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Help inside Haversack** (Settings, Help, in Gaming Mode and the desktop app). The whole user guide, readable with the controller: choose a topic, then move from section to section. It is built from the same text as the online guide, so the two always match.

### Changed

- **A rewritten README and user guide** for Haversack. They cover everything it now does: saves, sending games, Advisor, installing, the device pages and the desktop app.

## [0.51.1]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Changed

- **The project now lives at github.com/breakmylegs/haversack.** Old links, the install link and every earlier version's update check reach it through GitHub's redirect, so nothing needs doing.

## [0.51.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Changed

- **Keepsake is now called Haversack, and nothing is lost.** Update as usual from Updates. Decky then installs Haversack beside Keepsake, at the top of its list, and Haversack's quick menu shows one card.
  - Press **Remove the old Keepsake** and confirm. Haversack copies your settings, sign-ins, games list and history across, checks every file, and starts.
  - Until you press it, Keepsake keeps working as before, and Haversack does nothing, so the two never sync at once.
  - Your old copy stays on the device: to go back, remove Haversack and install an old Keepsake from the Releases page.
  - Your cloud folder keeps its name (Apps/Keepsake in OneDrive), so your other handheld carries on even before it updates.
  - Microsoft's and Google's sign-in pages still show the registered name, Keepsake.
  - If you use the helper, Keepsake Helper is removed with Keepsake: install Haversack Helper from Device, Reconnect help.
- **A new logo:** a satchel on teal.

## [0.50.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Changed

- **Status colours that colour-blind players can tell apart.** Success, warning and failure now use the Okabe-Ito palette (bluish green, orange, vermilion) everywhere: in Gaming Mode, the library badge and the desktop app, which also gains proper colours in dark mode. Every status still has its own icon or words, so colour is never the only sign.

## [0.49.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Send emulator games to your other handheld** (Games and devices, Emulators, in Gaming Mode and the desktop app). One button per game sends:
  - the game's files, with multi-disc games kept together;
  - the emulator and its settings, but only if the other handheld lacks them;
  - firmware and keys, only if you tick **Also send firmware and keys**. They go straight to your own paired handheld over the encrypted link and are stored there for your user only. They never go to the cloud, logs or exports.

  Nothing already on the other handheld is replaced. The game gets a Steam shortcut built from that handheld's own Steam ROM Manager setup. Without one, it is copied and you add the shortcut with Steam ROM Manager. Flatpak emulators are not copied: install them on the other handheld.

## [0.48.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Emulators** (Games and devices, Emulators, in Gaming Mode and the desktop app). See what this device has:
  - EmuDeck or RetroDECK, and standalone emulators;
  - every emulator game, with multi-disc games grouped as one;
  - how many firmware, BIOS and key files there are, per system. Keepsake counts them and never reads them.

  A Device check, "Emulator setup", records the counts. Copying games, emulators, settings, firmware and keys to your other handheld comes in the next release.

## [0.47.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Change the Legion controllers' own settings and the stick lights** (Device, Controllers, in Gaming Mode and the desktop app), through the Keepsake Helper.
  - **Controller settings:** mode, button chords, rumble and its style, FPS mouse DPI, controller sleep, the left gyro, the touchpad and its haptics.
  - **Stick lights:** on or off, effect, brightness, speed and colour.
  - **Keep my changes** applies them again whenever the controllers reconnect or the device wakes.
  - Keepsake leaves alone what Handheld Daemon or InputPlumber manage.

  This needs kernel 7.1 or later, and on the Legion Go the 2025 controller firmware. The power LED is not offered: every known way to switch it needs a kernel module or memory access that Keepsake will not use.

## [0.46.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Quick menu shortcuts** (Settings, Quick menu, and the desktop app). Choose what Keepsake's panel in the quick access menu shows, and in what order. There are three kinds:
  - pages to open, such as Fans, Reconnect help or Device checks;
  - actions that run straight from the menu, such as Sync this game now, Back up this game now, Next performance mode or Run all device checks;
  - status lines, such as games moving between devices, open conflicts and the controller Reconnect buttons.

  Only shortcuts whose module is on and whose feature is available are offered. Open Keepsake is always there, last. Changes show at once. In Gaming Mode, use Up and Down to reorder; in the desktop app, drag.

## [0.45.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Changed

- **Network ISOs install in place, without copying,** also from shares that are not mounted. Keepsake reads the ISO over the network through its own read-only file system, mounted with `fusermount3` (approved for the System Binary Register). If anything about it fails, the ISO is copied as before.

## [0.44.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Fan control** (Device, Fans, in Gaming Mode and the desktop app), through the Keepsake Helper.
  - **Legion Go 2: your own fan curve.**
    - Stepped or smooth, with live temperature and fan speed.
    - Named profiles, a default, one per performance mode and one per game.
    - The fan rises at once and comes down gently.
    - Full speed at 101 °C, whatever the curve.
    - The fan goes back to the firmware within seconds if Keepsake stops; **Hand back** does it straight away.
    - Firmware checks: BIOS RRCN16WW with EC 1.16 is checked already; any other BIOS runs a short fan test first.
    - Wider limits, up to 5200 RPM, are off by default and behind a warning.
  - **Legion Go: full fan speed** (kernel 7.2 and later). Its own fan table needs a kernel module that SteamOS does not include, so it is not offered; the page says why.
  - **Never fights another fan tool:** with one installed, Keepsake only shows the readings.
  - **A Device check, "Fan control".**

## [0.43.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Separate power limits** (Device, Power, and the desktop app's Power page):
  - set SPL (sustained), SPPT (slow boost) and FPPT (fast boost) on their own, each within the firmware's range;
  - kept per game like the other performance settings, put back when the game exits, and applied again after sleep;
  - this needs the Keepsake Helper. Without it the current values are shown.

### Fixed

- The Power page's settings no longer redraw themselves on every update, which could move the focus.

## [0.42.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Reconnect help in the desktop app** (Device, Reconnect help). It offers what Gaming Mode does:
  - every paired device, with help per device;
  - Pair and commit, Reconnect, Diagnose, Read stored host over USB and the report bundle;
  - with the Keepsake Helper: cable pairing, Restore backup and the SSP gate. Each restart asks twice, and the gate asks you to type "I understand".

  Installing the helper still needs Gaming Mode, because Decky's installer runs there.

## [0.41.1]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Fixed

- **The full page's sidebar still jumped around, and the settings were hard to reach** (v0.39.1 did not fix it all). Five causes were found and fixed:
  - **The sidebar was rebuilt after it appeared.** If Keepsake's backend took more than 3 seconds to answer, the sidebar first showed a short list, then rebuilt itself with the full one, losing your place. The sidebar is now the same fixed list from the start: every section and every page, always. A page whose module is off says so inside, with a button to Settings, Modules, instead of disappearing.
  - **A row of tabs inside each page.** Every tab is now its own entry in the sidebar, with lines between the sections, as in Steam's own settings. There is no inner row for the D-pad to cross.
  - **A page took focus by itself:** the Cloud page moved focus to its buttons after a browser sign-in. No page takes focus by itself any more; press right or A to go into a page.
  - **A page could vanish under the focus.** Several panels blanked themselves when a background refresh failed. They now keep what they show.
  - **Old links** (for example from the quick menu) now go straight to the right page. A redirect only runs when that old address is opened, never while you move through the sidebar.
- **A navigation recorder, to prove it on the device:** Diagnostics, Tools, "Record navigation for 60 seconds".
  - It notes page openings, focus moves and focus calls. It records no names.
  - It saves them to a file and adds them to the Device checks export.

## [0.41.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **The Keepsake Helper**, a small separate plugin that runs as root, so that Keepsake itself never does. Install it from Device, Reconnect help: Keepsake checks its signature and Decky asks you to confirm. It is locked to Keepsake's version and does only a short list of jobs, for Keepsake alone.
- **Cable pairing** in Reconnect help, for DualShock 4 controllers and clones that use their IDs:
  - with the controller on a USB cable, Keepsake gives it and this handheld the same new key, then restarts Bluetooth;
  - it checks first that the controller on the cable is the one you chose;
  - it keeps a backup of the pairing, with **Restore backup**;
  - an advanced key-order switch is there for a controlled experiment.
- **The SSP gate**, off by default, for controllers that are refused while security starts:
  - Secure Simple Pairing is on only while pairing;
  - it comes behind a two-step warning, because it lowers Bluetooth security for the whole adapter;
  - SSP goes back on when you switch it off, and by itself if Keepsake stops.
- **Bluetooth capture in the diagnosis.** With the helper, the diagnosis records 40 seconds of Bluetooth traffic. It can now tell a key mismatch from the security race, and recommends cable pairing or the SSP gate.

## [0.40.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Reconnect help for Bluetooth controllers** (Device, Reconnect help). It is for Bluetooth Classic controllers, often clones, that pair once and then will not reconnect with their normal button. Every paired device is listed, and you turn help on only for the ones that need it: the others are never touched.
  - **Pair and commit:** when you pair a helped controller, Keepsake connects to it at once, so that the controller saves the pairing.
  - **Reconnect:** put the controller in pairing mode and select Reconnect, also from the quick menu. It uses the existing pairing, so nothing is forgotten.
  - **Diagnose:** turn the controller off, start, press its button once. Keepsake watches what happens, reads the Bluetooth journal and says what is wrong in plain words.
  - **Read stored host over USB** for DualShock 4 controllers on a cable: shows whether the controller will call this handheld.
  - **Export report bundle:** the diagnosis and journal lines in one zip, to share on a BlueZ or community issue, with this handheld's address replaced.
  - **Suggestions:** a device that connects and drops at once is flagged with "may need help". Nothing is done to it unless you choose.
  - A dry-run switch, a log of every action, and a Device check, "Controller reconnect help".

  The lasting fixes (cable pairing with a new key, and the Bluetooth security setting) need the root helper and come in the next release.

## [0.39.1]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Fixed

- **The sidebar on Keepsake's full page was unpredictable.** Clicking **Saves** could open **Games and devices**, and the D-pad could get stuck between **Settings** and **Diagnostics**. There were three causes:
  - the sidebar was drawn before Keepsake knew which modules were on, then grew, so every entry shifted;
  - hidden entries for the old page links sat at the end of the list;
  - the old Games page and the new Games and devices section shared one address.

  Now:
  - the sidebar appears once the modules are known, with no hidden entries;
  - Games and devices has its own address;
  - old links open the right section and tab through a redirect.

## [0.39.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Keepsake's badge in Steam's library.** On each game's page, a small label shows its saves, for example "Saves: in step", "Saves: newer on Legion Go 2" or "Saves: conflict". For a game streamed from another device, it shows where it streams from. Switch it off in Settings, General.
- **Artwork for streaming tiles.** On Install, each non-Steam game you can stream from another device is listed. **Find artwork** finds it on SteamGridDB, using your key, and Keepsake sets the tile's artwork through Steam.

## [0.38.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **"When saves differ"**, in Settings, Sync and safety, and in the desktop app.
  - **"Ask me"** stays the default.
  - **"Take the newest"** keeps the newer version by itself, but only when exactly two versions differ, their times are at least 2 minutes apart, and no device's clock looks wrong.
  - The other version stays pinned in History, and **Undo** brings it back. Otherwise Keepsake asks you as before, and says why.
- **History shows where each snapshot is stored** when you use several save locations, for example "In: onedrive, direct".

## [0.37.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Device, Other** (the last stage of the Legion Go controls that needs no root), in Gaming Mode and the desktop app:
  - **Wi-Fi power saving** on or off, through Valve's steamos-manager;
  - **a BIOS check** that warns about known Legion Go BIOS problems, such as the withdrawn N3CN42WW, and features missing before v28 and v29;
  - **where the display settings are:** refresh rate, frame limit and brightness stay in Steam's own settings.
- **A new Device check, "BIOS check".**

## [0.36.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Device, Controllers** (the controller stage of the Legion Go controls), in Gaming Mode and the desktop app. It shows:
  - each controller's battery;
  - the settings the controllers report (mode, rumble, gyro, auto-sleep, touchpad);
  - the stick lights.

  It points to Steam's controller settings for remapping, dead zones and gyro, which Steam already does well. Changing the controllers' own settings and the lights needs root, and waits for the owner's decision. Keepsake only reads these.
- **A new Device check, "Controllers",** records what each device shows of its controllers.

## [0.35.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Battery care** (the battery stage of the Legion Go controls). On Device, Battery, in the quick access menu and in the desktop app, choose **Stop charging at 80%**, Lenovo's charge limit on the Legion Go and Go 2.
  - Keepsake changes it only through Valve's steamos-manager, with no root.
  - Where steamos-manager does not offer it yet, Keepsake shows whether the limit is on and says where to change it: Steam's settings, Power.
- **A new Device check, "Battery charge limit",** says who controls the limit on each device.

## [0.34.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Performance profiles per game** (the second stage of the Legion Go controls).
  - On Device, Power, in the quick access menu while a game runs, and in the desktop app, choose the performance mode (Quiet, Balanced, Performance or Custom), the TDP and CPU boost.
  - While a game runs, your choice is kept for that game and applied each time it starts. When the game exits, Keepsake puts back what was there before.
  - Keepsake changes these only through Valve's steamos-manager, with no root.
- **Keepsake never fights another tool.**
  - If SimpleDeckyTDP, PowerControl, LegionGo2Companion, Legion Go Toolbox, Legion Center or Handheld Daemon manages performance, Keepsake only shows the settings and names the tool.
  - If Steam's own performance settings change a value Keepsake set, Keepsake leaves it alone until the next launch and says so.
- **A new Device check, "Performance control",** says what each device offers and proves a write works.
- **Research.**
  - `docs/research/legion-control.md` lists every existing Legion Go tool, kernel interface and firmware rule, with sources.
  - ADR-0075 sets out how Keepsake changes device settings without root.
  - Fans, RGB and the controller's hardware settings need root, and wait for the owner's decision on that ADR.

## [0.33.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Live readings on Device, Status** (the first stage of the Legion Go controls). Every 2 seconds, in Gaming Mode and in the desktop app, it shows:
  - temperatures (CPU, GPU and the rest), fan speed, and battery and GPU power;
  - Lenovo's performance mode (Quiet, Balanced, Performance or Custom);
  - the BIOS version and date;
  - CPU boost, SMT and the cores online;
  - the battery charge limit, if the system exposes one.

  Keepsake only reads these; it changes nothing.
- **A new Device check, "Device readings",** says which sensors, fan readings and modes this device exposes, so the next stages know what they can control.

## [0.32.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Changed

- **A new layout** (ADR-0073, `docs/design/layout-v3.md`). Keepsake's full page now has seven sections, each with tabs along the top. Every page from before is still there, as a tab, and old links still open it:
  - **Play:** Now playing, Advisor.
  - **Saves:** Games, Conflicts, History, Activity, Import and export.
  - **Games and devices:** Moving games, Other devices, Disk use.
  - **Device:** Status.
  - **Install.**
  - **Settings:** General, Cloud, Sync and safety, Modules, Updates.
  - **Diagnostics:** Health, Device checks, Tools, Logs.
- **The quick access menu fits on one screen.**
  - **Now playing:** the game, its saves, Save checkpoint, and the Advisor's top advice as one row.
  - **Moving games.**
  - **Up to three things that need you.**
  - **The status line,** then **Sync now** and **Open Keepsake**.
- **Renamed:** "Devices" is **Other devices**, "Storage" is **Disk use**, and "Import saves" is **Import and export**, which now also holds the zip export.
- **Errors are plain sentences everywhere,** never "Python ValueError: ...".
- **The desktop app** now uses the same sections in a sidebar, with:
  - a settings search;
  - a Games table you can sort and filter;
  - a sortable transfer table;
  - Advisor, with charts of your last sessions (power, temperatures, frame rate, battery);
  - Device, Status;
  - Device checks;
  - Logs.

### Added

- **Device, Status:** this handheld as Keepsake sees it, with its model and profile, power range, screen, battery and charging. The device controls arrive here next.

## [0.31.1]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Fixed

- **Send's confirmation was out of date.** It said nothing is copied until the game is accepted on the other device. Since 0.31.0 a game starts copying by itself, so it now says that, and that either device can stop and remove it. Gaming Mode and the desktop app.
- **The device-run list** labelled a 0.30.2 step as 0.31.0.

## [0.31.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- **Get a game from another device.** On Devices, press **Games on Legion Go** (or your other device's name), then **Get this game**.
  - Keepsake checks there is space on this device first.
  - The other device then sends the game as if you had pressed Send there, with the same rules: nothing is replaced, a missing compatibility tool is copied, and the Steam shortcut, artwork and launch options are set up.
  - The other device allows it automatically, because pairing is trust both ways, and shows a toast.
- **Progress bars on both devices.** They show on the Devices page, as a compact line in the quick access menu, and as a table in the desktop app. Each bar shows:
  - the percentage done, GiB done of the total, speed and time left;
  - the stage (checking space, preparing, copying, verifying, adding to Steam, done, or failed with the reason);
  - **Stop and remove**.

  Several games each get their own bar, and the bars carry on while a page is closed and reopened.
- **Stop and remove on either device.** Stopping on the sending device asks the receiving one to delete everything the copy made, then withdraws the offer. Stopping on the receiving device withdraws the offer on the sending one.
- **A space check before sending.** Keepsake now asks the other device first and stops at once if the game will not fit, before it spends minutes reading the game's files. The message reads, for example, "Legion Go 2 doesn't have enough space: needs 41.2 GiB, has 12.0 GiB free".
- **Toasts on both devices** when a game starts copying, arrives, fails, or is stopped and removed.

### Changed

- **New games no longer wait for Accept.** A game from a paired device starts copying as soon as it arrives, with the same checks as before. Updates to a game you already have still follow that game's own setting.
- **Pairing works both ways.** When a pairing you started finishes, this device can be reached too, so games can go either way. "Let other devices reach this one" on Devices still switches that off.

## [0.30.2]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Fixed

- **Sending a game could stall for ever** (seen with Factorio). Cause: accepting an offer started the copy from a worker thread, where it cannot start. The offer then said "transferring" with nothing running, a failed copy never changed its state, and the sending device was never told.
  - The copy now starts on the plugin's own event loop. Anything that stops it marks the offer **failed** with a plain reason, and nothing is left half-started.
  - Both devices now see what happened. The receiving device tells the sending one each change (copying, adding to Steam, arrived, failed, declined, removed), without any folder paths. The sending device's list and a toast show it.
  - The sending device also no longer says "preparing" for ever when an unexpected error stops an offer.
  - The Device checks' **Export results** now includes the offer and transfer states, redacted: no titles, device names or paths.
- **OneDrive sign-in could end on a "cannot connect to localhost" page.**
  - Keepsake now keeps answering the sign-in address for 2 minutes after sign-in ends, so a browser that loads it again sees "You're signed in".
  - If you finished on your phone instead, an open tab now says so plainly, and the toast says "Signed in with your phone".
  - Keepsake listens on IPv6 (`::1`) as well as IPv4, on the same port. If that port is taken on IPv6, it picks another one, so a browser that looks up `localhost` as IPv6 still arrives.
- **Windows shares: Find shares and Browse showed raw errors.**
  - Addresses written the Windows way now work, as File Explorer shows them (`\\server\share\folder`). Before, the backslashes ended up in the server or folder name.
  - User names written `DOMAIN\user` or `PC-NAME\user` now sign in, with the domain sent separately.
  - Errors on the Install page are now plain sentences, never "Python ValueError: ...". Anything unexpected names itself once and points to diagnostics.

## [0.30.1]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Fixed

- **The Desktop Mode taskbar could freeze** (plasmashell stopped responding while KWin and Konsole kept working, until the plugin was stopped). Cause:
  - Plasma asks a tray icon for its properties and menu and waits for the answer.
  - Keepsake's tray checked the plugin over HTTP, with up to 3 seconds' wait, on the same thread that answers Plasma: when its menu was about to open, and every 30 seconds.
  - When the plugin was slow, for example while a disk on a dock was slow or offline, every check held Plasma up.
  - Clicking the icon also had two threads reading the tray's D-Bus connection.

  Now:
  - the tray answers Plasma at once from what it last knew;
  - it checks the plugin on a separate thread, one check at a time, with a 1-second limit;
  - it opens the window over a connection of its own;
  - it signals Plasma only when its status changes, at most every 2 seconds.

  The plugin's page also gives its status without waiting for anything. Game scans run on their own low-priority threads, one at a time; a disk that is slow, spinning up or gone no longer holds anything up, and the last list of games is used. A new Device check, "Desktop tray responsive", times both and fails above 200 ms.

## [0.30.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- Several save locations at once: on the Cloud page, **Add ... as a save location** for each one you want, for example OneDrive, directly between your devices, and a NAS. Every snapshot goes to each, a location that is down is caught up later and never stops you playing, and each is listed with its status and **Remove**, which never deletes what is stored there. A game can use only some of them. Existing setups with one location work exactly as before (ADR-0071).

## [0.29.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Changed

- Pairing is simpler: there is no window to open first. On one device press **Find devices**, choose the other and press **Pair**; the other device asks you to **Accept** or **Decline** (only a notification while a game runs), then shows a 6-digit code to type on the first with a number pad. Both devices check the code without sending it, so a device in the middle cannot pair with either; a wrong code ends the attempt on both, and a device that keeps trying is locked out for ten minutes. Both devices need this version to pair; devices already paired stay paired. A new Device check, "The other handheld can be seen" (ADR-0070).

## [0.28.0]

> **Not yet tested on a device.** Published on the stable channel before the device run, at the owner's request. Report anything that misbehaves on the Releases page.

### Added

- Advisor remembers how each game ran on this device. While you play, it measures frame rate, power, battery drain, load, clocks, temperatures and throttling, read only and with nothing to set up, and the game's Advisor page shows a **Last session** card and **Recent sessions**, even when the game is not running. Advice "Measured on this device" comes first, for example lowering a frame cap the game cannot hold, or a lower TDP that gives the same frame rate. The frame rate comes from Steam's own overlay or your MangoHud logs; otherwise the card says it is not available. A new Device check, "Session stats sources" (ADR-0069).

## [0.27.0]

> **Not yet tested on a device.** Everything since 0.26.0, published as a stable release before the device run, at the owner's request. It supersedes 0.27.0-beta.1 and -beta.2. Report anything that misbehaves on the Releases page.

### Added

- The desktop app comes with the plugin: on SteamOS and Bazzite, Keepsake now starts with Desktop Mode, minimised to the system tray. Click the icon, or **Open Keepsake** in its menu, to open it; closing the window leaves it in the tray, and **Quit** stops it until you next log in. Keepsake is also in the app menu, which brings up the running one. Nothing to install and nothing to switch on; Settings, Modules can turn it off. A new Device check, "Desktop app ready" (ADR-0068).
- An ISO on a share that is already mounted is opened where it is; if the share does not allow that, Keepsake now copies it to the device by itself and installs from the copy, instead of failing. A new Device check, "Network ISO in place", tests opening an ISO on a mounted share, replacing the old SSH loop test. Installing straight from a share that is not mounted is built and waits for approval of `fusermount3` in the System Binary Register; until then those ISOs are copied first as before (ADR-0067).
- **Find shares on my network** under Install, From a network location, Windows share (SMB): lists the Windows PCs, NAS boxes and Macs sharing folders on your local network (found by mDNS, NetBIOS and WS-Discovery, with no extra software), and picking one lists its shares. A new Device check of the same name says which ways work on your network (ADR-0066).
- **Uninstall** on each game's page. Steam games: an optional final backup of the saves, then Steam's own uninstall. Non-Steam games: a confirmation screen listing every folder to delete with its size and the free space after (Cancel selected first), then a final backup if the game syncs, the shortcut and its artwork removed from Steam, the Proton prefix and game folder deleted in the background with progress and **Stop**, and Keepsake's records of the game cleared. Home folders, Steam libraries, folders other games use, links and drives are never deleted, and running games and games you stream from another device are refused (ADR-0065).
- Games you can stream from another device (Steam Remote Play's tiles with **Stream** instead of **Play**) are recognised from Steam's own install state and never treated as games on this device: not synced, sent, replicated, advised on or uninstalled. Real shortcuts always stay listed, even with an unusual path. **Show games you can stream from another device** lists them, and a new Device check, "Games you can stream from another device", counts them and flags any synced game that streams. To keep the library tidy, use Steam's **Installed** tab (ADR-0064).

### Changed

- Steam games are always listed on the Games page beside your non-Steam games, and their saves sync, back up and restore in exactly the same way. A Steam game you have played that has no Steam Cloud saves now starts syncing by itself, and Keepsake tells you which. Games that use Steam Cloud stay off unless you turn them on, and a game you turn off stays off. Settings has **Sync Steam games that Steam Cloud does not back up** to stop it (ADR-0063).

## [0.27.0-beta.2]

> **Not yet tested on a device.** A pre-release, offered only on the Pre-release update channel. Report anything that misbehaves on the Releases page.

### Added

- The desktop app comes with the plugin: on SteamOS and Bazzite, Keepsake now starts with Desktop Mode, minimised to the system tray. Click the icon, or **Open Keepsake** in its menu, to open it; closing the window leaves it in the tray, and **Quit** stops it until you next log in. Keepsake is also in the app menu, which brings up the running one. Nothing to install and nothing to switch on; Settings, Modules can turn it off. A new Device check, "Desktop app ready" (ADR-0068).

## [0.27.0-beta.1]

> **Not yet tested on a device.** A pre-release with the changes merged since 0.26.0. It is offered only on the Pre-release update channel. Report anything that misbehaves on the Releases page.

### Added

- An ISO on a share that is already mounted is opened where it is; if the share does not allow that, Keepsake now copies it to the device by itself and installs from the copy, instead of failing. A new Device check, "Network ISO in place", tests opening an ISO on a mounted share, replacing the old SSH loop test. Installing straight from a share that is not mounted is built and waits for approval of `fusermount3` in the System Binary Register; until then those ISOs are copied first as before (ADR-0067).
- **Find shares on my network** under Install, From a network location, Windows share (SMB): lists the Windows PCs, NAS boxes and Macs sharing folders on your local network (found by mDNS, NetBIOS and WS-Discovery, with no extra software), and picking one lists its shares. A new Device check of the same name says which ways work on your network (ADR-0066).
- **Uninstall** on each game's page. Steam games: an optional final backup of the saves, then Steam's own uninstall. Non-Steam games: a confirmation screen listing every folder to delete with its size and the free space after (Cancel selected first), then a final backup if the game syncs, the shortcut and its artwork removed from Steam, the Proton prefix and game folder deleted in the background with progress and **Stop**, and Keepsake's records of the game cleared. Home folders, Steam libraries, folders other games use, links and drives are never deleted, and running games and games you stream from another device are refused (ADR-0065).
- Games you can stream from another device (Steam Remote Play's tiles with **Stream** instead of **Play**) are recognised from Steam's own install state and never treated as games on this device: not synced, sent, replicated, advised on or uninstalled. Real shortcuts always stay listed, even with an unusual path. **Show games you can stream from another device** lists them, and a new Device check, "Games you can stream from another device", counts them and flags any synced game that streams. To keep the library tidy, use Steam's **Installed** tab (ADR-0064).

### Changed

- Steam games are always listed on the Games page beside your non-Steam games, and their saves sync, back up and restore in exactly the same way. A Steam game you have played that has no Steam Cloud saves now starts syncing by itself, and Keepsake tells you which. Games that use Steam Cloud stay off unless you turn them on, and a game you turn off stays off. Settings has **Sync Steam games that Steam Cloud does not back up** to stop it (ADR-0063).

## [0.26.0]

> **Not yet tested on a device.** This release has everything in 0.26.0-beta.1, published as stable at the owner's request before the device run. Report anything that misbehaves on the Releases page.

### Added

- Device checks: on the Diagnostics page, **Device checks** runs the device run's measurements on the device itself. Each check shows pass or fail and what it found, **Run all** runs them all, and **Export results** saves one file with no names, addresses or paths and shows a QR code and a short summary to photograph. The steps are in docs/device-run.md (ADR-0062).
- Save sync with no cloud account: on the Cloud page, **Directly between my devices** keeps your saves in step between your paired devices. Each device keeps the history, and they fetch what they are missing from each other whenever they can reach each other. Conflicts and history work as with a cloud store. There is no copy away from your devices (ADR-0061).
- One-button cloud sign-in: OneDrive and Google Drive now work out of the box. Pick one, press **Sign in** and approve with your account. No client ID or app registration is needed; your own client is still available under Advanced (ADR-0055).
- Games you sent stay in step between devices. On the game's page, **Updates** is Ask me, Take them by themselves, or Off, with **Check now** and **Send update**. On Devices, **Apply update**, **Keep mine** and **Stop update**:
  - when a game changes on one device, for example a patch, Keepsake offers the update to the other;
  - set to Auto, the update goes in by itself;
  - if both devices changed the game, Keepsake asks you which copy to keep;
  - your saves and settings on each device are never replaced by an update (ADR-0060).
- Send a game to another device: **Send to <device>** on a non-Steam game, then **Accept** on the other device, under Devices:
  - Keepsake copies a non-Steam game, its Proton prefix, its compatibility tool if needed, and its artwork to the other device;
  - it adds the game to Steam there with the same name, program, launch options and tool;
  - your saves come along and Saves carries on with them;
  - the other device asks before anything is copied, and **Stop and remove** undoes everything (ADR-0059).
- Transfers between your devices adapt to the link:
  - they use more parallel streams only while that makes them faster, and can pull from several of your devices at once;
  - they keep the device awake while copying, wait while a game runs and below 30 percent battery off the charger, then carry on by themselves;
  - **Devices** shows each transfer's progress, speed and time left, with **Pause**, **Resume** and **Stop and remove** (ADR-0058).
- Replication's transfer engine (no button yet; sending games comes with slice 19): folders copy between paired devices exactly. Every piece is checked, and a copy carries on after a dropped network, a restart or a power cut. Nothing replaces the existing copy until the new one is complete and verified, and **Stop and remove** leaves nothing behind (ADR-0057).
- Devices: switch on Replication in Modules to link your own handhelds and PCs directly, with no SSH, keys or accounts. **Find devices** lists Keepsake devices on your network. You pair each one once by checking that both screens show the same 6-digit code. Paired devices can be checked, woken with Wake-on-LAN, or removed. Every connection is encrypted with a key only your two devices know, and nothing goes through the cloud. Sending games between devices comes next (ADR-0054, ADR-0056).
- Install, games on several discs: keep the ISOs together in one folder, and when the installer asks for the next disc, press **Swap to <disc>**. Keepsake puts it in the drive without stopping the installer (ADR-0053).
- Install queue: start another install while one is under way, and it waits its turn. Queued installs start by themselves and carry on after a restart (ADR-0053).
- Install, runtimes: the runtime installers a game ships (Visual C++, DirectX, .NET and others) are listed, with advice on when they are needed. Nothing is run for you (ADR-0053).
- Storage: a new page shows how much space each game uses (the game, its Proton prefix, its shader cache and its saves). **Clear shader cache** frees a game's shader cache. **Reset prefix, keep saves** gives a game with a broken prefix a fresh one: Keepsake keeps a checked copy of the saves, moves the old prefix aside, and puts the saves back after you start the game once. The old prefix stays until you delete it (ADR-0052).
- Heroic, Lutris and Bottles games: on a handheld or a Linux PC, Games lists your Heroic (GOG and Epic), Lutris and Bottles games, and syncs their saves like any other game. Newer saves from your other devices come in while the game is closed, and only if you have not played on since (ADR-0051).
- Emulator saves: one entry each for RetroArch, Dolphin, PCSX2, DuckStation, PPSSPP, RPCS3 and Cemu, with battery and memory-card saves. Save states can be added per emulator, but are off by default (ADR-0051).
- Cloud integrity: once a week Keepsake checks that the cloud copies of each game's important snapshots are intact, and **Check cloud integrity** checks them all. A damaged copy shows in Health and in the game's History, where **Repair** saves a fresh copy from this device (ADR-0050).
- Export snapshots: copy your saves out as plain zip files, with a list of their contents, to a folder you choose, such as an SD card. There is no lock-in, and nothing in that folder is overwritten (ADR-0050).
- Releases now include a software bill of materials, covered by the release signature. The release instructions include signing-key rotation and compromise runbooks, and private vulnerability reporting is on (ADR-0050).
- Newer save from another device: the game's row, the Quick Access Menu and the PC Overview say when another device has a newer save, for example "Newer save from Handheld B, 10 minutes ago". **Get it now** brings it in straight away, but only if you have not played on since; otherwise nothing is replaced (ADR-0049).
- Playtime across your devices: each game's page shows how long you have played it in all, and on each device (ADR-0049).
- What's new: after an update, Keepsake shows that version's release notes once. A short tip in the Quick Access Menu introduces checkpoints and restoring single files (ADR-0049).
- Machines without a battery, such as a Steam Machine or a desktop: Advisor leaves out battery estimates, and suggests no TDP when it has no profile for the machine (ADR-0049).

- Checkpoints: **Save checkpoint** keeps a named copy of a game's save, for example "Before the final boss". It is in the Quick Access Menu while you play and in each game's History. Checkpoints are kept until you remove them (ADR-0048).
- Restore some files: see what restoring an older save would change, file by file, and restore only the files you choose. It can be undone like any restore (ADR-0048).
- A clearer conflict screen: it shows when this device's save last changed (not "now"), and lists the files that are new, gone or changed on each side. Keepsake still never chooses for you (ADR-0048).
- Games: find a game by name, and turn sync on or off for every game shown in one go (ADR-0048).
- Activity: a plain-words list of what Keepsake did, such as saves sent, saves brought in, checkpoints and restores, on the handheld and the PC (ADR-0048).
- A user guide on GitHub: getting started on a handheld, a Linux PC or Windows, a guide to each feature, privacy, and questions and answers, with screenshots and diagrams. Start at docs/user/README.md (ADR-0046).
- PC preview, the desktop interface: `python -m keepsake.host --open` now shows Keepsake in your browser, on this computer only. It has an overview with Sync now, conflicts with the same two-step choices as in Gaming Mode, history, health checks, and the modules page with on and off switches. It follows your light or dark setting. The rest of the screens follow (ADR-0040).
- PC preview, Steam for Windows: on Windows, Keepsake finds Steam where Steam for Windows records it, and reads its libraries, games and non-Steam shortcuts. Games run natively there, so their saves are found in your Windows folders (ADR-0038).
- PC preview, saves after you play: the PC host notices when a game starts and stops. When you quit, it saves to the cloud within seconds. It never restores a save while a game is running. On a PC, saves from your other devices arrive when Keepsake syncs while the game is closed (ADR-0041).
- PC preview, install from the release: each release now carries `Keepsake-desktop-v<version>.zip`, covered by the release signature. Unzip it and run `install.pyw`. Keepsake installs into your own folders with no administrator rights, starts when you sign in, and opens in your browser. `install.pyw --uninstall` removes it and keeps your settings and saves (ADR-0042).
- Sign in with one button: "Sign in with OneDrive" or "Sign in with Google" opens the provider's page in a browser. Sign in with your normal account, allow access, and Keepsake carries on, refreshing its access by itself. On a PC it is your usual browser. In Gaming Mode it is Steam's browser where the provider allows it. Google does not allow sign-in there, so Google starts with a code on your phone instead, and a switch lets you choose either way for each service. If a browser sign-in does not finish, "Use your phone instead" is one press away. Each device signs in for itself, so you can sign out one device without the others. The desktop interface gains a Cloud page (ADR-0044).
- Replication (in development): game installs will go only directly between your own devices, on your network or over your own VPN, and never through any cloud storage. They are sent uncompressed and exactly as they are. They can be paused and resumed, and recover by themselves after errors, network loss or a restart. "Stop and remove" cleans up everything a transfer made. Tests now enforce the no-cloud and no-compression rules (ADR-0045).
- Diagnostics, "Sign-in browser test": three steps that check which sign-ins work in Steam's browser on your device (ADR-0044).
- PC preview, more of the desktop interface: Games (turn sync on per game, choose a game's save data, confirm a link another device proposes), Import from Ludusavi with progress, and Settings (device name, sync interval, notifications, update channel).
- PC preview, updates: the desktop interface has an Updates page. Check, Install, then Restart. Keepsake installs a new version only when the release signature and checksum prove it is Keepsake's own. It keeps the version you had, so "Go back" returns to it. Your settings, saves and start-up choice are left as they are (ADR-0043).

### Changed

- The PC interface's text now follows your browser's text size setting (ADR-0049).
- Snapshot clean-up plans are about four times faster for games with long histories (ADR-0050).

### Fixed

- A device that had never synced a game and had no save files for it no longer reports a conflict; the cloud save is simply brought in (ADR-0051).

## [0.26.0-beta.1]

> **Pre-release for device testing: nothing in this version has been tested on a device yet.** It is offered only to devices on the Pre-release update channel. The stable channel and the first-install link stay on v0.25.0.

### Added

- Device checks: on the Diagnostics page, **Device checks** runs the device run's measurements on the device itself. Each check shows pass or fail and what it found, **Run all** runs them all, and **Export results** saves one file with no names, addresses or paths and shows a QR code and a short summary to photograph. The steps are in docs/device-run.md (ADR-0062).
- Save sync with no cloud account: on the Cloud page, **Directly between my devices** keeps your saves in step between your paired devices. Each device keeps the history, and they fetch what they are missing from each other whenever they can reach each other. Conflicts and history work as with a cloud store. There is no copy away from your devices (ADR-0061).
- One-button cloud sign-in: OneDrive and Google Drive now work out of the box. Pick one, press **Sign in** and approve with your account. No client ID or app registration is needed; your own client is still available under Advanced (ADR-0055).
- Games you sent stay in step between devices. On the game's page, **Updates** is Ask me, Take them by themselves, or Off, with **Check now** and **Send update**. On Devices, **Apply update**, **Keep mine** and **Stop update**:
  - when a game changes on one device, for example a patch, Keepsake offers the update to the other;
  - set to Auto, the update goes in by itself;
  - if both devices changed the game, Keepsake asks you which copy to keep;
  - your saves and settings on each device are never replaced by an update (ADR-0060).
- Send a game to another device: **Send to <device>** on a non-Steam game, then **Accept** on the other device, under Devices:
  - Keepsake copies a non-Steam game, its Proton prefix, its compatibility tool if needed, and its artwork to the other device;
  - it adds the game to Steam there with the same name, program, launch options and tool;
  - your saves come along and Saves carries on with them;
  - the other device asks before anything is copied, and **Stop and remove** undoes everything (ADR-0059).
- Transfers between your devices adapt to the link:
  - they use more parallel streams only while that makes them faster, and can pull from several of your devices at once;
  - they keep the device awake while copying, wait while a game runs and below 30 percent battery off the charger, then carry on by themselves;
  - **Devices** shows each transfer's progress, speed and time left, with **Pause**, **Resume** and **Stop and remove** (ADR-0058).
- Replication's transfer engine (no button yet; sending games comes with slice 19): folders copy between paired devices exactly. Every piece is checked, and a copy carries on after a dropped network, a restart or a power cut. Nothing replaces the existing copy until the new one is complete and verified, and **Stop and remove** leaves nothing behind (ADR-0057).
- Devices: switch on Replication in Modules to link your own handhelds and PCs directly, with no SSH, keys or accounts. **Find devices** lists Keepsake devices on your network. You pair each one once by checking that both screens show the same 6-digit code. Paired devices can be checked, woken with Wake-on-LAN, or removed. Every connection is encrypted with a key only your two devices know, and nothing goes through the cloud. Sending games between devices comes next (ADR-0054, ADR-0056).
- Install, games on several discs: keep the ISOs together in one folder, and when the installer asks for the next disc, press **Swap to <disc>**. Keepsake puts it in the drive without stopping the installer (ADR-0053).
- Install queue: start another install while one is under way, and it waits its turn. Queued installs start by themselves and carry on after a restart (ADR-0053).
- Install, runtimes: the runtime installers a game ships (Visual C++, DirectX, .NET and others) are listed, with advice on when they are needed. Nothing is run for you (ADR-0053).
- Storage: a new page shows how much space each game uses (the game, its Proton prefix, its shader cache and its saves). **Clear shader cache** frees a game's shader cache. **Reset prefix, keep saves** gives a game with a broken prefix a fresh one: Keepsake keeps a checked copy of the saves, moves the old prefix aside, and puts the saves back after you start the game once. The old prefix stays until you delete it (ADR-0052).
- Heroic, Lutris and Bottles games: on a handheld or a Linux PC, Games lists your Heroic (GOG and Epic), Lutris and Bottles games, and syncs their saves like any other game. Newer saves from your other devices come in while the game is closed, and only if you have not played on since (ADR-0051).
- Emulator saves: one entry each for RetroArch, Dolphin, PCSX2, DuckStation, PPSSPP, RPCS3 and Cemu, with battery and memory-card saves. Save states can be added per emulator, but are off by default (ADR-0051).
- Cloud integrity: once a week Keepsake checks that the cloud copies of each game's important snapshots are intact, and **Check cloud integrity** checks them all. A damaged copy shows in Health and in the game's History, where **Repair** saves a fresh copy from this device (ADR-0050).
- Export snapshots: copy your saves out as plain zip files, with a list of their contents, to a folder you choose, such as an SD card. There is no lock-in, and nothing in that folder is overwritten (ADR-0050).
- Releases now include a software bill of materials, covered by the release signature. The release instructions include signing-key rotation and compromise runbooks, and private vulnerability reporting is on (ADR-0050).
- Newer save from another device: the game's row, the Quick Access Menu and the PC Overview say when another device has a newer save, for example "Newer save from Handheld B, 10 minutes ago". **Get it now** brings it in straight away, but only if you have not played on since; otherwise nothing is replaced (ADR-0049).
- Playtime across your devices: each game's page shows how long you have played it in all, and on each device (ADR-0049).
- What's new: after an update, Keepsake shows that version's release notes once. A short tip in the Quick Access Menu introduces checkpoints and restoring single files (ADR-0049).
- Machines without a battery, such as a Steam Machine or a desktop: Advisor leaves out battery estimates, and suggests no TDP when it has no profile for the machine (ADR-0049).

- Checkpoints: **Save checkpoint** keeps a named copy of a game's save, for example "Before the final boss". It is in the Quick Access Menu while you play and in each game's History. Checkpoints are kept until you remove them (ADR-0048).
- Restore some files: see what restoring an older save would change, file by file, and restore only the files you choose. It can be undone like any restore (ADR-0048).
- A clearer conflict screen: it shows when this device's save last changed (not "now"), and lists the files that are new, gone or changed on each side. Keepsake still never chooses for you (ADR-0048).
- Games: find a game by name, and turn sync on or off for every game shown in one go (ADR-0048).
- Activity: a plain-words list of what Keepsake did, such as saves sent, saves brought in, checkpoints and restores, on the handheld and the PC (ADR-0048).
- A user guide on GitHub: getting started on a handheld, a Linux PC or Windows, a guide to each feature, privacy, and questions and answers, with screenshots and diagrams. Start at docs/user/README.md (ADR-0046).
- PC preview, the desktop interface: `python -m keepsake.host --open` now shows Keepsake in your browser, on this computer only. It has an overview with Sync now, conflicts with the same two-step choices as in Gaming Mode, history, health checks, and the modules page with on and off switches. It follows your light or dark setting. The rest of the screens follow (ADR-0040).
- PC preview, Steam for Windows: on Windows, Keepsake finds Steam where Steam for Windows records it, and reads its libraries, games and non-Steam shortcuts. Games run natively there, so their saves are found in your Windows folders (ADR-0038).
- PC preview, saves after you play: the PC host notices when a game starts and stops. When you quit, it saves to the cloud within seconds. It never restores a save while a game is running. On a PC, saves from your other devices arrive when Keepsake syncs while the game is closed (ADR-0041).
- PC preview, install from the release: each release now carries `Keepsake-desktop-v<version>.zip`, covered by the release signature. Unzip it and run `install.pyw`. Keepsake installs into your own folders with no administrator rights, starts when you sign in, and opens in your browser. `install.pyw --uninstall` removes it and keeps your settings and saves (ADR-0042).
- Sign in with one button: "Sign in with OneDrive" or "Sign in with Google" opens the provider's page in a browser. Sign in with your normal account, allow access, and Keepsake carries on, refreshing its access by itself. On a PC it is your usual browser. In Gaming Mode it is Steam's browser where the provider allows it. Google does not allow sign-in there, so Google starts with a code on your phone instead, and a switch lets you choose either way for each service. If a browser sign-in does not finish, "Use your phone instead" is one press away. Each device signs in for itself, so you can sign out one device without the others. The desktop interface gains a Cloud page (ADR-0044).
- Replication (in development): game installs will go only directly between your own devices, on your network or over your own VPN, and never through any cloud storage. They are sent uncompressed and exactly as they are. They can be paused and resumed, and recover by themselves after errors, network loss or a restart. "Stop and remove" cleans up everything a transfer made. Tests now enforce the no-cloud and no-compression rules (ADR-0045).
- Diagnostics, "Sign-in browser test": three steps that check which sign-ins work in Steam's browser on your device (ADR-0044).
- PC preview, more of the desktop interface: Games (turn sync on per game, choose a game's save data, confirm a link another device proposes), Import from Ludusavi with progress, and Settings (device name, sync interval, notifications, update channel).
- PC preview, updates: the desktop interface has an Updates page. Check, Install, then Restart. Keepsake installs a new version only when the release signature and checksum prove it is Keepsake's own. It keeps the version you had, so "Go back" returns to it. Your settings, saves and start-up choice are left as they are (ADR-0043).

### Changed

- The PC interface's text now follows your browser's text size setting (ADR-0049).
- Snapshot clean-up plans are about four times faster for games with long histories (ADR-0050).

### Fixed

- A device that had never synced a game and had no save files for it no longer reports a conflict; the cloud save is simply brought in (ADR-0051).

## [0.25.0]

Install from network locations (web servers, Windows shares and WebDAV), ProtonDB reports in Advisor, the first signed release, and the groundwork for Linux and Windows PCs.

### Security

- This release is signed, and it pins Keepsake's release key. Releases are signed from this one on. Devices on any earlier version install it with the usual checksum check. From then on, Keepsake refuses any update that is unsigned or signed with another key. The first-install link keeps working. The signature check is proven against the real minisign tool (ADR-0036).

### Added

- Groundwork for Linux and Windows PCs and laptops (ADR-0038). Keepsake can now find a game's saves in a native Windows layout. A save from a handheld's Proton prefix and the same save on Windows count as the same files, so they sync between the two. The PC app that uses this comes in later releases.
- Preview for PCs: `python -m keepsake.host` runs Keepsake without Decky on Windows or Linux and serves a local page only to this computer. The full desktop interface comes next. On PCs the Installer is unavailable, because it needs Decky to create Steam shortcuts, and Advisor starts switched off (ADR-0038, ADR-0039).
- Advisor, ProtonDB (optional, off by default): ProtonDB reports from handhelds join the community reports. Reports from handhelds with your chip, such as the Z1 Extreme or Z2 Extreme, are marked as the same chip. They feed the Proton and launch-option advice, and a summary shows the share of reports that say the game works, with a link to ProtonDB. Keepsake downloads its own ProtonDB index (a few MB) once a month and looks games up on your device, so no game is named to anyone. Contains information from ProtonDB, made available under the ODbL (ADR-0035).

- Install, "From a network location": install from a NAS or web server that is not mounted. Choose Web server, enter the address (and a user name and password if it needs one), Browse its folders and pick an ISO. Keepsake downloads the ISO to this device with progress and a cancel button, resumes after a dropped connection, checks the size and an optional SHA-256, and then installs it like any ISO. The download is deleted when the install ends. "Remember this location" keeps the address, and the password stays on the device. Plain http:// works only on your local network and never with a password. If the server sends you to another host, Keepsake asks first. NFS shares still need mounting first (ADR-0033).
- Install, "From a network location", Windows share (SMB): enter `smb://nas.local/` to list a server's shares, or `smb://nas.local/Games/` to open one, with an optional user name and password. Browse, pick an ISO, and it is copied and installed the same way, reconnecting if the connection drops. Only servers on your local network, using SMB 2 or 3; SMB 1 is refused. Shares that require SMB 3 encryption cannot be used yet. This uses the pure-Python pysmb library, included with Keepsake (ADR-0034).
- Install, "From a network location", WebDAV: browse a WebDAV folder such as Nextcloud (`davs://cloud.example/remote.php/dav/files/me/Games/`) and install an ISO from it, with the same download, checks and clean-up as Web server. `dav://` without the s works only on your local network and never with a password. If an address is a plain web server, Keepsake says so (ADR-0033).

### Changed

- Cloud sign-in: Keepsake can ship its own OneDrive and Google Drive sign-in, so you pick the service, press Sign in and approve on your phone, with no client ID to enter. OneDrive is listed first and opens by default. The sign-in screen says exactly what you allow: Apps/Keepsake only on OneDrive, Keepsake's own app data only on Google Drive. Your own client ID moves under "Advanced: use my own client ID", and a client ID you already saved keeps working. The built-in clients turn on in the release that carries their IDs (ADR-0032).

## [0.24.0]

Import every game's save backups at once, games that need your approval at the top of the Games list, setup buttons clear of the Gaming Mode footer, and PCGamingWiki in Advisor.

### Added

- Import saves, "Import every game": after Read folder, import the latest backup of every game, or all backups of every game, in one go. It shows how many games and backups each will import. It shows "Importing 7 of 42: Game name" as it goes, and can stop between games. One game failing does not stop the rest, and running it again skips what is already imported. It ends with a summary, and games that failed move to the top. Games not on this device or not in the manifest are included, so their backups are ready if you install them later or play them on your other device.
- Advisor, PCGamingWiki (optional, off by default): which upscalers and frame generation a game supports, with a link to its page. Advisor warns when a report recommends an upscaler the wiki does not list. It needs your own PCGamingWiki bot password, which stays on the device.

### Changed

- Games: games whose match needs your approval come first, then any with a prefix mismatch, a conflict or a quarantined save, then the rest by name (numbers in order, so Game 2 comes before Game 10). The order is the same under every filter, and in setup's match review.
- Games: an Approve button on each row that needs it, next to Open, with the same confirmation as the game's page. "Review matches" in the banner opens the first match waiting for you.

### Fixed

- Setup: the Back, Continue and Skip setup buttons could sit under Gaming Mode's footer bar after a long game list. They now also appear at the top of every step, and the page ends clear of the footer.

## [0.23.0]

The Advisor module: tuning advice for each game, for your exact device. Advisor only recommends: it never changes a setting.

It also hardens the parsers that read outside data, which fixed several crashes on malformed input.

### Added

- Keepsake, Advisor: recommendations for the game you are playing, or any game you choose, for your exact device. It covers TDP in your tuning tool's own words, frame cap and VRR, render resolution and scaling filter, in-game preset and battery estimate. Each recommendation shows its source and confidence, and it uses Deck Verified community reports where there are any. It changes nothing: launch options are offered to copy.
- Advice in the Quick Access Menu for the running game.
- Detects your handheld (Legion Go, Legion Go 2, Steam Deck, ROG Ally and others) and your TDP and frame generation tools, and warns when two TDP tools fight. You can choose both by hand.
- Non-Steam shortcuts are matched to their Steam game through the save manifest, or by a Steam app ID you enter.
- Anti-cheat status from Are We Anti-Cheat Yet for games that have it.
- Advisor, Proton: which Proton to use and why (a community report, or for non-Steam games the newest GE-Proton you have installed), next to what the game uses now.
- Advisor, launch options from reports, explained and combined with your own, with warnings for anything that runs other programs. Copy them, then set them yourself in Steam.
- Advisor, frame generation and upscaling: the game's own upscaler and frame generation first, and lsfg-vk only when the base frame rate is 40 fps or more.
- Advisor shows what your TDP tool and lsfg-vk are set to for the game.
- Advisor is hardened against malformed community reports, anti-cheat entries and AI replies, and never suggests an FSR 4 setting in launch options, wherever it appears.
- Optional AI advice with your own Anthropic, OpenAI or Gemini key, from a button only, with a daily limit. It sends only the game's title, your device's hardware, your tools and the settings shown.

## [0.22.1]

Fixes Keepsake not starting at all on some devices.

### Fixed

- On Decky builds whose Python has no XML module, Keepsake's backend failed to start. Updates stayed on "Checking" with no version shown, and Games, the manifest update and shortcuts never loaded. Keepsake now starts normally there. Only WebDAV and S3 need the XML module, and they say so clearly if it is missing.

### Added

- Diagnostics, "Python modules in this Decky build": lists any module this Decky build lacks and what it stops.
- Troubleshooting: what to do when Updates stays on "Checking", and how to read Decky's journal.

## [0.22.0]

Keepsake v2 begins: Keepsake is now one plugin with modules. This release adds the Installer module and the module framework, alongside save sync, which works as before.

This is the first release since 0.11.0. It also contains 0.12.0, 0.13.0 and 0.21.0 below, which were not published on their own: release signature checking, the README and help guides, the module framework with Settings, Modules, and the first part of the Installer.

### Added

- Install, "Installer wants a disc drive": for ISO installs, the disc becomes a CD drive (D: or the next free letter) inside the installer's prefix. It is removed again when the install ends.
- Install: SD cards, USB drives and network shares that are already mounted appear as places to browse from. Sources and library folders outside the home folder are made visible to the installer.
- Install, "Remove the installer shortcut" for an install that stopped or was cancelled.
- Install, "Sync this game's saves" once a game is installed. Other modules are told about new games.
- Installer health in Settings, Modules: discs left mounted, installer shortcuts left behind, and Steam changes still waiting.
- Install, "Add artwork from SteamGridDB": once a game is installed, add its library artwork with your own SteamGridDB API key. Enter the key on the Install page.

### Changed

- Games, Update manifest now shows what it is doing: contacting GitHub, how much of the manifest has downloaded, how many games it has read, and saving. It also shows a weekly update that is already running, and says in words why an update failed.
- The Import tab is now Import saves, and its page says plainly that it imports save backups from Ludusavi, not installed games.

### Fixed

- A malformed entry in the Ludusavi manifest could stop the whole game list from loading its save locations. Now only that entry is skipped.
- Manifest entries with a Steam ID of `true` or `false` are no longer matched to a Steam game.

## [0.21.0]

Slice 21: the Installer module, first part.

### Added

- Keepsake, Install: install a Windows game from an ISO file or a folder without leaving Gaming Mode. Keepsake adds an `Install: <Title>` shortcut with the newest GE-Proton, shows where to install, notices when the installer closes, lists the programs it created and points the same shortcut at the one you choose, so the game keeps its Proton prefix. ISO files are mounted read-only and released when the install ends.
- Install, Change folder: where games are installed (default `~/Games`), for example a folder on the SD card.

### Changed

- Module tabs appear in the Keepsake page only while their module is running.

## [0.13.0]

Slice 13: the module framework for Keepsake v2. Saves works as before.

### Added

- Settings, Modules: each module with its switch, health and what it writes. Saves can be switched off; Advisor, Replication, Installer and Desktop are listed as coming in later versions. A module that fails is stopped on its own, with "Try again", and never affects the others.
- Diagnostics, Probe Steam APIs: checks which Steam client functions are available, without changing anything.
- The Games list knows each shortcut's launch options, compatibility tool, artwork and icon, for the modules that need them.

## [0.12.0]

Slice 12: hardening and documentation ahead of 1.0.0.

### Added

- Release signature checking: once the owner's release key is pinned in the plugin, an update without a valid signature is refused. Until then the Updates page installs with the SHA-256 check, as before.
- README with install and first-run steps, a troubleshooting guide, the cutover plan from Ludusavi, and a security review of the threat model.

### Fixed

- Background sync with many games was slow on the device's local test store, because every listing walked the whole store. With 50 games an idle pass now takes seconds instead of minutes.

## [0.11.0]

Slice 11: registry saves, Steam Cloud detection and sleep snapshots. Each has its own setting.

This is the first release since 0.2.0. It also contains everything listed under 0.3.0 to 0.10.0 below, which were not published on their own: game discovery, save locations, snapshots, OneDrive sync before launch and after exit, cross-device game matching, the full Gaming Mode interface and setup wizard, Google Drive, WebDAV and S3, and the Ludusavi import.

### Added

- Every release also carries `Keepsake.zip`, a byte-identical copy of `Keepsake-v<version>.zip`, so a first install always uses the same URL: `https://github.com/breakmylegs/keepsake/releases/latest/download/Keepsake.zip`. `SHA256SUMS` lists both names. The in-plugin updater still uses the versioned zip.

- Games that keep save data in the Proton registry can sync those keys ("Sync registry keys" on the game page, off by default). Only the keys the save-location manifest lists are touched, only while the game is closed, with a backup, and the file is checked before and after so it cannot be left damaged.
- Steam games are labelled when they use Steam Cloud, and "Sync them all" turns on Keepsake for played Steam games that have no Steam Cloud saves.
- Optional sleep snapshots: when the device goes to sleep during a game, its progress is saved. Your other device tells you about it but only uses it if you restore it from History.

## [0.10.0]

Slice 10: more cloud backends and the Ludusavi import.

### Added

- Google Drive, WebDAV (for example Nextcloud) and S3 or S3-compatible storage, chosen in Settings, Cloud. Google Drive signs in with your phone and Keepsake sees only its own hidden app folder; see `docs/setup-google.md`. WebDAV and S3 are set up with an HTTPS address and keys; see `docs/setup-backends.md`.
- Every backend is checked before use: WebDAV and S3 must refuse to overwrite files, or Keepsake will not use them.
- Import tab: bring in Ludusavi backups from a folder on this device. Each backup becomes a snapshot in History with its original date, checked against Ludusavi's records, and its paths are recognised inside any Proton prefix whatever the compatdata number. Imports never replace your current saves: restore one from History when you want it.

### Security

- Passwords, secret keys and the Google client secret are kept on the device with owner-only permissions and are never shown again.

## [0.9.0]

Slice 9: the Gaming Mode interface is complete, plus cross-device game matching.

### Added

- First-run setup: name the device, sign in, scan games, review matches, choose games, see a dry run of what the first sync will do, then confirm. Run it again from Settings.
- Quick Access Menu: health badge, cloud and last sync, the game you are playing with its sync state, open conflicts, "Sync now" and "Open Keepsake".
- Conflicts tab and a conflict window that shows each side's device, time, files, size and files changed. "Decide later" has the focus and is what the B button does; replacing a save needs two presses.
- History tab: recent snapshots across games with restore, pin and release quarantine. Each game's page shows the last sync from each device.
- Games list: sync status icons and a "Synced games" filter. Steam games are hidden unless Settings, "Show Steam games" is on, because Steam Cloud usually covers them.
- A game's aliases, config files choice, custom paths and exclusions are shared with your other devices. If both devices change them at the same time, the newest change is kept and the game page says so.
- Health checks on the Diagnostics page (sign-in, last sync, open sessions, quarantine, conflicts, prefixes, games played without Keepsake, manifest age, decky-ludusavi), included in the diagnostics export.
- Messages when a background sync finds a conflict or a suspicious save, and when OneDrive sign-in needs attention.
- Background sync interval in Settings (10 to 240 minutes) and a Modules overview.
- Keepsake recognises the same game on your other device even when the shortcut has a different name and the game sits in a differently numbered compatdata folder. It compares the program file name, install folder names and, most strongly, the save folders the other device syncs. Clear matches are applied automatically and shown with the evidence; weaker ones are offered as suggestions.
- When a match is likely but not certain, Keepsake asks: approve it, choose another, or say it is not this game (that answer is remembered).
- Games the save-location manifest does not know can be given their own game key and synced through custom folders.

### Documentation

- Slice C0: plan for Keepsake v2, one plugin with five modules (Saves, Advisor, Replication, Installer, Desktop). No change to the plugin itself. See `docs/plan.md`.

## [0.8.0]

Slice 8: lifecycle integration. Saves now sync on their own when you start and quit a game.

### Added

- When a synced game starts, Keepsake pauses it for a moment, loads a newer cloud save if there is one, and lets it continue. A watchdog always releases the game within 30 seconds.
- When the game quits, its saves go to the cloud, with a message you can switch off in Settings.
- If the cloud is slow, the game starts with the local save after the launch check timeout (Settings, 5 to 60 seconds) and the check is finished later.
- Optional strict launch gate per game: the game waits for the check before it starts. Your own launch options are kept and restored exactly when you turn it off.
- A warning when a game was played while Keepsake was not running; its saves are uploaded at the next idle pass.

## [0.7.0]

Slice 7: sync engine. Automatic sync on game launch and exit comes in slice 8; until then the game page has "Check before play" and "Save after play".

### Added

- "Sync this game" per game, and the sync rules: a newer cloud save is restored before play, new progress is saved after play, and a device that has never synced a game adopts the cloud save when it matches.
- Conflicts when both sides changed, when two devices saved from the same point, or when a device's unsynced files differ from the cloud. Choices: "Use cloud save", "Use this device's save" or "Decide later". Whichever side is not chosen is kept and pinned for at least 90 days.
- Offline play: the game always starts; checks and saves wait and are reconciled when the cloud is back.
- Every 30 minutes, for synced games: newer cloud saves are downloaded ahead of time so a restore at launch is local, changes made while Keepsake was not running are saved, and a missed exit save (for example after Steam was closed) is recovered with the message "Recovered missed exit backup".

## [0.6.0]

Slice 6: OneDrive sign-in and cloud store. Syncing on game launch and exit comes in slices 7 and 8.

### Added

- Sign in to OneDrive from Gaming Mode with your phone: Keepsake shows a code and a QR code; you finish on microsoft.com. Keepsake can only see its own folder, `Apps/Keepsake`.
- OneDrive client ID setting, with step-by-step setup in `docs/setup-entra.md`.
- Tokens refresh automatically and are stored privately on the device.
- Snapshots can go to OneDrive ("Use OneDrive for snapshots" in Settings). Uploads never overwrite anything, are checked against the hash OneDrive reports, and large files upload in resumable chunks.
- Each device registers itself once in the cloud.
- "Test connection" and "Sign out".

### Changed

- The cloud layout and snapshot format are now frozen (`docs/cloud-layout.md`).

## [0.5.0]

Slice 5: snapshot engine and safety rails. Snapshots go to a local test store on the device; the cloud comes in slice 6.

### Added

- Snapshots of a game's save files: hashed, packed into a zip and recorded with a complete file list.
- Restores are atomic: either all the new files are in place or none are, even if the device loses power mid-restore. The files present before every restore are saved first, verified, and can be put back with "Undo to this" (the last five per game).
- Safety gates: a snapshot that empties the save, removes more than half the files or shrinks by more than 70% is kept on the device as quarantined and never uploaded unless you release it. The limits can be made stricter in Settings.
- Pinning, and retention that keeps recent, daily and monthly snapshots and never removes pinned, current or manual ones.
- Game page "Snapshots (local test store)" panel to try all of this on the device.

### Security

- Snapshot zips are fully checked before anything is extracted: no unexpected paths, symlinks, oversized or encrypted entries, and every file's hash must match.

## [0.4.0]

Slice 4: manifest resolution and save preview. Still does not sync saves.

### Added

- Downloads the Ludusavi manifest of save locations, checks for changes weekly (using its ETag) and keeps a compact index on the device. "Update manifest" on the Games page refreshes it on demand.
- Each game is matched to a manifest entry by Steam ID or by title, ignoring case, punctuation, edition names such as "Game of the Year Edition" and roman numerals. Several matches are shown as a choice rather than guessed.
- Game page: matched title and game key, "Change match" with search, include config files (off by default), custom folders through the file picker, exclusions, and a preview of the files that would be synced with counts and sizes.
- Logs, crash dumps, shader and web caches and temporary files are excluded by default.
- Paths that cannot be resolved safely are skipped and listed with the reason.

### Security

- Every resolved path must stay inside its root; escaping symlinks are ignored; a game folder that is too broad (such as `/` or the home folder) is refused.

## [0.3.0]

Slice 3: discovery. Still does not sync saves.

### Added

- Games page listing non-Steam shortcuts for every Steam user (the most recent user first) and installed Steam games, with filters and a rescan button.
- Each shortcut's Proton prefix is found from its app ID in `shortcuts.vdf` (signed values converted to unsigned) across all Steam libraries, internal storage first, including SD cards.
- Steam runtimes and tools (Proton, Steam Linux Runtime, redistributables) are left out.
- "Check running prefix" compares a running game's actual prefix with the discovered one; a mismatch is remembered and will block sync for that game.
- Supports Steam in `~/.local/share/Steam`, `~/.steam` and the Flatpak location, and `/var/home` home folders as on Bazzite.

## [0.2.0]

Slice 2: release pipeline and in-plugin updater. Still does not sync saves.

### Added

- Updates page: check for updates, release notes, "Update now" and "Install this version" for any earlier release (rollback).
- "Update available" row in the Quick Access Menu and a toast when a new version is found, checked at most once a day.
- Updates are verified against the release's `SHA256SUMS` and handed to Decky Loader's own installer, which asks you to confirm and checks the hash. If this Decky version does not allow that, Keepsake shows the zip address as text and a QR code.
- "Updated to vX.Y.Z" toast after an update.
- Stable and Pre-release update channels in Settings.
- Updates are refused while a sync job runs, with an "Update when idle" option. Diagnostics has a "Simulate sync job" button to test this.
- Read-only safe mode when the settings file comes from a newer version, and settings unknown to an older version are preserved on rollback.
- `pnpm release prepare <version>` and `pnpm release publish` build, checksum, sign (with minisign when configured), tag and publish releases locally.

## [0.1.0]

Slice 1: skeleton, development loop and on-device diagnostics. Does not sync saves.

### Added

- Plugin skeleton from decky-plugin-template, with no root flag.
- Quick Access Menu panel and a full-screen Keepsake route with Diagnostics, Logs and Settings pages.
- Settings store with a device ID and an editable device name.
- Structured, redacted, rotated JSON-lines logging and a log viewer.
- Diagnostics page that records Python and module availability, Decky environment variables, Steam roots and libraries, `shortcuts.vdf` app IDs (signed and unsigned) with matching compatdata folders, the running game's process tree, Steam client lifetime, game action and suspend events, and which Decky install routes are visible.
- Freeze test that pauses the running game for 5 seconds behind a 30 second watchdog.
- Diagnostics export to the settings folder.
- `LocalFolderStore` with create-only writes.
- Local quality gate `pnpm run check` (lint, type checks, build, version consistency, packaging, ruff, mypy, secret scan) and `pnpm run test:device` to run Linux-only tests on a device over SSH. No GitHub Actions.
