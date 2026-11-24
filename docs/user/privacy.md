# Privacy

Haversack has no server and no account. It collects nothing about you, sends no analytics, and talks only to the services you choose.

## What is stored where

| Where | What |
|---|---|
| Each handheld | Settings, your SteamGridDB key and network-location passwords (readable only by your user), the list of games, the devices you paired and their keys, logs, and the record of each install and transfer. |
| Your other handheld | The games you send it, and what it needs to keep them in step: each game's name, its file list and checksums, and which device sent it. |

Haversack stores nothing in the cloud. Versions before 0.61.0 kept save snapshots in your cloud storage; they are still there, untouched ([Updates](updates.md#going-back-to-a-version-with-save-sync)).

What goes between your devices never contains paths from the sending device, your user name, Proton prefix numbers or SD card labels. Each device puts the game in its own folders.

Logs and diagnostics stay on the device. Keys, passwords and codes are removed from them. A diagnostics export goes only where you copy it.

## Who Haversack talks to

Each service is contacted only for the feature that needs it, and only while that feature is on:

| Service | When |
|---|---|
| GitHub (`api.github.com`, release downloads) | Checking for updates and downloading them |
| GitHub (`raw.githubusercontent.com`) | The Ludusavi game database, which tells Haversack where each game keeps its saves, so an update to a game never replaces them |
| SteamGridDB | Only with your own key, when you look for artwork |
| A network location you type in Install | Only that address, after you choose it |
| Your other handhelds | Only for Moving games, once you let other devices reach this one and pair them |

## Removing everything

- **Each device:** uninstall Haversack in Decky, then delete its settings folder, `~/homebrew/settings/Haversack`.
- **Your cloud, from earlier versions:** delete the `Apps/Keepsake` folder in OneDrive. In Google Drive, open Settings, then **Manage apps**, and choose **Delete hidden app data** for Haversack. For WebDAV and S3, delete the folder you gave Haversack. Withdraw its access at [Microsoft's app permissions page](https://account.live.com/consent/Manage) or [Google's third-party access page](https://myaccount.google.com/connections).
