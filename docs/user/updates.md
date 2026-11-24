# Updates

Every Haversack release is signed, and lists every third-party component it contains in a software bill of materials. Before installing an update, Haversack checks the signature against Haversack's own key, which is built in, and checks the download against the signed list of checksums. An update that fails either check is refused.

## On a handheld

Open **Settings**, **Updates** in Haversack. When a new version is available, the Quick Access Menu also says so. Choose the version and install it: Haversack hands the checked download to Decky's own installer. You can also go back to an earlier version from the same page.

The **Channel** setting chooses between stable releases only, or test releases too.

After an update, Haversack shows **What's new** once, from that version's release notes.

Updates never change your settings, your games or your saves.

## Going back to a version with save sync

Version 0.61.0 removed save sync, Advisor, the desktop app, PC support and the device pages, so Haversack only installs and moves games. Nothing was deleted:
- your snapshots stay in your cloud storage, in the same folder;
- your sign-ins, game list and history stay in Haversack's settings folder on each device.

To use them again, open **Settings**, **Updates**, and install version 0.60.0 from the list of earlier versions. Everything is where you left it. Version 0.60.0 still tells you about later versions; installing one removes save sync again, without deleting anything.

## Keepsake is now Haversack

Version 0.51.0 renamed Keepsake to Haversack. On a handheld, update Keepsake as usual. Decky installs Haversack beside Keepsake, at the top of its list:

1. Open Haversack in the Quick Access Menu. It shows one card, "Keepsake is now called Haversack". Until you go on, Keepsake keeps working and Haversack does nothing, so the two never sync at once.
2. Press **Remove the old Keepsake** and confirm. Haversack removes Keepsake (and Keepsake Helper, if you had it), copies your settings, sign-ins, games and history across, checks every file, and starts.

Nothing is lost:
- Your old copy stays on the device.
- Your cloud folder keeps its name, so your other devices carry on before they update.

To go back, remove Haversack in Decky's settings and install an earlier Keepsake from the Releases page. If you later update again, Haversack brings in what Keepsake did meanwhile, and keeps its own earlier copy aside.
