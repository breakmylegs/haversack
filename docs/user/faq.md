# Questions and answers

**What happened to save sync?**
Version 0.61.0 took Haversack back to installing games and moving them between your handhelds. Save sync, Advisor, the desktop app, PC support and the device pages were removed. Your saves in the cloud were not deleted: install version 0.60.0 from **Settings**, **Updates** to use them again ([Updates](updates.md#going-back-to-a-version-with-save-sync)).

**What happens to my saves when I send a game?**
The first time you send a game, the whole game goes, with its Proton prefix and the saves in it, so the other handheld can carry on where you left off. After that, updates never replace saves or settings on either handheld. Haversack finds where each game keeps them from the Ludusavi game database.

**My non-Steam game has a different shortcut ID on each device. Does that matter?**
No. Haversack recognises the game on each handheld, and puts it in that handheld's own prefix and folders.

**Do my games go through the cloud?**
No. They go straight between your own handhelds, on your home network or over your own VPN, encrypted with a key only your two devices know.

**Does Haversack need root, Desktop Mode or a terminal?**
No. Everything happens in Gaming Mode with the controller. Nothing runs as root, and Haversack installs no extra programs.

**Where do I report a problem?**
Open an issue on [GitHub](https://github.com/breakmylegs/haversack/issues). For a security problem, use **Report a vulnerability** on the repository's Security tab instead, so it stays private. **Diagnostics**, **Tools**, **Export diagnostics** makes a file you can attach. Keys and passwords are removed from it, but read it first.

**Why does my library show my other handheld's games with Stream instead of Play?**
That is Steam Remote Play. When your other device is on with Steam running, Steam lists the games installed there in this device's library, so you can stream them. A non-Steam game installed on the other device shows as a tile with **Stream**. Haversack never treats these as games on this device: they are left out of its Games list and are never sent. **Install** can find artwork for those tiles ([Installing games](installer.md#artwork-for-streaming-tiles)).

To see only the games installed on this device, use the **Installed** tab in Steam's library, or switch off Remote Play in Steam's settings.
