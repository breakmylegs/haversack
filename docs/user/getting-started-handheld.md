# Getting started on a handheld

For SteamOS and Bazzite handhelds with [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader). Everything happens in Gaming Mode with the controller. You never need Desktop Mode or a terminal.

## 1. Install Keepsake

1. In Decky, open **Settings**, then **General**, and turn on **Developer mode**. You only do this once per device.
2. In Decky, open **Settings**, then **Developer**, then **Install Plugin from URL**, and enter:
   ```
   https://github.com/breakmylegs/keepsake/releases/latest/download/Keepsake.zip
   ```
3. After that, Keepsake updates itself from its own **Settings**, **Updates** tab ([Updates](updates.md)).

## 2. Set it up

Open Keepsake from the Quick Access Menu and choose **Set up Keepsake**. The wizard has five steps:

1. **Device name.** It is shown next to this device's saves on your other devices.
2. **Cloud.** Choose OneDrive, Google Drive, WebDAV or S3, and sign in ([Cloud storage and sign-in](cloud.md)).
3. **Scan games** and **review matches.** Keepsake finds your Steam games and non-Steam shortcuts and looks up where each one keeps its saves. Approve any match it is not sure about.
4. **Choose games** to sync. Steam games are listed too. Played Steam games with no Steam Cloud saves are synced automatically; ones that use Steam Cloud stay off unless you choose them, because Steam already keeps their saves.
5. **Dry run.** See what the first sync will do for each game. Nothing changes until you confirm.

## 3. Play

That is all. Before a game starts, Keepsake checks the cloud for newer saves, pausing the game for a moment. After you quit, it saves to the cloud ([How syncing works](how-sync-works.md)).

The Quick Access Menu shows the current game's sync state, any conflicts, available updates and **Sync now**. **Open Keepsake** opens the full view, with Games, Conflicts, History, Import saves, Install, Advisor, Settings, Updates, Logs and Diagnostics.

## In Desktop Mode

Keepsake comes with a desktop app, with nothing more to install. When you switch to Desktop Mode, its icon appears in the system tray, with no window. Click it, or choose **Open Keepsake** from its menu, to open Keepsake in your browser; it covers the same pages as in Gaming Mode. Closing the window leaves the icon in the tray. **Quit** in the icon's menu stops it until you next log in. Keepsake is also in the app menu, which brings up the one already running.

If the icon's status line says Keepsake's plugin cannot be reached, Decky Loader is not running in Desktop Mode: switch back to Gaming Mode once, then try again. To stop the desktop app starting, switch **Desktop** off in Settings, Modules.

## Next device

Set up your next device the same way, with the same cloud account. Non-Steam games installed into their own Proton prefixes are recognised as the same game, even though their shortcut IDs and prefix folders differ on each device.

Moving from Ludusavi? See [Importing from Ludusavi](import-ludusavi.md).
