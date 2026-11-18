# Changelog

All notable changes to Keepsake are listed here. Versions follow [Semantic Versioning](https://semver.org/). Each release uses its section below as release notes.

## [Unreleased]

### Added

- One-button cloud sign-in: OneDrive and Google Drive now work out of the box. Pick one, press **Sign in** and approve with your account. No client ID or app registration is needed; your own client is still available under Advanced (ADR-0055).
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
