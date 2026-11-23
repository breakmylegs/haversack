// Built by scripts/help.py from docs/user: do not edit by hand (R28, ADR-0090).
// Run `python scripts/help.py` after changing the user guide; the gate checks it is in step.
export type HelpBlock =
  | { k: "h"; l: number; t: string }
  | { k: "p"; t: string }
  | { k: "li"; d: number; t: string }
  | { k: "row"; t: string }
  | { k: "code"; t: string };

export interface HelpTopic {
  id: string;
  title: string;
  blocks: HelpBlock[];
}

export const HELP: HelpTopic[] = [
 {
  "id": "readme",
  "title": "About this guide",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Haversack user guide"
   },
   {
    "k": "p",
    "t": "Haversack keeps your PC game saves in step between your devices: SteamOS and Bazzite handhelds, Linux PCs and Windows PCs. It stores them in your own cloud storage. It never overwrites a save without asking, and every save it replaces can be brought back."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Where things are"
   },
   {
    "k": "p",
    "t": "Haversack was called Keepsake until version 0.51.0. Updating moved everything across, and nothing was lost (Updates)."
   },
   {
    "k": "p",
    "t": "Haversack's page has seven sections in its sidebar, each with its own entries:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Play:** Now playing and Advisor."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Saves:** Games, Conflicts, History, Activity, Import and export."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Games and devices:** Moving games, Other devices, Emulators, Disk use."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Device:** Device status, Power, Battery, Fans, Controllers, Reconnect help, More device settings, Looks."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Install.**"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Settings:** General, Cloud, Sync and safety, Modules, Quick menu, Updates, Help."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Diagnostics:** Health, Device checks, Tools, Logs."
   },
   {
    "k": "p",
    "t": "This guide is also in Haversack itself, under **Settings**, **Help**, so you can read it on the handheld."
   },
   {
    "k": "p",
    "t": "The quick access menu shows the game you are playing, games on their way between your devices, and anything that needs you. The desktop app has the same sections down the left."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Getting started"
   },
   {
    "k": "p",
    "t": "Pick the guide for your device:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Handheld with Decky Loader: Steam Deck, Legion Go, ROG Ally and others, on SteamOS or Bazzite."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Linux PC: a desktop or laptop, with or without Decky."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Windows PC."
   },
   {
    "k": "p",
    "t": "Set Haversack up on one device, then on the next. Games whose saves already match link up silently. Any that differ ask you which save to keep."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Guides"
   },
   {
    "k": "li",
    "d": 0,
    "t": "How syncing works: when Haversack checks the cloud and when it saves, on a handheld and on a PC."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Cloud storage and sign-in: OneDrive, Google Drive, WebDAV and S3."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Conflicts, history and restoring: choosing between two saves, and going back to an older one."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Importing from Ludusavi: bring your existing backups with you."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Storage: disk use per game, clearing a shader cache, and resetting a broken prefix without losing your saves."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Your device: live readings, performance for each game, power limits, fans, battery, controllers, reconnect help, and boot and sleep animations."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Installing games: from an ISO, a folder or a network share, on a handheld."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Advisor: recommended settings for your device. It never changes anything."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Replication: sending a whole game, or an emulator game, from one device to another."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Updates: keeping Haversack up to date, and going back a version."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Reference"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Privacy: what Haversack stores, where, and what it sends to whom."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Questions and answers."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Troubleshooting: what each message means."
   },
   {
    "k": "li",
    "d": 0,
    "t": "What changed in each version."
   },
   {
    "k": "p",
    "t": "The screenshots show sample data, not anyone's real games or devices."
   }
  ]
 },
 {
  "id": "getting-started-handheld",
  "title": "Handheld with Decky Loader",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Getting started on a handheld"
   },
   {
    "k": "p",
    "t": "For SteamOS and Bazzite handhelds with Decky Loader (github.com/SteamDeckHomebrew/decky-loader). Everything happens in Gaming Mode with the controller. You never need Desktop Mode or a terminal."
   },
   {
    "k": "h",
    "l": 2,
    "t": "1. Install Haversack"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. In Decky, open **Settings**, then **General**, and turn on **Developer mode**. You only do this once per device."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. In Decky, open **Settings**, then **Developer**, then **Install Plugin from URL**, and enter:  https://github.com/breakmylegs/haversack/releases/latest/download/Haversack.zip "
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. After that, Haversack updates itself from its own **Settings**, **Updates** tab (Updates)."
   },
   {
    "k": "h",
    "l": 2,
    "t": "2. Set it up"
   },
   {
    "k": "p",
    "t": "Open Haversack from the Quick Access Menu and choose **Set up Haversack**. The wizard has five steps:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. **Device name.** It is shown next to this device's saves on your other devices."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. **Cloud.** Choose OneDrive, Google Drive, WebDAV or S3, and sign in (Cloud storage and sign-in)."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. **Scan games** and **review matches.** Haversack finds your Steam games and non-Steam shortcuts and looks up where each one keeps its saves. Approve any match it is not sure about."
   },
   {
    "k": "li",
    "d": 0,
    "t": "4. **Choose games** to sync. Steam games are listed too. Played Steam games with no Steam Cloud saves are synced automatically; ones that use Steam Cloud stay off unless you choose them, because Steam already keeps their saves."
   },
   {
    "k": "li",
    "d": 0,
    "t": "5. **Dry run.** See what the first sync will do for each game. Nothing changes until you confirm."
   },
   {
    "k": "h",
    "l": 2,
    "t": "3. Play"
   },
   {
    "k": "p",
    "t": "That is all. Before a game starts, Haversack checks the cloud for newer saves, pausing the game for a moment. After you quit, it saves to the cloud (How syncing works)."
   },
   {
    "k": "p",
    "t": "The Quick Access Menu shows the current game's sync state, any conflicts, available updates and **Sync now**. **Open Haversack** opens the full view, with Games, Conflicts, History, Import saves, Install, Advisor, Settings, Updates, Logs and Diagnostics."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Your quick menu"
   },
   {
    "k": "p",
    "t": "Haversack's panel in the quick access menu can show what you use most. Open **Settings**, **Quick menu**:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "tick the shortcuts you want, and move them with **Up** and **Down**;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "they can be pages to open, actions that run straight from the menu, or status lines;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "shortcuts for modules you have switched off are not offered;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Open Haversack** is always there, last."
   },
   {
    "k": "h",
    "l": 2,
    "t": "In Desktop Mode"
   },
   {
    "k": "p",
    "t": "Haversack comes with a desktop app, with nothing more to install. When you switch to Desktop Mode, its icon appears in the system tray, with no window. Click it, or choose **Open Haversack** from its menu, to open Haversack in your browser; it covers the same pages as in Gaming Mode. Closing the window leaves the icon in the tray. **Quit** in the icon's menu stops it until you next log in. Haversack is also in the app menu, which brings up the one already running."
   },
   {
    "k": "p",
    "t": "If the icon's status line says Haversack's plugin cannot be reached, Decky Loader is not running in Desktop Mode: switch back to Gaming Mode once, then try again. To stop the desktop app starting, switch **Desktop** off in Settings, Modules."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Next device"
   },
   {
    "k": "p",
    "t": "Set up your next device the same way, with the same cloud account. Non-Steam games installed into their own Proton prefixes are recognised as the same game, even though their shortcut IDs and prefix folders differ on each device."
   },
   {
    "k": "p",
    "t": "Moving from Ludusavi? See Importing from Ludusavi."
   }
  ]
 },
 {
  "id": "getting-started-linux-pc",
  "title": "Linux PC",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Getting started on a Linux PC"
   },
   {
    "k": "p",
    "t": "Haversack runs on Linux desktops and laptops. With Decky Loader in Steam's Big Picture mode, follow the handheld guide instead. Without Decky, Haversack runs as a small background program with a page in your browser, as described here."
   },
   {
    "k": "p",
    "t": "The PC version is a preview: the main screens are in place, and more follow."
   },
   {
    "k": "h",
    "l": 2,
    "t": "1. Install"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. You need Python 3.11 or newer. Most distributions already have it as python3."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Download Haversack-desktop-v.zip from the latest release (github.com/breakmylegs/haversack/releases/latest) and unzip it anywhere."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. In that folder, run:  python3 install.pyw "
   },
   {
    "k": "p",
    "t": "Haversack installs into ~/.local/share/keepsake/app, adds itself to your app menu, starts when you sign in, and opens in your browser. It needs no administrator rights. The download is covered by the release's signature, which Haversack also checks on every update."
   },
   {
    "k": "li",
    "d": 0,
    "t": "To install without starting at sign-in, add --no-autostart."
   },
   {
    "k": "li",
    "d": 0,
    "t": "To remove Haversack, run python3 install.pyw --uninstall. Your settings and saves are kept."
   },
   {
    "k": "h",
    "l": 2,
    "t": "2. Set it up"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open **Cloud** and sign in (Cloud storage and sign-in). Then choose **Use... for snapshots**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Open **Games** and turn on **Sync this game** for each game you want (How syncing works)."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. In **Settings**, give this computer a name your other devices will show."
   },
   {
    "k": "h",
    "l": 2,
    "t": "What is different on a PC"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Haversack does not pause a game when it starts. Instead, it never restores a save while a game is running, and saves to the cloud a few seconds after you quit. Saves from your other devices arrive when Haversack syncs while the game is closed."
   },
   {
    "k": "li",
    "d": 0,
    "t": "The Installer needs Decky, so it is not available on a PC. Advisor starts switched off, because its advice is built for handhelds."
   },
   {
    "k": "p",
    "t": "Haversack keeps its settings in ~/.config/keepsake and its state and logs in ~/.local/state/keepsake."
   }
  ]
 },
 {
  "id": "getting-started-windows",
  "title": "Windows PC",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Getting started on Windows"
   },
   {
    "k": "p",
    "t": "Haversack runs on Windows 10 and 11 as a small background program with a page in your browser. It finds Steam for Windows, its libraries and your non-Steam shortcuts. It reads your games' saves from your Windows folders. The same game's saves from a handheld's Proton prefix count as the same files, so they sync between the two."
   },
   {
    "k": "p",
    "t": "The PC version is a preview: the main screens are in place, and more follow."
   },
   {
    "k": "h",
    "l": 2,
    "t": "1. Install"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Install Python 3.11 or newer, for example with:  winget install Python.Python.3.13 "
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Download Haversack-desktop-v.zip from the latest release (github.com/breakmylegs/haversack/releases/latest) and unzip it anywhere."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Double-click install.pyw in that folder."
   },
   {
    "k": "p",
    "t": "Haversack installs into %LOCALAPPDATA%\\Keepsake\\app, starts when you sign in to Windows, and opens in your browser. It needs no administrator rights. To open it later, run keepsake.pyw in that folder. The download is covered by the release's signature, which Haversack also checks on every update."
   },
   {
    "k": "li",
    "d": 0,
    "t": "To install without starting at sign-in, run python install.pyw --no-autostart."
   },
   {
    "k": "li",
    "d": 0,
    "t": "To remove Haversack, run python install.pyw --uninstall. Your settings and saves are kept."
   },
   {
    "k": "h",
    "l": 2,
    "t": "2. Set it up"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open **Cloud** and choose **Sign in with OneDrive** or **Sign in with Google**. Your browser opens the provider's page: sign in and allow access (Cloud storage and sign-in)."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Open **Games** and turn on **Sync this game** for each game you want."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. In **Settings**, give this computer a name your other devices will show."
   },
   {
    "k": "h",
    "l": 2,
    "t": "What is different on a PC"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Haversack never restores a save while a game is running, and saves to the cloud a few seconds after you quit (How syncing works)."
   },
   {
    "k": "li",
    "d": 0,
    "t": "The Installer needs Decky, so it is not available on Windows. Advisor starts switched off."
   },
   {
    "k": "p",
    "t": "Haversack keeps its settings in %APPDATA%\\Keepsake and its state and logs in %LOCALAPPDATA%\\Keepsake. These folders keep Haversack's former name, so an earlier install carries on where it was."
   }
  ]
 },
 {
  "id": "how-sync-works",
  "title": "How syncing works",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "How syncing works"
   },
   {
    "k": "p",
    "t": "Haversack works with snapshots. Each time a game's saves change, Haversack records a snapshot: a copy of that game's save files, identified by their content. Snapshots go to your cloud storage and are never changed afterwards. Each snapshot remembers which one it came from, so Haversack always knows whether two devices played on from the same point."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Choosing games"
   },
   {
    "k": "p",
    "t": "Turn on **Sync this game** for each game whose saves should follow you. Haversack works out where each game keeps its saves from the Ludusavi manifest (github.com/mtkennerly/ludusavi-manifest), a community list of save locations. If a game matches more than one entry, or none, pick its save data from the list or search for it."
   },
   {
    "k": "p",
    "t": "When another device has already linked a game, Haversack asks whether this is **Same game** or **A different game**. Your answer links the two, even if the shortcuts have different names."
   },
   {
    "k": "h",
    "l": 2,
    "t": "On a handheld"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Before a game starts:** Haversack pauses it for a moment, checks the cloud, and puts a newer save in place if there is one. A watchdog always resumes a paused game, whatever happens. If the check takes too long or the network is down, the game simply starts with the save it has."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**After you quit:** the new save goes to the cloud."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**While no game runs:** Haversack checks for saves from your other devices every 30 minutes (change it in Settings), and when you press **Sync now**."
   },
   {
    "k": "h",
    "l": 2,
    "t": "On a PC"
   },
   {
    "k": "p",
    "t": "A PC cannot pause a game the way Steam on a handheld lets Haversack do, so Haversack never touches a game's saves while it runs."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Heroic, Lutris, Bottles and emulators"
   },
   {
    "k": "p",
    "t": "On a handheld or a Linux PC, **Games** also lists your Heroic (GOG and Epic), Lutris and Bottles games, and one entry for each emulator whose saves Haversack knows: RetroArch, Dolphin, PCSX2, DuckStation, PPSSPP, RPCS3 and Cemu. Use the filters **Heroic, Lutris, Bottles** and **Emulators** to find them, then turn sync on like any other game."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Haversack cannot see these games start, so it saves after you play and brings in newer saves from your other devices in the background. It only does so while the game or emulator is closed, and only when you have not played on since. Otherwise it asks you."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Emulator entries sync battery and memory-card saves. **Include save states** on the game page adds save states too. They are off by default, because a save state often does not load in another version of the emulator."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Heroic can sync GOG and Epic saves itself. Use either Heroic's sync or Haversack's for a game, not both."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Settings, Show other launchers** turns these entries off."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Newer save from another device"
   },
   {
    "k": "p",
    "t": "When another device has saved a game since this one last synced it, the game's row, the Quick Access Menu and the PC Overview say so: \"Newer save from Handheld B, 10 minutes ago\". On a handheld it is brought in automatically when you start the game. **Get it now** on the game's row brings it in straight away, on a handheld or a PC. It only does so when you have not played on since; otherwise it tells you there is a conflict, and nothing is replaced."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Playtime"
   },
   {
    "k": "p",
    "t": "Each game's page shows how long you have played it across your devices, for example \"Played 12 h 30 min on your devices\", with the time on each one. Sessions under a minute and over a day are not counted. Playtime is shown for your information only, and never decides which save is kept."
   },
   {
    "k": "h",
    "l": 2,
    "t": "What Haversack will never do"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Overwrite a save without asking.** When both devices have new progress, you choose (Conflicts, history and restoring)."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Lose the save it replaces.** Before any save file is replaced, a snapshot of the current one is taken and checked, so every restore can be undone."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Let timestamps pick a winner.** Clocks on different devices disagree. Haversack compares content and history, and shows times only for your information."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Upload a save that looks broken.** If a sync would remove more than half of a game's save files, or shrink them by more than 70 percent, Haversack keeps that snapshot on the device, marks it as held back, and asks you."
   }
  ]
 },
 {
  "id": "cloud",
  "title": "Cloud storage and sign-in",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Cloud storage and sign-in"
   },
   {
    "k": "p",
    "t": "Haversack stores snapshots in your own cloud storage. There is no Haversack server."
   },
   {
    "k": "row",
    "t": "Service  |  What Haversack can see"
   },
   {
    "k": "row",
    "t": "OneDrive (personal Microsoft account)  |  Only the Apps/Keepsake folder in your OneDrive, never your other files. It keeps Haversack's former name, so every device, updated or not, uses the same folder."
   },
   {
    "k": "row",
    "t": "Google Drive  |  Only Haversack's own hidden app folder, never your files"
   },
   {
    "k": "row",
    "t": "WebDAV, for example Nextcloud  |  The folder you give it"
   },
   {
    "k": "row",
    "t": "S3 or an S3-compatible service  |  The bucket and folder you give it"
   },
   {
    "k": "h",
    "l": 2,
    "t": "Signing in to OneDrive or Google Drive"
   },
   {
    "k": "p",
    "t": "Choose **Sign in with OneDrive** or **Sign in with Google**. A browser opens the provider's own page. Sign in with your normal account and allow access for Haversack. From then on Haversack keeps itself signed in. You are only asked again if you, or the provider, withdraw its access."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**On a PC:** your usual browser opens in a new tab."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**On a handheld in Gaming Mode:** Steam's browser opens where the provider allows it. Google does not allow sign-in inside Steam's browser, so Google shows a code and a QR code instead: scan it with your phone, sign in there and enter the code. A switch lets you choose the browser or your phone for each service. If a browser sign-in does not finish, **Use your phone instead** is one press away."
   },
   {
    "k": "p",
    "t": "Check that the page is on microsoft.com, live.com or google.com and names Haversack before you sign in."
   },
   {
    "k": "p",
    "t": "Each device signs in for itself. You can sign one device out, at the provider or with **Sign out** in Haversack, without affecting the others."
   },
   {
    "k": "h",
    "l": 3,
    "t": "Using your own app registration"
   },
   {
    "k": "p",
    "t": "From version 0.26.0, Haversack includes its own sign-in, so most people never need this. Version 0.25.0 and earlier need your own app registration. Under **Advanced: use my own client ID** you can use your own Microsoft or Google app registration instead of Haversack's: see setting up Microsoft Entra and setting up Google."
   },
   {
    "k": "h",
    "l": 2,
    "t": "WebDAV and S3"
   },
   {
    "k": "p",
    "t": "Enter the address, user name and password (or access keys) on the Cloud page in Gaming Mode. The server must refuse to overwrite existing files, which Haversack checks before using it. See WebDAV and S3 set-up."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Directly between my devices (no cloud account)"
   },
   {
    "k": "p",
    "t": "If you would rather not use a cloud account, your devices can keep your saves in step with each other directly."
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Switch on **Replication** in Settings, **Modules**, and pair your devices in **Other devices**. See Replication."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. On each device, open the Cloud page, choose **Directly between my devices**, and press **Use Directly between my devices for snapshots**."
   },
   {
    "k": "p",
    "t": "Each device then keeps its own copy of your saves' history. When your devices can reach each other, each one fetches what it is missing:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "before a game starts;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "when the other device has just saved;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "now and then while Haversack is idle;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "whenever you press **Sync now**."
   },
   {
    "k": "p",
    "t": "If the other device is off or away, you play on with the saves this device has, and they meet the next time both are on. If you played on both in between, Haversack shows a conflict and you choose, as with a cloud store."
   },
   {
    "k": "p",
    "t": "There is no copy away from your devices. If you lose all of them, the history goes too. A cloud store gives you that off-site copy."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Choosing where snapshots go"
   },
   {
    "k": "p",
    "t": "After signing in, choose **Add... as a save location**. Haversack tests the connection first. Until you add one, snapshots stay in a test store on the device."
   },
   {
    "k": "p",
    "t": "You can use several save locations at once, for example OneDrive, directly between your devices, and a NAS over WebDAV. Every snapshot goes to each of them, so you have extra copies:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "If one location cannot be reached, the others still get the snapshot, and that location is caught up later by itself. A location that is down never stops you playing."
   },
   {
    "k": "li",
    "d": 0,
    "t": "When a game starts, Haversack looks at what all of them hold together."
   },
   {
    "k": "li",
    "d": 0,
    "t": "The Cloud page lists each location with when it was last reached, how much is still to copy to it, and the space it uses. **Remove** stops using a location; nothing stored there is deleted."
   },
   {
    "k": "li",
    "d": 0,
    "t": "On a game's page, **Save locations for this game** lets that game use only some of them."
   }
  ]
 },
 {
  "id": "conflicts-and-history",
  "title": "Conflicts, history and restoring",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Conflicts, history and restoring"
   },
   {
    "k": "h",
    "l": 2,
    "t": "Conflicts"
   },
   {
    "k": "p",
    "t": "A conflict means a game's saves changed on two devices since they last agreed. For example, you played on your handheld on the train while your PC was offline, then played on the PC too. Haversack cannot know which progress you want, so it asks."
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open **Conflicts** and choose **Compare and choose**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Haversack shows each side: the device, when its save last changed, how many files and the size. It also lists each file that is new, gone or changed on that side since the two devices last agreed. Haversack never picks for you by date, unless you turn on Take the newest (below)."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Choose **Keep this device's save** or **Use the save from...**, then press again to confirm. Or choose **Decide later**."
   },
   {
    "k": "p",
    "t": "The save you do not choose is kept in History and pinned, so you can always go back to it. Until you choose, Haversack does not sync that game, and the game stays playable with the save it has."
   },
   {
    "k": "h",
    "l": 3,
    "t": "Take the newest instead"
   },
   {
    "k": "p",
    "t": "If you would rather not be asked, set **Settings**, **Sync and safety**, **When saves differ** to **Take the newest**. Haversack then keeps the newer version by itself, but only when it can be sure:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "exactly two versions differ;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "they are at least 2 minutes apart;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "no device's clock looks wrong."
   },
   {
    "k": "p",
    "t": "If it cannot be sure, it asks you as before and says why. The version it did not keep stays pinned in the game's History, where **Undo** brings it back."
   },
   {
    "k": "h",
    "l": 2,
    "t": "History"
   },
   {
    "k": "p",
    "t": "Every snapshot of every game is listed in **History**, newest first, with the device it came from."
   },
   {
    "k": "p",
    "t": "On a handheld, open a game in **Games** to see its snapshots and:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Restore** an older snapshot. Haversack first takes a snapshot of the current save, so you can undo the restore."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Restore some files**: see what restoring that snapshot would change, file by file, and restore only the files you choose. Every other file stays as it is, and this can be undone too."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Save checkpoint**: keep a named copy of the current save, for example \"Before the final boss\". Checkpoints are pinned, so they are kept until you remove them. While you play, **Save checkpoint** is also in the Quick Access Menu. Save in the game first."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Undo restore** to go back to the save you had before."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Pin** a snapshot so it is never cleaned up."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Release** a held-back snapshot after checking it, so it can be uploaded."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Activity"
   },
   {
    "k": "p",
    "t": "**Activity** lists what Haversack did, newest first, in plain words: saves sent to the cloud, saves brought in from your other devices, checkpoints, restores and anything that needs your choice. The detailed log stays in **Logs**."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Checking the cloud copies"
   },
   {
    "k": "p",
    "t": "Once a week, Haversack checks that the cloud copies of each game's important snapshots are intact: the newest ones, the pinned ones, and the ones each device synced from. **Check cloud integrity** in Diagnostics (handheld) or on the Health page (PC) checks every snapshot at once. If a copy is damaged or missing, Health says so and the game's History offers **Repair**, which saves a fresh copy of your current save. Your save on the device is never affected."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Exporting your saves"
   },
   {
    "k": "p",
    "t": "You can take your saves out of Haversack at any time. In **Saves**, **Import and export**, **Export snapshots** copies them as plain zip files to a folder you choose, such as an SD card or a USB drive: either the latest snapshot of each game, or every snapshot. The export folder also holds a list of what each zip contains, and a short note explaining the folder names inside the zips. Nothing already in that folder is overwritten."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Clean-up"
   },
   {
    "k": "p",
    "t": "Haversack thins out old snapshots over time. It always keeps:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the last 10 automatic snapshots;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "one a day for 30 days;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "one a month for 12 months."
   },
   {
    "k": "p",
    "t": "It never removes:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "a pinned snapshot, including the save you did not choose in a conflict;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the newest snapshot of each game, and the point each device last synced from;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "anything younger than 7 days;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "snapshots you made by hand, merges, and imported backups."
   },
   {
    "k": "p",
    "t": "Only the saved files of an old snapshot are removed. A small record of it stays, so Haversack can still follow each save's history."
   }
  ]
 },
 {
  "id": "import-ludusavi",
  "title": "Importing from Ludusavi",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Importing from Ludusavi"
   },
   {
    "k": "p",
    "t": "If you used Ludusavi (github.com/mtkennerly/ludusavi) before, Haversack can bring its backups into Haversack's history, so nothing from before is lost. Your Ludusavi backups are only read, never changed."
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open **Saves**, **Import and export** (handheld) or **Import** (PC)."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Enter the folder of your Ludusavi backups (~/ludusavi-backup by default) and choose **Find backups**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Haversack lists each game with the number of backups it found."
   },
   {
    "k": "li",
    "d": 0,
    "t": "4. Choose **Import the latest backup of each game**, or **Import every backup** to bring the whole history."
   },
   {
    "k": "p",
    "t": "The import runs in the background with progress, and **Stop importing** stops it between games. Importing the same backup twice does nothing the second time."
   },
   {
    "k": "p",
    "t": "Imported snapshots appear in History like any other. They do not change the saves on your device: Haversack treats them as history to restore from when you want."
   },
   {
    "k": "p",
    "t": "Moving over from a Ludusavi and rclone setup on two handhelds? The step-by-step plan is in the cutover guide."
   }
  ]
 },
 {
  "id": "storage",
  "title": "Storage",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Storage"
   },
   {
    "k": "p",
    "t": "Haversack's **Disk use** tab (in **Games and devices**), on a handheld, shows how much space each game uses: the game, its Proton prefix, its shader cache and its saves. **Count disk use** lists the biggest first. Quit a game before changing anything here."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Clear the shader cache"
   },
   {
    "k": "p",
    "t": "**Clear shader cache** frees the space Steam uses for a game's compiled shaders. Steam builds them again the next time the game runs, so the first minutes may stutter. Your saves are not touched."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Reset a broken prefix and keep your saves"
   },
   {
    "k": "p",
    "t": "When a game stops starting because its Proton prefix is broken, **Reset prefix, keep saves** gives it a fresh one without losing your progress:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Haversack keeps a checked copy of the game's saves, then moves the prefix aside. Nothing is deleted."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Start the game once and quit at the title screen. Steam builds a fresh prefix."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. When you quit, Haversack puts your saves back into the fresh prefix."
   },
   {
    "k": "li",
    "d": 0,
    "t": "4. Once the game works, **Delete old prefix** frees the space of the old one."
   },
   {
    "k": "p",
    "t": "Until step 3, **Undo reset** puts the old prefix back exactly as it was. Haversack will not reset a game that is installed inside its own prefix, because that would move the game itself."
   }
  ]
 },
 {
  "id": "device",
  "title": "Your device",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Your device"
   },
   {
    "k": "p",
    "t": "Haversack's **Device** section shows your handheld, and lets you choose its performance for each game. It is built for the Legion Go and Legion Go 2, and works on any SteamOS or Bazzite device where Valve's steamos-manager runs."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Status"
   },
   {
    "k": "p",
    "t": "**Device**, **Device status** shows:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the model Haversack recognised;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "its power range and screen;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the battery and charging;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "live readings, every 2 seconds:"
   },
   {
    "k": "li",
    "d": 1,
    "t": "temperatures;"
   },
   {
    "k": "li",
    "d": 1,
    "t": "fan speed;"
   },
   {
    "k": "li",
    "d": 1,
    "t": "power;"
   },
   {
    "k": "li",
    "d": 1,
    "t": "Lenovo's performance mode;"
   },
   {
    "k": "li",
    "d": 1,
    "t": "the BIOS version;"
   },
   {
    "k": "li",
    "d": 1,
    "t": "CPU boost and threads."
   },
   {
    "k": "p",
    "t": "Haversack only reads these."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Power"
   },
   {
    "k": "p",
    "t": "**Device**, **Power** has:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Mode:** Quiet, Balanced, Performance or Custom. On the Legion Go these are the same modes as Legion L + Y."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**TDP:** the power limit in watts. Setting it switches to Custom, the only mode where the firmware uses it."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**CPU boost:** on or off."
   },
   {
    "k": "p",
    "t": "While a game runs, what you choose is kept for that game and applied each time you start it. When you quit, Haversack puts back what was there before. The same controls are in the quick access menu, under **Now playing**."
   },
   {
    "k": "p",
    "t": "Haversack never fights another tool:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "If SimpleDeckyTDP, PowerControl, LegionGo2Companion, Legion Go Toolbox, Legion Center or Handheld Daemon manages performance, Haversack only shows the settings, and says which tool is in charge."
   },
   {
    "k": "li",
    "d": 0,
    "t": "If Steam's own performance settings change something Haversack set, Haversack leaves Steam's value until you next start the game."
   },
   {
    "k": "p",
    "t": "Haversack changes these settings through Valve's steamos-manager, and never needs root."
   },
   {
    "k": "h",
    "l": 3,
    "t": "Separate power limits"
   },
   {
    "k": "p",
    "t": "With the Haversack Helper installed, **Device**, **Power** also has **Separate power limits**:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**SPL** is the sustained power;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**SPPT** is the slow boost;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**FPPT** is the fast boost."
   },
   {
    "k": "p",
    "t": "Move the sliders, then select **Apply**. Haversack switches to Custom mode first, because the firmware ignores the limits in any other mode. With a game running, the limits are kept for that game, like the TDP."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Fans"
   },
   {
    "k": "p",
    "t": "**Device**, **Fans** shows the temperature and fan speed. With the Haversack Helper installed:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Legion Go 2:**"
   },
   {
    "k": "li",
    "d": 1,
    "t": "Switch on **Haversack controls the fan**, then edit a curve: each point is a temperature and a fan speed."
   },
   {
    "k": "li",
    "d": 1,
    "t": "Save it, make it the default, or use it in the current performance mode or for the game you are playing."
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Smooth curve** blends between points; off, each point's speed holds until the next."
   },
   {
    "k": "li",
    "d": 1,
    "t": "The fan speeds up at once and slows down gently. At 101 °C it runs at full speed whatever the curve says."
   },
   {
    "k": "li",
    "d": 1,
    "t": "If Haversack stops, the fan goes back to the firmware within seconds. **Hand back** does it straight away."
   },
   {
    "k": "li",
    "d": 1,
    "t": "On a BIOS other than RRCN16WW with EC 1.16, run **the fan test** first. It takes about 15 seconds."
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Unlock wider limits** lets curves reach 5200 RPM. It is off by default, because it is louder and wears the fan more."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Legion Go:**"
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Full fan speed** (kernel 7.2 and later)."
   },
   {
    "k": "li",
    "d": 1,
    "t": "The Legion Go's own fan table needs a kernel module SteamOS does not include, so curves are not offered yet."
   },
   {
    "k": "p",
    "t": "If another fan tool is installed (or Handheld Daemon is running), Haversack only shows the readings."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Battery"
   },
   {
    "k": "p",
    "t": "**Device**, **Battery** has **Stop charging at 80%**, Lenovo's charge limit. It keeps the battery healthier if the device is plugged in for long spells. The same toggle is in the quick access menu."
   },
   {
    "k": "p",
    "t": "Haversack changes it through Valve's steamos-manager. Where steamos-manager does not offer it yet, Battery shows whether the limit is on and tells you where to change it: Steam's settings, Power."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Controllers"
   },
   {
    "k": "p",
    "t": "**Device**, **Controllers** shows each controller's battery, the settings the controllers report, and the stick lights. Remap buttons, set dead zones and use the gyro in Steam's controller settings."
   },
   {
    "k": "p",
    "t": "With the Haversack Helper installed, you can also change:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**the controllers' own settings:** mode, button chords, rumble and its style, FPS mouse DPI, how soon each controller sleeps, the left gyro, the touchpad and its haptics;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**the stick lights:** on or off, effect, brightness, speed and colour (select **Apply colour**)."
   },
   {
    "k": "p",
    "t": "Leave **Keep my changes** on, and Haversack applies them again when the controllers reconnect or the device wakes. This needs kernel 7.1 or later; on the Legion Go it also needs Lenovo's 2025 controller firmware. If Handheld Daemon is running, Haversack only shows the settings. If InputPlumber is installed, it keeps the button chords and touchpad haptics."
   },
   {
    "k": "p",
    "t": "The power LED cannot be changed: every known way needs a kernel module or memory access that Haversack will not use."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Reconnect help"
   },
   {
    "k": "p",
    "t": "**Device**, **Reconnect help** is for Bluetooth controllers, often clones, that pair once and then will not reconnect when you press their normal button."
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Pair the controller in Steam's Bluetooth settings."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Find it in the list and turn on help for it. Help acts only on the controllers you turn it on for."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Select **Help options**:"
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Pair and commit** (on by default): the next time you pair this controller, Haversack connects to it at once, so that it saves the pairing. Forget it and pair it again after turning help on."
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Reconnect**: put the controller in pairing mode (on a DualShock 4, hold Share and PS until the light flashes quickly), then select Reconnect. This is also in the quick menu."
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Diagnose**: turn the controller off, wait 10 seconds, select **Start** and press the controller's normal button once. Haversack says what went wrong and what to try."
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Read stored host over USB** (DualShock 4 on a USB data cable): whether the controller will call this handheld."
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Export report bundle**: the last diagnosis and the Bluetooth journal lines in a zip, to share on an issue. This handheld's address is replaced."
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Full report mode** (DualShock 4 only): for clones that send reduced reports, such as a missing touchpad or motion."
   },
   {
    "k": "p",
    "t": "The desktop app has the same page under Device, Reconnect help. Install the Haversack Helper from Gaming Mode."
   },
   {
    "k": "p",
    "t": "The list also shows a note when a controller's address is not from a registered manufacturer. That is only information: Haversack never acts on it."
   },
   {
    "k": "p",
    "t": "If a controller connects and drops at once, Haversack suggests a diagnosis. It does nothing to the controller unless you choose."
   },
   {
    "k": "h",
    "l": 3,
    "t": "The Haversack Helper: cable pairing and the SSP gate"
   },
   {
    "k": "p",
    "t": "The lasting fixes need root, so they run in a small separate plugin, the **Haversack Helper**. Select **Install helper** at the top of Reconnect help. Haversack checks the helper's signature, and Decky asks you to confirm. After each Haversack update, select **Update helper**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Cable pairing** (DualShock 4 and clones using its IDs):"
   },
   {
    "k": "li",
    "d": 1,
    "t": "1. Connect the controller with a USB data cable."
   },
   {
    "k": "li",
    "d": 1,
    "t": "2. Open its Help options and select **Cable pair**, then **Confirm**. Bluetooth restarts, so every Bluetooth device drops for a few seconds. It never runs during a game."
   },
   {
    "k": "li",
    "d": 1,
    "t": "3. Unplug the controller, turn it off, and press PS. If it still fails, try once more with **Reversed key order**. **Restore backup** puts back the pairing from before."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**SSP gate:** offered when the diagnosis says the controller is refused while security starts. It lowers Bluetooth security for the whole adapter, so it asks twice. Secure Simple Pairing comes back on while you pair, when you switch the gate off, and by itself if Haversack stops."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Bluetooth capture:** with the helper, Diagnose also records 40 seconds of Bluetooth traffic, to tell the causes apart."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Other"
   },
   {
    "k": "p",
    "t": "**Device**, **More device settings** has:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Wi-Fi power saving**, through steamos-manager. Turn it off if streaming or online games stutter."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**A BIOS check**, with what is known about your Legion Go's BIOS version."
   },
   {
    "k": "p",
    "t": "Refresh rate, frame limit and brightness stay in Steam's own quick access menu."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Looks"
   },
   {
    "k": "p",
    "t": "**Device**, **Looks** changes the videos Steam plays when the device starts and when it goes to sleep. First switch on **Looks** in **Settings**, **Modules**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Put WebM videos in your **Videos** or **Downloads** folder. Animation Changer's sets are offered too."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. For **Boot**, **Sleep** or **Sleep from the loading screen**, choose a video. It shows the next time the device starts or sleeps."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. **Use Steam's own** goes back."
   },
   {
    "k": "p",
    "t": "Nothing is lost:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "If a video was already there, Haversack keeps a copy first, and **Use Steam's own** puts that one back."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Haversack never removes a video another tool put there."
   },
   {
    "k": "li",
    "d": 0,
    "t": "While Animation Changer is installed, Haversack only shows the videos and leaves them to it."
   },
   {
    "k": "p",
    "t": "The page also lists the themes and sound packs that **CSS Loader** and **Audio Loader** have installed. Haversack does not change themes or sounds itself; install those plugins from Decky's store."
   },
   {
    "k": "h",
    "l": 3,
    "t": "Sending looks to your other handheld"
   },
   {
    "k": "p",
    "t": "With Replication on and your handhelds paired, **Send to your other handheld** at the bottom of Looks sends any of:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "your CSS Loader themes;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "your Audio Loader sound packs;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the animations you chose above."
   },
   {
    "k": "p",
    "t": "The other handheld keeps everything it already has. Only themes and packs it lacks are added, where CSS Loader and Audio Loader find them. Videos arrive as choices on its own Looks page, so its screen only changes when someone picks one there. The other handheld needs Looks switched on, and Haversack 0.54.0 or later."
   }
  ]
 },
 {
  "id": "installer",
  "title": "Installing games",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Installing games"
   },
   {
    "k": "p",
    "t": "On a handheld, Haversack's **Install** page installs a Windows game into its own Steam shortcut and Proton prefix, all from Gaming Mode. It needs Decky, so it is not available on a PC."
   },
   {
    "k": "p",
    "t": "**An installer is a Windows program that runs with your user's rights. A Proton prefix is not a sandbox.** Only install software you trust."
   },
   {
    "k": "h",
    "l": 2,
    "t": "From an ISO or a folder"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open **Install** and choose the ISO file or the folder holding the installer."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Haversack mounts the ISO (read-only, no root needed) and adds a shortcut called Install: that runs the installer, with the recommended Proton version."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Start that shortcut. When the installer asks where to install, type the folder Haversack shows, for example Z:\\home\\deck\\Games\\."
   },
   {
    "k": "li",
    "d": 0,
    "t": "4. Finish the installer and quit."
   },
   {
    "k": "li",
    "d": 0,
    "t": "5. Back in Haversack, choose the game's program from the list. Haversack ranks the new programs, leaving out uninstallers and setup tools. Then confirm."
   },
   {
    "k": "li",
    "d": 0,
    "t": "6. The same shortcut now starts the game, keeps its prefix, and is named after the game. Haversack offers to sync its saves."
   },
   {
    "k": "p",
    "t": "If an installer asks for the disc, press **Installer wants a disc drive** and start the installer again. Haversack gives the prefix a CD drive pointing at the mounted ISO."
   },
   {
    "k": "h",
    "l": 3,
    "t": "Games on several discs"
   },
   {
    "k": "p",
    "t": "Keep the discs' ISO files together in one folder and start with disc 1. When the installer asks for the next disc, press **Swap to ** on the Install page, then carry on in the installer. Haversack puts that disc in the drive without stopping the installer."
   },
   {
    "k": "h",
    "l": 3,
    "t": "Several installs in a row"
   },
   {
    "k": "p",
    "t": "Start another install while one is under way, and it joins the queue. Each queued install starts by itself when the one before it ends, and the queue carries on after a restart."
   },
   {
    "k": "h",
    "l": 3,
    "t": "Runtimes the game ships"
   },
   {
    "k": "p",
    "t": "If the game comes with runtime installers, such as Visual C++, DirectX or.NET, the Install page lists them when you choose the game's program. Proton already provides most of these, so only run one if the game will not start."
   },
   {
    "k": "h",
    "l": 2,
    "t": "From a network location"
   },
   {
    "k": "p",
    "t": "Choose **From a network location** to install from a NAS or server that is not mounted:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Web server:** https:// addresses anywhere. Plain http:// only on your local network, and never with a password."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Windows share (SMB):** press **Find shares** to list the Windows PCs, NAS boxes and Macs sharing folders on your network, then pick one to see its shares. Or type an address: smb://nas.local/ lists the shares, and smb://nas.local/Games/ opens one. SMB 2 or 3 on your local network only. If nothing is found, your network may block the search (some mesh and guest Wi-Fi do); typing the address still works."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**WebDAV:** for example davs://cloud.example/remote.php/dav/files/me/Games/."
   },
   {
    "k": "p",
    "t": "Browse to an ISO and pick it. Haversack downloads it with progress and a cancel button, resumes after a dropped connection, checks it, and installs it as above. The download is deleted when the install ends. **Remember this location** keeps the address; the password stays on the device."
   },
   {
    "k": "p",
    "t": "NFS shares still need mounting first, for example by opening them in Dolphin in Desktop Mode. They then appear on the Install page."
   },
   {
    "k": "p",
    "t": "An ISO on a share that is already mounted is opened where it is, with nothing copied. If the share does not allow that, Haversack copies the ISO to the device first, by itself, shows the progress, and installs from the copy. Installing straight from a share that is not mounted, without downloading first, is coming once a system tool it needs is approved; until then the ISO is downloaded as above."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Artwork"
   },
   {
    "k": "p",
    "t": "With your own SteamGridDB (www.steamgriddb.com) API key in Settings, Haversack can find artwork for the new shortcut. Your key is never sent anywhere except SteamGridDB."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Artwork for streaming tiles"
   },
   {
    "k": "p",
    "t": "Steam lists non-Steam games installed on your other devices as streaming tiles, with no artwork. At the bottom of **Install**, **Artwork for streaming tiles** lists them. Press **Find artwork**, pick the game on SteamGridDB (your SteamGridDB key, set up as for installed games), and Haversack sets the tile's artwork through Steam."
   }
  ]
 },
 {
  "id": "advisor",
  "title": "Advisor",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Advisor"
   },
   {
    "k": "p",
    "t": "Advisor recommends settings for the game you are playing or have selected, tuned to your device. **It never changes anything.** It shows advice, says where each piece came from and how sure it is, and lets you copy launch options."
   },
   {
    "k": "p",
    "t": "It is on by default on a handheld. On a PC it starts switched off, because its advice is built for handhelds. Turn it on under **Modules**."
   },
   {
    "k": "h",
    "l": 2,
    "t": "What it recommends"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Power:** the TDP to set, in the terms of the tool you use."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Display:** the refresh rate and frame cap, with VRR where your screen has it."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Scaling:** the game's own upscaler first, then the gamescope filter. Frame generation (lsfg-vk) only when the base frame rate is high enough."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**The game's own preset**, plus the Proton version and launch options."
   },
   {
    "k": "p",
    "t": "On a machine without a battery, such as a Steam Machine or a desktop, Advisor leaves out battery estimates. If it has no profile for the machine, it suggests no TDP, because the machine's power limits are unknown."
   },
   {
    "k": "p",
    "t": "Advisor recognises your device from its hardware (for example the Legion Go and Legion Go 2) and the tools you have installed, such as TDP tools, lsfg-vk and OptiScaler. It only reads them."
   },
   {
    "k": "h",
    "l": 2,
    "t": "How your games ran on this device"
   },
   {
    "k": "p",
    "t": "While you play, Advisor quietly measures how the game runs on this device: frame rate, power use, battery drain, CPU and GPU load, clocks, temperatures and whether it throttled, along with the TDP and Proton version you used. There is nothing to set up, and it only reads what the system already reports; it never changes the game. After you quit, the game's Advisor page shows a **Last session** card and your **Recent sessions**, even when the game is not running."
   },
   {
    "k": "p",
    "t": "These measurements feed the advice, marked \"Measured on this device\", and they count for more than community reports. For example: the frame rate dropped well under your frame cap, so lower the cap or raise the TDP; the GPU was flat out while the CPU idled, so lower the resolution or use FSR; you got the same frame rate at a lower TDP, so save the battery; or it throttled after 20 minutes."
   },
   {
    "k": "p",
    "t": "The frame rate comes from Steam's own performance overlay, or from MangoHud's logs if you already log with MangoHud. If neither is available, the card says \"frame rate not available\" and everything else is still measured. Only a summary of each session is kept, the last 20 per game, on this device only. If you ask for an AI explanation, only plain numbers from them are sent, never names, paths or launch options."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Where its advice comes from"
   },
   {
    "k": "p",
    "t": "Each source can be switched off, and each is contacted only while it is on:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Deck Verified** community reports, from deckverified.games."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**PCGamingWiki**, using your own PCGamingWiki bot password."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**ProtonDB** reports, from Haversack's own monthly index. Games are looked up on your device, so no game is named to anyone."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Are We Anti-Cheat Yet**, to warn about games whose anti-cheat blocks Proton."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Optional AI explanations"
   },
   {
    "k": "p",
    "t": "If you add your own Anthropic, OpenAI or Google Gemini API key and turn that provider on, Advisor can explain its advice in plain words. A request carries only:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the game's title;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "your device's hardware profile;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "your tool versions;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the settings being discussed."
   },
   {
    "k": "p",
    "t": "Nothing else is sent, and nothing is sent until you press the button. Without a key, Advisor gives the same advice from its own rules."
   }
  ]
 },
 {
  "id": "replication",
  "title": "Replication",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Replication: your devices"
   },
   {
    "k": "p",
    "t": "Replication links your own devices directly: handhelds, Linux PCs and Windows PCs. It pairs them, then sends non-Steam games between them: a game you set up on one handheld appears on the other, playable, with the same Proton version, artwork and launch options."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Switch it on"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open Haversack, then **Settings**, then **Modules**, and switch on **Replication**. **Games and devices** then has **Moving games** and **Other devices**. On a PC, it is the **Moving games and devices** page."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. On **Other devices**, switch on **Let other devices reach this one**. Until you do, nothing on your network can connect to this device."
   },
   {
    "k": "p",
    "t": "Do this on each device you want to link. You need no SSH, keys or accounts."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Pair two devices"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. On the other device, switch on **Let other devices reach this one** under Other devices."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. On the device you are holding, press **Find devices**, choose the other one and press **Pair**. If it is not listed, for example over a VPN, type its address under **Pair by address**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. The other device shows \"*name* wants to pair\", with the address it came from. Press **Accept** if it is your own device; **Decline** if you do not recognise it. If a game is running there, you get a notification instead, and the request waits under Other devices."
   },
   {
    "k": "li",
    "d": 0,
    "t": "4. It then shows a 6-digit code. Type that code on the first device with the number pad and press **OK**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "5. Both show **Paired**. If the code was wrong, both say so and nothing is paired; start again."
   },
   {
    "k": "p",
    "t": "Pairing is trust both ways. When it finishes, the device you started from can be reached too, so games can go in either direction. \"Let other devices reach this one\" switches that off again."
   },
   {
    "k": "p",
    "t": "The code is new each time and only works for that attempt. A device that keeps getting it wrong, or keeps asking, is locked out for ten minutes."
   },
   {
    "k": "p",
    "t": "Each device you pair is linked to every other one you pair, so a group such as two handhelds and a PC works."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Paired devices"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Check** connects and shows the round trip. Over a VPN it says when the link looks slow, which can mean the VPN is relaying it."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Wake** sends a Wake-on-LAN signal. It usually wakes a PC on a cable. A handheld asleep on Wi-Fi usually cannot be woken this way."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Remove** forgets a device. It can no longer connect until you pair it again."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Send a game"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. On the device that has the game, open it in **Saves**, **Games** and press **Send to **."
   },
   {
    "k": "li",
    "d": 1,
    "t": "Haversack first asks the other device whether the game fits, and stops at once if it does not, for example \"Legion Go 2 doesn't have enough space: needs 41.2 GiB, has 12.0 GiB free\"."
   },
   {
    "k": "li",
    "d": 1,
    "t": "It then checks every file, which takes a few minutes for a large game."
   },
   {
    "k": "li",
    "d": 1,
    "t": "If Saves syncs the game, the newest saves go first."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. The other device starts copying by itself, with a toast. There is nothing to accept."
   },
   {
    "k": "li",
    "d": 1,
    "t": "If that device lacks the game's compatibility tool (a GE-Proton version, for example), Haversack copies it too. Steam finds a copied tool after a restart."
   },
   {
    "k": "li",
    "d": 1,
    "t": "Launch options that only make sense on the first device, such as a mounted disc, stay behind, and Haversack lists them."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Haversack copies the game, adds it to Steam with the same name, program, launch options, Proton version and artwork, and says when it is ready. If Saves synced the game, it carries on with the same saves, with no conflict."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Get a game from another device"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. On **Other devices**, press **Games on **. Its non-Steam games are listed."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Choose one and press **Get this game**. Haversack checks there is room on this device first."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. The other device sends it as if you had pressed Send there, and shows a toast that the game is being copied from it. The same rules apply: nothing here is replaced, a missing compatibility tool is copied, and the game is added to Steam."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Watch it move"
   },
   {
    "k": "p",
    "t": "Every game on its way, in either direction, has a bar on both devices:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "under **Moving games**;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "as a short line in the quick access menu;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "in the desktop app's table."
   },
   {
    "k": "p",
    "t": "Each bar shows the percentage done, GiB done of the total, the speed, the time left and the stage:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Checking space;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Preparing;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Copying;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Verifying;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Adding to Steam;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Done, or Failed with the reason."
   },
   {
    "k": "p",
    "t": "Several games each get their own bar. The bars carry on if you close Haversack and open it again."
   },
   {
    "k": "p",
    "t": "**Stop and remove** works on either device and asks you first:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**On the receiving device** it deletes everything that copy made there: its folder, its prefix, a copied tool and its Steam shortcut. Nothing else is touched."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**On the sending device** it asks the receiving device to do the same, and then stops offering the game."
   },
   {
    "k": "p",
    "t": "**Clear** tidies a finished or failed bar away. A finished game stays. A failed copy is removed, as Stop and remove does."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Keep a game in step"
   },
   {
    "k": "p",
    "t": "Once a game has been sent, each device knows the other has it. When it changes on one device, for example after a patch or a mod, Haversack notices when you quit the game."
   },
   {
    "k": "li",
    "d": 0,
    "t": "On the game's page in Haversack, **Updates** sets what happens:"
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Ask me** (the default) shows **Send update**;"
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Take them by themselves** sends and applies updates without asking;"
   },
   {
    "k": "li",
    "d": 1,
    "t": "**Off** stops keeping it in step."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Check now** looks for changes straight away. A big game takes a while."
   },
   {
    "k": "li",
    "d": 0,
    "t": "On the other device, the update appears under **Moving games**. **Apply update** takes it, and **Keep mine** leaves that device's copy as it is."
   },
   {
    "k": "li",
    "d": 0,
    "t": "If the game changed on both devices, Haversack changes nothing and asks you. **Take theirs** replaces this device's copy with the other's, and **Keep mine** keeps it."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Stop update** stops an update part way. The game stays exactly as it was."
   },
   {
    "k": "p",
    "t": "Your saves and settings on each device are never replaced by an update, whichever you choose. Saves looks after them."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Firewalls"
   },
   {
    "k": "p",
    "t": "Haversack never changes your firewall. **Diagnostics**, **Health** says what to allow, if anything: TCP 47110 and UDP 5353."
   },
   {
    "k": "li",
    "d": 0,
    "t": "On Windows, allow Python on private networks when Windows asks."
   },
   {
    "k": "li",
    "d": 0,
    "t": "On Bazzite, the default settings already allow it."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Promises"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Device to device only.** Game files go straight between your own devices, on your home network or over your own VPN (WireGuard, Tailscale or ZeroTier). They never go through cloud storage, or through any server or relay run by Haversack."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Paired devices only.** Every connection is encrypted with a key only your two devices know. Devices you have not paired are refused."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Exact copies.** Files arrive exactly as they were, with their sizes, permissions, times and links. Nothing is compressed, at any layer."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Pause and resume.** You can pause a transfer and resume it later. It also carries on by itself after errors, a lost network, the other device going away and coming back, a restart, sleep, or a power cut. Nothing already checked is sent twice."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Stop means clean.** **Stop and remove**, which asks you first, deletes everything the transfer made: partial files, the shortcut, the prefix and any tool copy. Your existing install is never touched."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Room to spare.** Haversack checks there is enough free space before anything is read or copied, and keeps the device awake while it copies."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Honest speed.** Both devices show the speed, time left and progress, and say plainly when a link looks slow."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Saves stay with Saves.** Replication never touches save files. Haversack's save sync looks after them."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Emulators"
   },
   {
    "k": "p",
    "t": "**Games and devices**, **Emulators** shows what this device has:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "EmuDeck or RetroDECK, and the standalone emulators;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "every emulator game, with multi-disc games grouped as one;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "how many firmware, BIOS and key files there are."
   },
   {
    "k": "p",
    "t": "Haversack only counts the firmware, BIOS and key files and never reads them."
   },
   {
    "k": "p",
    "t": "**Send to** your other handheld (one button per game) copies:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the game's files, with multi-disc games kept together;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "the emulator and its settings, but only if the other handheld lacks them;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "firmware and keys, only when you tick **Also send firmware and keys**. They go only straight to your own paired handheld, over the encrypted link, and are stored there for your user only. Never to the cloud. Copy only what you own."
   },
   {
    "k": "p",
    "t": "Accept it on the other handheld, as with any game. Nothing already there is replaced. The game gets a Steam shortcut made from that handheld's Steam ROM Manager setup; if it has none, add the shortcut with Steam ROM Manager. Flatpak emulators are not copied: install them on the other handheld first."
   }
  ]
 },
 {
  "id": "updates",
  "title": "Updates",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Updates"
   },
   {
    "k": "p",
    "t": "Every Haversack release is signed, and lists every third-party component it contains in a software bill of materials. Before installing an update, Haversack checks the signature against Haversack's own key, which is built in, and checks the download against the signed list of checksums. An update that fails either check is refused."
   },
   {
    "k": "h",
    "l": 2,
    "t": "On a handheld"
   },
   {
    "k": "p",
    "t": "Open **Settings**, **Updates** in Haversack. When a new version is available, the Quick Access Menu also says so. Choose the version and install it: Haversack hands the checked download to Decky's own installer. You can also go back to an earlier version from the same page."
   },
   {
    "k": "p",
    "t": "The **Channel** setting chooses between stable releases only, or test releases too."
   },
   {
    "k": "p",
    "t": "After an update, Haversack shows **What's new** once, from that version's release notes."
   },
   {
    "k": "h",
    "l": 2,
    "t": "On a PC"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open **Updates** and choose **Check for updates**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Choose **Install** for the new version. It is installed beside the one you are running."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Choose **Restart Haversack now**. Haversack opens again in a new tab, on the new version."
   },
   {
    "k": "p",
    "t": "The version you had is kept. **Go back to...**, then a restart, returns to it."
   },
   {
    "k": "p",
    "t": "Updates never change your settings, your saves or whether Haversack starts when you sign in."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Keepsake is now Haversack"
   },
   {
    "k": "p",
    "t": "Version 0.51.0 renamed Keepsake to Haversack. On a handheld, update Keepsake as usual. Decky installs Haversack beside Keepsake, at the top of its list:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open Haversack in the Quick Access Menu. It shows one card, \"Keepsake is now called Haversack\". Until you go on, Keepsake keeps working and Haversack does nothing, so the two never sync at once."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Press **Remove the old Keepsake** and confirm. Haversack removes Keepsake (and Keepsake Helper, if you had it), copies your settings, sign-ins, games and history across, checks every file, and starts."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. If you use the helper, install Haversack Helper from **Device**, **Reconnect help**."
   },
   {
    "k": "p",
    "t": "Nothing is lost:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Your old copy stays on the device."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Your cloud folder keeps its name, so your other devices carry on before they update."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Microsoft's and Google's sign-in pages still show the registered name, Keepsake."
   },
   {
    "k": "p",
    "t": "To go back, remove Haversack in Decky's settings and install an earlier Keepsake from the Releases page. If you later update again, Haversack brings in what Keepsake did meanwhile, and keeps its own earlier copy aside."
   },
   {
    "k": "p",
    "t": "On a PC, the update installs Haversack in place of Keepsake, in the same folders."
   }
  ]
 },
 {
  "id": "privacy",
  "title": "Privacy",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Privacy"
   },
   {
    "k": "p",
    "t": "Haversack has no server and no account. It collects nothing about you, sends no analytics, and talks only to the services you choose."
   },
   {
    "k": "h",
    "l": 2,
    "t": "What is stored where"
   },
   {
    "k": "row",
    "t": "Where  |  What"
   },
   {
    "k": "row",
    "t": "Your cloud storage  |  Snapshots of the save files of the games you sync. Each snapshot also records the device name you chose, the time, a name for the game taken from its title, Haversack's version, and each file's name within its save location. A small record per device holds that device's name and Haversack version. Each play session is recorded with its start, end and length, and which of your devices it was on, for the combined playtime."
   },
   {
    "k": "row",
    "t": "Each device  |  Settings, sign-in tokens (readable only by your user), the list of games, logs, the copies taken before each restore, and any snapshot held back for checking."
   },
   {
    "k": "p",
    "t": "Cloud data never contains paths from your devices, your user name, Proton prefix numbers or SD card labels. Save files are stored under neutral names such as \"Documents\" or \"AppData\", so one device's paths never leak to another."
   },
   {
    "k": "p",
    "t": "Logs and diagnostics stay on the device. Tokens, passwords and codes are removed from them. A diagnostics export goes only where you copy it."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Who Haversack talks to"
   },
   {
    "k": "p",
    "t": "Each service is contacted only for the feature that needs it, and only while that feature is on:"
   },
   {
    "k": "row",
    "t": "Service  |  When"
   },
   {
    "k": "row",
    "t": "Microsoft (login.microsoftonline.com, graph.microsoft.com) or Google (oauth2.googleapis.com, www.googleapis.com)  |  Sign-in and your snapshots, if you use OneDrive or Google Drive"
   },
   {
    "k": "row",
    "t": "Your WebDAV or S3 server  |  Your snapshots, if you use one"
   },
   {
    "k": "row",
    "t": "GitHub (api.github.com, release downloads, raw.githubusercontent.com)  |  Checking for updates, downloading them, and the Ludusavi save database"
   },
   {
    "k": "row",
    "t": "Advisor's sources (deckverified.games, PCGamingWiki, Haversack's ProtonDB index on GitHub)  |  Only while Advisor and that source are on"
   },
   {
    "k": "row",
    "t": "An AI provider (Anthropic, OpenAI or Google Gemini)  |  Only with your own key, when you press the button, with only the game title, hardware profile, tool versions and the settings discussed"
   },
   {
    "k": "row",
    "t": "SteamGridDB  |  Only with your own key, when you look for artwork"
   },
   {
    "k": "row",
    "t": "A network location you type in the Installer  |  Only that address, after you choose it"
   },
   {
    "k": "row",
    "t": "Your other devices  |  Only for Replication, once it exists and you turn it on and pair them"
   },
   {
    "k": "p",
    "t": "Sign-in uses the provider's own page. Haversack never sees your password. It asks only for access to its own folder: Apps/Keepsake in OneDrive, or Haversack's hidden app folder in Google Drive."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Removing everything"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Your cloud:** delete the Apps/Keepsake folder in OneDrive. In Google Drive, open Settings, then **Manage apps**, and choose **Delete hidden app data** for Haversack. For WebDAV and S3, delete the folder you gave Haversack."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Each device:** uninstall Haversack (in Decky, or with install.pyw --uninstall on a PC), then delete its settings folder: ~/homebrew/settings/Haversack on a handheld, ~/.config/keepsake and ~/.local/state/keepsake on Linux, and %APPDATA%\\Keepsake and %LOCALAPPDATA%\\Keepsake on Windows."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Its access:** withdraw it at Microsoft's app permissions page (account.live.com/consent/Manage) or Google's third-party access page (myaccount.google.com/connections)."
   }
  ]
 },
 {
  "id": "faq",
  "title": "Questions and answers",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Questions and answers"
   },
   {
    "k": "p",
    "t": "**Does Haversack work with emulators, Heroic, Lutris or Bottles?** Yes, on a handheld or a Linux PC. See How syncing works."
   },
   {
    "k": "p",
    "t": "**Does Haversack replace Steam Cloud?** No, it works beside it. Steam games are listed with your non-Steam games, and their saves are snapshotted, synced, restored and kept in History in exactly the same way. A Steam game you have played that has no Steam Cloud saves starts syncing on its own, and Haversack tells you when it does. Games that use Steam Cloud stay off unless you turn them on, because Steam already keeps their saves. Turn any game on or off on its page; one you turn off stays off. Settings has **Sync Steam games that Steam Cloud does not back up** to stop the automatic part."
   },
   {
    "k": "p",
    "t": "**My non-Steam game has a different shortcut ID on each device. Will it still sync?** Yes. That is what Haversack is built for. Saves are stored under neutral locations rather than prefix numbers. The same game is recognised on each device by its save data and title, and by your confirmation when Haversack is not sure."
   },
   {
    "k": "p",
    "t": "**What happens if I play on two devices without syncing in between?** Haversack notices that both changed and asks you which save to keep. The other one stays in History, pinned. See Conflicts, history and restoring."
   },
   {
    "k": "p",
    "t": "**Can a sync ever wipe my save?** Haversack takes and checks a snapshot of your current save before replacing any file, so every restore can be undone. A save that suddenly loses most of its files is held back on the device instead of being uploaded."
   },
   {
    "k": "p",
    "t": "**What if I am offline?** Games always start. Haversack syncs the next time it can reach your cloud."
   },
   {
    "k": "p",
    "t": "**Why does my game pause for a moment when it starts?** On a handheld, Haversack pauses the game briefly while it checks for a newer save, so it can put that save in place before the game reads it. A watchdog always resumes the game, whatever happens. You can switch this off per game."
   },
   {
    "k": "p",
    "t": "**Why does a PC not pause the game?** On a PC, Haversack does not start your games, so it cannot pause one safely at launch. It never touches saves while a game runs. Press **Sync now** before playing to be sure you have the newest save."
   },
   {
    "k": "p",
    "t": "**Does Haversack need root, Desktop Mode or a terminal?** No. On a handheld everything happens in Gaming Mode with the controller. Nothing runs as root, and Haversack installs no extra programs."
   },
   {
    "k": "p",
    "t": "**Is my health page showing a warning?**"
   },
   {
    "k": "p",
    "t": "Each check says what is wrong and what to do. Most warnings are a game waiting for your choice in Conflicts, or a sign-in that needs renewing. See Troubleshooting."
   },
   {
    "k": "p",
    "t": "**Can I leave Haversack and keep my saves?** Yes. Settings, **Export snapshots** copies them out as plain zip files with a list of their contents. See Conflicts, history and restoring."
   },
   {
    "k": "p",
    "t": "**Where do I report a problem?** Open an issue on GitHub (github.com/breakmylegs/haversack/issues). For a security problem, use **Report a vulnerability** on the repository's Security tab instead, so it stays private. Diagnostics, then **Export diagnostics**, makes a file you can attach. Tokens and passwords are removed from it, but read it first."
   },
   {
    "k": "p",
    "t": "**Why does my library show my other handheld's games with Stream instead of Play?** That is Steam Remote Play. When your other device is on with Steam running, Steam lists the games installed there in this device's library, so you can stream them. A non-Steam game installed on the other device shows as a tile with **Stream**. If you have the same game on both, you may see it twice. Haversack never treats these as games on this device: they are left out of the Games list, save sync, Send to, Replication, Advisor and Uninstall. Haversack's Games page says how many there are, and **Show games you can stream from another device** lists them."
   },
   {
    "k": "p",
    "t": "To see only the games installed on this device, use the **Installed** tab in Steam's library, or switch off Remote Play in Steam's settings. Haversack does not hide them for you yet: Steam may share hidden games between your devices, so hiding one here could hide the real game on your other handheld. If a game on this device ever becomes hidden, Haversack tells you and offers **Show it again**."
   },
   {
    "k": "p",
    "t": "**How do I uninstall a game?** Open the game in Haversack's Games page and press **Uninstall**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**A Steam game:** if it syncs, Haversack first offers a final backup of its saves, then opens Steam's own uninstall. Steam removes the game, as it always does."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**A non-Steam game:** Haversack shows exactly which folders it will delete (the game's Proton prefix and its game folder), how big they are and how much space you will have after. Cancel is selected first; nothing happens until you press **Uninstall**. If the game syncs, a final backup of its saves goes to your cloud or your other devices first, and Haversack tells you where to restore it from: the game's History on any of your devices. Then the shortcut and its artwork leave Steam, the folders are deleted with progress and a **Stop** button, and Haversack forgets the game on this device."
   },
   {
    "k": "p",
    "t": "Haversack never deletes your home folder, a Steam library, a folder another game uses, a link or a drive, and it will not uninstall a game while it is running or one you can only stream from another device. Anything it will not delete is listed with the reason."
   }
  ]
 },
 {
  "id": "troubleshooting",
  "title": "Troubleshooting",
  "blocks": [
   {
    "k": "h",
    "l": 1,
    "t": "Troubleshooting"
   },
   {
    "k": "p",
    "t": "Start with Haversack, Diagnostics, Health, **Run checks**. Each check says what is wrong and what to do. The Quick Access Menu badge shows the worst result."
   },
   {
    "k": "row",
    "t": "What you see  |  What it means  |  What to do"
   },
   {
    "k": "row",
    "t": "\"Test store on this device\" in the Quick Access Menu  |  Snapshots are not leaving the device  |  Settings, Cloud: choose OneDrive, Google Drive, WebDAV or S3 and finish its setup"
   },
   {
    "k": "row",
    "t": "Cloud check fails: \"not signed in or set up\"  |  No sign-in, or settings incomplete  |  Settings, Cloud, the backend in use: sign in or fill in the settings, then Test connection"
   },
   {
    "k": "row",
    "t": "\"Sign-in needs attention\"  |  The cloud stopped accepting the saved sign-in (password change, revoked access, or Google's 7-day limit for apps in testing mode)  |  Settings, Cloud: Sign out, then Sign in again. Waiting saves are uploaded afterwards"
   },
   {
    "k": "row",
    "t": "WebDAV or S3: \"ignores create-only writes\"  |  The server would overwrite files, which could lose saves  |  Use a server that supports If-None-Match (Nextcloud, ownCloud, AWS S3), see docs/setup-backends.md"
   },
   {
    "k": "row",
    "t": "A game says \"Conflict: your choice needed\"  |  Both devices have new progress, or the cloud and this device differ  |  Conflicts tab, Choose. Whichever save you do not choose is kept and pinned"
   },
   {
    "k": "row",
    "t": "\"A suspicious save was kept on this device\"  |  A save lost many files or much of its size, so it was not uploaded  |  History: if the game really did drop those files, Release quarantine; otherwise play on and the next good save replaces it"
   },
   {
    "k": "row",
    "t": "\"Prefix mismatch, sync blocked\"  |  The running game used a different Proton prefix from the one Haversack found  |  Check the shortcut's compatibility settings; Rescan on the Games page; the block clears when the prefixes agree"
   },
   {
    "k": "row",
    "t": "\"Played while Haversack was not running\"  |  Steam saw a play Haversack missed  |  Nothing: the idle pass saved it. Make sure Decky starts with the device"
   },
   {
    "k": "row",
    "t": "A game is not matched  |  The manifest does not know it, or the name differs  |  Game page: Change match, approve a suggested match, or \"Give it its own game key\" and add custom folders"
   },
   {
    "k": "row",
    "t": "Saves restored but \"registry keys were left unchanged\"  |  user.reg could not be read safely or the game was running  |  Quit the game and restore again from History; the save files are already in place"
   },
   {
    "k": "row",
    "t": "Update refused: \"not signed\" or \"signature is not valid\"  |  A release key is pinned and the release does not carry a valid signature  |  Do not install it; report it on the repository's Issues page"
   },
   {
    "k": "row",
    "t": "Update refused while syncing  |  Updates wait for sync jobs and open game sessions  |  Use \"Update when idle\", or quit the game"
   },
   {
    "k": "row",
    "t": "Settings are read-only (\"safe mode\")  |  You went back to an older version than the one that wrote the settings  |  Update Haversack from the Updates page"
   },
   {
    "k": "row",
    "t": "Updates stuck on \"Checking\", no installed version shown, and Games, the manifest update or shortcuts never load  |  Haversack's backend did not start, so the page waits for answers that never come. The usual cause is a Python module missing from this Decky build  |  Read Decky's journal (below). If it names a missing module, install the latest Haversack from the install link and report the module name on the repository's Issues page"
   },
   {
    "k": "row",
    "t": "Diagnostics, \"Python modules in this Decky build\" warns about xml  |  Decky's Python on this device has no XML module  |  Save sync is fine with OneDrive, Google Drive or the local store. WebDAV and S3 need it, so choose another cloud"
   },
   {
    "k": "h",
    "l": 2,
    "t": "Reading Decky's journal"
   },
   {
    "k": "p",
    "t": "When Haversack's page loads but nothing answers (Updates stays on \"Checking\" and no installed version is shown), its backend failed to start. Decky records why in the system journal."
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Open a terminal: Desktop Mode's Konsole, or SSH from another computer (ssh deck@)."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. Run journalctl -u plugin_loader -b to see this boot's Decky messages. Add --no-pager | grep -i -A5 keepsake to show only Haversack's lines, or -f to follow it live while you open Haversack."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Look for a Traceback near Haversack. The last line says what failed, for example ModuleNotFoundError: No module named 'xml.etree'."
   },
   {
    "k": "p",
    "t": "Decky runs plugins with its own built-in Python, which only includes the standard modules Decky itself uses. Haversack imports anything else only inside the feature that needs it, so a missing module switches that feature off instead of stopping the backend (ADR-0030). If the journal shows a missing module anyway, that is a Haversack bug: report the line on the repository's Issues page. Installing the latest release from the install link (see the README) is the fix once it is out."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Getting details off the device"
   },
   {
    "k": "p",
    "t": "Diagnostics, Tools, **Export diagnostics** writes one JSON file in ~/homebrew/settings/Haversack/. It is redacted (no tokens, passwords or account names) but lists your games. Logs are in ~/homebrew/logs/Keepsake/. Over SSH: scp deck@:homebrew/settings/Keepsake/diagnostics-*.json."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Starting again on one device"
   },
   {
    "k": "p",
    "t": "Settings, General, Run setup again walks through every step. Your cloud history is never deleted by setup."
   }
  ]
 }
];
