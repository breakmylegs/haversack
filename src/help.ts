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
    "t": "Haversack installs Windows games on your SteamOS and Bazzite handhelds, from an ISO, a folder or a network share, each into its own Steam shortcut and Proton prefix. It then sends them between your handhelds when you ask, directly over your home network, and keeps them in step after a patch or a mod. Everything happens in Gaming Mode with the controller."
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
    "t": "Version 0.61.0 took Haversack back to installing and moving games. Save sync, Advisor, the desktop app, PC support and the device pages are gone. Your saves in the cloud are still there: install version 0.60.0 to use them (Updates)."
   },
   {
    "k": "p",
    "t": "Haversack's page has four sections in its sidebar. Highlight one to see its pages, then press A to open one. On a section's page, **L1** and **R1** move between its pages, and **B** goes back to the sidebar. Each section opens where you left it."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Install.**"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Games and devices:** Games, Moving games, Other devices, Emulators."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Settings:** General (with the quick menu's shortcuts), Modules, Updates, Help."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Diagnostics:** Device checks, Tools, Logs."
   },
   {
    "k": "p",
    "t": "This guide is also in Haversack itself, under **Settings**, **Help**, so you can read it on the handheld."
   },
   {
    "k": "p",
    "t": "The quick access menu shows games on their way between your devices, your chosen shortcuts, and anything that needs you."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Getting started"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Getting started on a handheld: Steam Deck, Legion Go, ROG Ally and others, on SteamOS or Bazzite."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Guides"
   },
   {
    "k": "li",
    "d": 0,
    "t": "Installing games: from an ISO, a folder or a network share, and finding artwork."
   },
   {
    "k": "li",
    "d": 0,
    "t": "Replication: pairing your handhelds, sending a game or an emulator game, and keeping it in step."
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
   }
  ]
 },
 {
  "id": "getting-started-handheld",
  "title": "Getting started on a handheld",
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
    "k": "p",
    "t": "There is nothing to set up. Open Haversack from the Quick Access Menu and choose **Open Haversack**."
   },
   {
    "k": "h",
    "l": 2,
    "t": "2. Install a game"
   },
   {
    "k": "p",
    "t": "Open **Install** and choose an ISO, a folder holding an installer, or a network share. Haversack mounts the ISO, adds a shortcut that runs the installer in the game's own Proton prefix, and turns that shortcut into the game when the installer finishes (Installing games)."
   },
   {
    "k": "h",
    "l": 2,
    "t": "3. Send it to your other handheld"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. On both handhelds, open **Games and devices**, **Other devices**, and switch on **Let other devices reach this one**."
   },
   {
    "k": "li",
    "d": 0,
    "t": "2. On one of them, press **Find devices**, choose the other and press **Pair**. Accept on the other handheld and type the code it shows."
   },
   {
    "k": "li",
    "d": 0,
    "t": "3. Open **Games and devices**, **Games**, choose the game and press **Send to **."
   },
   {
    "k": "p",
    "t": "The other handheld gets the game, added to Steam with the same name, launch options, Proton version and artwork (Replication). After a patch or a mod, Haversack offers to send the update; your saves on each handheld are never replaced by one."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Your quick menu"
   },
   {
    "k": "p",
    "t": "Haversack's panel in the quick access menu can show what you use most. Open **Settings**, **General**, **Quick menu**:"
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
    "t": "Haversack's **Install** page installs a Windows game into its own Steam shortcut and Proton prefix, all from Gaming Mode."
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
    "t": "6. The same shortcut now starts the game, keeps its prefix, and is named after the game. **Open in Games** takes you to it, to send it to your other handheld or find its artwork."
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
    "t": "Artwork for any non-Steam game"
   },
   {
    "k": "p",
    "t": "Any non-Steam game in **Games and devices**, **Games** has **Artwork** when the game is missing a cover, a wide cover, a background or a logo. Press **Find artwork** and pick the game on SteamGridDB. Haversack adds only the kinds the game has none of, through Steam, so artwork you or another tool set is never replaced. It uses the same SteamGridDB key as installed games."
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
    "t": "Replication links your own handhelds directly. It pairs them, then sends non-Steam games between them: a game you set up on one handheld appears on the other, playable, with the same Proton version, artwork and launch options."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Switch it on"
   },
   {
    "k": "li",
    "d": 0,
    "t": "1. Replication is on from the start. If you switched it off, open **Settings**, **Modules** and switch on **Replication**. **Games and devices** has **Moving games** and **Other devices**."
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
    "t": "Each device you pair is linked to every other one you pair, so a group of three handhelds works."
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
    "t": "**Wake** sends a Wake-on-LAN signal. A handheld asleep on Wi-Fi usually cannot be woken this way, but one on a dock's cable often can."
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
    "t": "1. On the device that has the game, open it in **Games and devices**, **Games** and press **Send to **."
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
    "t": "3. Haversack copies the game, adds it to Steam with the same name, program, launch options, Proton version and artwork, and says when it is ready. The first copy includes the game's saves, so you carry on where you left off."
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
    "t": "as a short line in the quick access menu."
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
    "t": "Your saves and settings on each device are never replaced by an update, whichever you choose. Haversack finds them from the Ludusavi game database and leaves them out of every update."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Firewalls"
   },
   {
    "k": "p",
    "t": "Haversack never changes your firewall. **Diagnostics**, **Device checks** says what to allow, if anything: TCP 47110 and UDP 5353. On Bazzite, the default settings already allow it."
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
    "t": "**Saves copied once.** The first copy of a game includes its saves. After that, no update ever replaces a save or settings file on either device."
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
    "k": "p",
    "t": "Updates never change your settings, your games or your saves."
   },
   {
    "k": "h",
    "l": 2,
    "t": "Going back to a version with save sync"
   },
   {
    "k": "p",
    "t": "Version 0.61.0 removed save sync, Advisor, the desktop app, PC support and the device pages, so Haversack only installs and moves games. Nothing was deleted:"
   },
   {
    "k": "li",
    "d": 0,
    "t": "your snapshots stay in your cloud storage, in the same folder;"
   },
   {
    "k": "li",
    "d": 0,
    "t": "your sign-ins, game list and history stay in Haversack's settings folder on each device."
   },
   {
    "k": "p",
    "t": "To use them again, open **Settings**, **Updates**, and install version 0.60.0 from the list of earlier versions. Everything is where you left it. Version 0.60.0 still tells you about later versions; installing one removes save sync again, without deleting anything."
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
    "k": "p",
    "t": "To go back, remove Haversack in Decky's settings and install an earlier Keepsake from the Releases page. If you later update again, Haversack brings in what Keepsake did meanwhile, and keeps its own earlier copy aside."
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
    "t": "Each handheld  |  Settings, your SteamGridDB key and network-location passwords (readable only by your user), the list of games, the devices you paired and their keys, logs, and the record of each install and transfer."
   },
   {
    "k": "row",
    "t": "Your other handheld  |  The games you send it, and what it needs to keep them in step: each game's name, its file list and checksums, and which device sent it."
   },
   {
    "k": "p",
    "t": "Haversack stores nothing in the cloud. Versions before 0.61.0 kept save snapshots in your cloud storage; they are still there, untouched (Updates)."
   },
   {
    "k": "p",
    "t": "What goes between your devices never contains paths from the sending device, your user name, Proton prefix numbers or SD card labels. Each device puts the game in its own folders."
   },
   {
    "k": "p",
    "t": "Logs and diagnostics stay on the device. Keys, passwords and codes are removed from them. A diagnostics export goes only where you copy it."
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
    "t": "GitHub (api.github.com, release downloads)  |  Checking for updates and downloading them"
   },
   {
    "k": "row",
    "t": "GitHub (raw.githubusercontent.com)  |  The Ludusavi game database, which tells Haversack where each game keeps its saves, so an update to a game never replaces them"
   },
   {
    "k": "row",
    "t": "SteamGridDB  |  Only with your own key, when you look for artwork"
   },
   {
    "k": "row",
    "t": "A network location you type in Install  |  Only that address, after you choose it"
   },
   {
    "k": "row",
    "t": "Your other handhelds  |  Only for Moving games, once you let other devices reach this one and pair them"
   },
   {
    "k": "h",
    "l": 2,
    "t": "Removing everything"
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Each device:** uninstall Haversack in Decky, then delete its settings folder, ~/homebrew/settings/Haversack."
   },
   {
    "k": "li",
    "d": 0,
    "t": "**Your cloud, from earlier versions:** delete the Apps/Keepsake folder in OneDrive. In Google Drive, open Settings, then **Manage apps**, and choose **Delete hidden app data** for Haversack. For WebDAV and S3, delete the folder you gave Haversack. Withdraw its access at Microsoft's app permissions page (account.live.com/consent/Manage) or Google's third-party access page (myaccount.google.com/connections)."
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
    "t": "**What happened to save sync?** Version 0.61.0 took Haversack back to installing games and moving them between your handhelds. Save sync, Advisor, the desktop app, PC support and the device pages were removed. Your saves in the cloud were not deleted: install version 0.60.0 from **Settings**, **Updates** to use them again (Updates)."
   },
   {
    "k": "p",
    "t": "**What happens to my saves when I send a game?** The first time you send a game, the whole game goes, with its Proton prefix and the saves in it, so the other handheld can carry on where you left off. After that, updates never replace saves or settings on either handheld. Haversack finds where each game keeps them from the Ludusavi game database."
   },
   {
    "k": "p",
    "t": "**My non-Steam game has a different shortcut ID on each device. Does that matter?** No. Haversack recognises the game on each handheld, and puts it in that handheld's own prefix and folders."
   },
   {
    "k": "p",
    "t": "**Do my games go through the cloud?** No. They go straight between your own handhelds, on your home network or over your own VPN, encrypted with a key only your two devices know."
   },
   {
    "k": "p",
    "t": "**Does Haversack need root, Desktop Mode or a terminal?** No. Everything happens in Gaming Mode with the controller. Nothing runs as root, and Haversack installs no extra programs."
   },
   {
    "k": "p",
    "t": "**Where do I report a problem?** Open an issue on GitHub (github.com/breakmylegs/haversack/issues). For a security problem, use **Report a vulnerability** on the repository's Security tab instead, so it stays private. **Diagnostics**, **Tools**, **Export diagnostics** makes a file you can attach. Keys and passwords are removed from it, but read it first."
   },
   {
    "k": "p",
    "t": "**Why does my library show my other handheld's games with Stream instead of Play?** That is Steam Remote Play. When your other device is on with Steam running, Steam lists the games installed there in this device's library, so you can stream them. A non-Steam game installed on the other device shows as a tile with **Stream**. Haversack never treats these as games on this device: they are left out of its Games list and are never sent. **Install** can find artwork for those tiles (Installing games)."
   },
   {
    "k": "p",
    "t": "To see only the games installed on this device, use the **Installed** tab in Steam's library, or switch off Remote Play in Steam's settings."
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
    "t": "Start with Haversack, **Diagnostics**, **Device checks**, **Run all**. Each check says what is wrong and what to do."
   },
   {
    "k": "row",
    "t": "What you see  |  What it means  |  What to do"
   },
   {
    "k": "row",
    "t": "Find devices lists nothing  |  The other handheld is not letting devices reach it, or your network blocks the search  |  On the other handheld, Games and devices, Other devices: switch on Let other devices reach this one. Or type its address under Pair by address"
   },
   {
    "k": "row",
    "t": "\"doesn't have enough space\" when sending  |  The other handheld has too little free space for the game  |  Free some space there, or send the game to a different drive"
   },
   {
    "k": "row",
    "t": "A transfer says the link looks slow  |  A VPN may be relaying the connection  |  Use your home network, or check your VPN's direct connection settings"
   },
   {
    "k": "row",
    "t": "Install cannot open an ISO on a share  |  The share does not let the system mount the ISO there  |  Nothing: Haversack copies it to the device first and installs from the copy"
   },
   {
    "k": "row",
    "t": "Find shares lists nothing  |  Your network blocks the search (some mesh and guest Wi-Fi do)  |  Type the address, for example smb://nas.local/Games/"
   },
   {
    "k": "row",
    "t": "Update refused: \"not signed\" or \"signature is not valid\"  |  A release key is pinned and the release does not carry a valid signature  |  Do not install it; report it on the repository's Issues page"
   },
   {
    "k": "row",
    "t": "Update refused while busy  |  Updates wait for installs, transfers and open game sessions  |  Wait for them to finish, or quit the game"
   },
   {
    "k": "row",
    "t": "Settings are read-only (\"safe mode\")  |  You went back to an older version than the one that wrote the settings  |  Update Haversack from the Updates page"
   },
   {
    "k": "row",
    "t": "Updates stuck on \"Checking\", no installed version shown, and Games or shortcuts never load  |  Haversack's backend did not start, so the page waits for answers that never come. The usual cause is a Python module missing from this Decky build  |  Read Decky's journal (below). If it names a missing module, install the latest Haversack from the install link and report the module name on the repository's Issues page"
   },
   {
    "k": "row",
    "t": "My saves from before 0.61.0 are missing  |  Version 0.61.0 removed save sync; nothing was deleted  |  Install version 0.60.0 from Settings, Updates (Updates)"
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
    "t": "Diagnostics, Tools, **Export diagnostics** writes one JSON file in ~/homebrew/settings/Haversack/. It is redacted (no keys, passwords or account names) but lists your games. Logs are in ~/homebrew/logs/Haversack/. Over SSH: scp deck@:homebrew/settings/Haversack/diagnostics-*.json."
   }
  ]
 }
];
