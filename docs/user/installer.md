# Installing games

On a handheld, Haversack's **Install** page installs a Windows game into its own Steam shortcut and Proton prefix, all from Gaming Mode. It needs Decky, so it is not available on a PC.

**An installer is a Windows program that runs with your user's rights. A Proton prefix is not a sandbox.** Only install software you trust.

## From an ISO or a folder

1. Open **Install** and choose the ISO file or the folder holding the installer.
2. Haversack mounts the ISO (read-only, no root needed) and adds a shortcut called `Install: <Title>` that runs the installer, with the recommended Proton version.
3. Start that shortcut. When the installer asks where to install, type the folder Haversack shows, for example `Z:\home\deck\Games\<Title>`.
4. Finish the installer and quit.
5. Back in Haversack, choose the game's program from the list. Haversack ranks the new programs, leaving out uninstallers and setup tools. Then confirm.
6. The same shortcut now starts the game, keeps its prefix, and is named after the game. Haversack offers to sync its saves.

If an installer asks for the disc, press **Installer wants a disc drive** and start the installer again. Haversack gives the prefix a CD drive pointing at the mounted ISO.

### Games on several discs

Keep the discs' ISO files together in one folder and start with disc 1. When the installer asks for the next disc, press **Swap to <disc>** on the Install page, then carry on in the installer. Haversack puts that disc in the drive without stopping the installer.

### Several installs in a row

Start another install while one is under way, and it joins the queue. Each queued install starts by itself when the one before it ends, and the queue carries on after a restart.

### Runtimes the game ships

If the game comes with runtime installers, such as Visual C++, DirectX or .NET, the Install page lists them when you choose the game's program. Proton already provides most of these, so only run one if the game will not start.

## From a network location

Choose **From a network location** to install from a NAS or server that is not mounted:

- **Web server:** `https://` addresses anywhere. Plain `http://` only on your local network, and never with a password.
- **Windows share (SMB):** press **Find shares** to list the Windows PCs, NAS boxes and Macs sharing folders on your network, then pick one to see its shares. Or type an address: `smb://nas.local/` lists the shares, and `smb://nas.local/Games/` opens one. SMB 2 or 3 on your local network only. If nothing is found, your network may block the search (some mesh and guest Wi-Fi do); typing the address still works.
- **WebDAV:** for example `davs://cloud.example/remote.php/dav/files/me/Games/`.

Browse to an ISO and pick it. Haversack downloads it with progress and a cancel button, resumes after a dropped connection, checks it, and installs it as above. The download is deleted when the install ends. **Remember this location** keeps the address; the password stays on the device.

NFS shares still need mounting first, for example by opening them in Dolphin in Desktop Mode. They then appear on the Install page.

An ISO on a share that is already mounted is opened where it is, with nothing copied. If the share does not allow that, Haversack copies the ISO to the device first, by itself, shows the progress, and installs from the copy. Installing straight from a share that is not mounted, without downloading first, is coming once a system tool it needs is approved; until then the ISO is downloaded as above.

## Artwork

With your own [SteamGridDB](https://www.steamgriddb.com) API key in Settings, Haversack can find artwork for the new shortcut. Your key is never sent anywhere except SteamGridDB.

## Artwork for streaming tiles

Steam lists non-Steam games installed on your other devices as streaming tiles, with no artwork. At the bottom of **Install**, **Artwork for streaming tiles** lists them. Press **Find artwork**, pick the game on SteamGridDB (your SteamGridDB key, set up as for installed games), and Haversack sets the tile's artwork through Steam.
