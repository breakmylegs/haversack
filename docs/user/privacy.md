# Privacy

Keepsake has no server and no account. It collects nothing about you, sends no analytics, and talks only to the services you choose.

## What is stored where

| Where | What |
|---|---|
| Your cloud storage | Snapshots of the save files of the games you sync. Each snapshot also records the device name you chose, the time, a name for the game taken from its title, Keepsake's version, and each file's name within its save location. A small record per device holds that device's name and Keepsake version. Each play session is recorded with its start, end and length, and which of your devices it was on, for the combined playtime. |
| Each device | Settings, sign-in tokens (readable only by your user), the list of games, logs, the copies taken before each restore, and any snapshot held back for checking. |

Cloud data never contains paths from your devices, your user name, Proton prefix numbers or SD card labels. Save files are stored under neutral names such as "Documents" or "AppData", so one device's paths never leak to another.

Logs and diagnostics stay on the device. Tokens, passwords and codes are removed from them. A diagnostics export goes only where you copy it.

## Who Keepsake talks to

Each service is contacted only for the feature that needs it, and only while that feature is on:

| Service | When |
|---|---|
| Microsoft (`login.microsoftonline.com`, `graph.microsoft.com`) or Google (`oauth2.googleapis.com`, `www.googleapis.com`) | Sign-in and your snapshots, if you use OneDrive or Google Drive |
| Your WebDAV or S3 server | Your snapshots, if you use one |
| GitHub (`api.github.com`, release downloads, `raw.githubusercontent.com`) | Checking for updates, downloading them, and the Ludusavi save database |
| Advisor's sources (deckverified.games, PCGamingWiki, Keepsake's ProtonDB index on GitHub) | Only while Advisor and that source are on |
| An AI provider (Anthropic, OpenAI or Google Gemini) | Only with your own key, when you press the button, with only the game title, hardware profile, tool versions and the settings discussed |
| SteamGridDB | Only with your own key, when you look for artwork |
| A network location you type in the Installer | Only that address, after you choose it |
| Your other devices | Only for Replication, once it exists and you turn it on and pair them |

Sign-in uses the provider's own page. Keepsake never sees your password. It asks only for access to its own folder: `Apps/Keepsake` in OneDrive, or Keepsake's hidden app folder in Google Drive.

## Removing everything

- **Your cloud:** delete the `Apps/Keepsake` folder in OneDrive. In Google Drive, open Settings, then **Manage apps**, and choose **Delete hidden app data** for Keepsake. For WebDAV and S3, delete the folder you gave Keepsake.
- **Each device:** uninstall Keepsake (in Decky, or with `install.pyw --uninstall` on a PC), then delete its settings folder: `~/homebrew/settings/Keepsake` on a handheld, `~/.config/keepsake` and `~/.local/state/keepsake` on Linux, and `%APPDATA%\Keepsake` and `%LOCALAPPDATA%\Keepsake` on Windows.
- **Its access:** withdraw it at [Microsoft's app permissions page](https://account.live.com/consent/Manage) or [Google's third-party access page](https://myaccount.google.com/connections).
