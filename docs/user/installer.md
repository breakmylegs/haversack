# Installing games

On a handheld, Keepsake's **Install** page installs a Windows game into its own Steam shortcut and Proton prefix, all from Gaming Mode. It needs Decky, so it is not available on a PC.

**An installer is a Windows program that runs with your user's rights. A Proton prefix is not a sandbox.** Only install software you trust.

## From an ISO or a folder

1. Open **Install** and choose the ISO file or the folder holding the installer.
2. Keepsake mounts the ISO (read-only, no root needed) and adds a shortcut called `Install: <Title>` that runs the installer, with the recommended Proton version.
3. Start that shortcut. When the installer asks where to install, type the folder Keepsake shows, for example `Z:\home\deck\Games\<Title>`.
4. Finish the installer and quit.
5. Back in Keepsake, choose the game's program from the list. Keepsake ranks the new programs, leaving out uninstallers and setup tools. Then confirm.
6. The same shortcut now starts the game, keeps its prefix, and is named after the game. Keepsake offers to sync its saves.

If an installer asks for the disc, press **Installer wants a disc drive** and start the installer again. Keepsake gives the prefix a CD drive pointing at the mounted ISO.

### Games on several discs

Keep the discs' ISO files together in one folder and start with disc 1. When the installer asks for the next disc, press **Swap to <disc>** on the Install page, then carry on in the installer. Keepsake puts that disc in the drive without stopping the installer.

### Several installs in a row

Start another install while one is under way, and it joins the queue. Each queued install starts by itself when the one before it ends, and the queue carries on after a restart.

### Runtimes the game ships

If the game comes with runtime installers, such as Visual C++, DirectX or .NET, the Install page lists them when you choose the game's program. Proton already provides most of these, so only run one if the game will not start.

## From a network location

Choose **From a network location** to install from a NAS or server that is not mounted:

- **Web server:** `https://` addresses anywhere. Plain `http://` only on your local network, and never with a password.
- **Windows share (SMB):** `smb://nas.local/` lists the shares, and `smb://nas.local/Games/` opens one. SMB 2 or 3 on your local network only.
- **WebDAV:** for example `davs://cloud.example/remote.php/dav/files/me/Games/`.

Browse to an ISO and pick it. Keepsake downloads it with progress and a cancel button, resumes after a dropped connection, checks it, and installs it as above. The download is deleted when the install ends. **Remember this location** keeps the address; the password stays on the device.

NFS shares still need mounting first, for example by opening them in Dolphin in Desktop Mode. They then appear on the Install page.

## Artwork

With your own [SteamGridDB](https://www.steamgriddb.com) API key in Settings, Keepsake can find artwork for the new shortcut. Your key is never sent anywhere except SteamGridDB.
