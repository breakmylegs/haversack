# Device run for v0.61.0

No SSH, terminal or laptop is needed. Do the first two parts on each handheld, then the rest with both. "Go" is the Legion Go and "Go 2" the Legion Go 2. The device run for v0.60.0 and earlier, with the steps for removed features, is in the git history and on the `full` branch.

## 1. Update to v0.61.0 (each handheld)

1. Open Haversack, **Settings**, **Updates**, press **Check for updates**, then install 0.61.0. If the device is still on Keepsake, update it first as before: Haversack appears and asks to remove the old Keepsake.
2. After the update, **What's new** should say save sync and the other features were removed, and that nothing was deleted.
3. The sidebar should have four sections: **Install**, **Games and devices**, **Settings**, **Diagnostics**.
4. In **Settings**, **Modules**, Installer and Replication should both be on.
5. In **Settings**, **General**, **Game database** should show a number of games and when it was updated, with the Ludusavi credit.
6. Switch to Desktop Mode once: no Haversack tray icon should appear, and Haversack should not be in the app menu. Switch back.

## 2. Device checks (each handheld)

1. Put the SD card in.
2. Open **Diagnostics**, **Device checks** and press **Run all**. It takes about a minute. Checks marked "(both)" say Skipped until part 3.
3. Press **Export results**, and photograph the QR code or the summary.

## 3. Install

1. **From an ISO.** On the Go 2, open **Install**, choose an ISO, and follow it through to the game's program. At the end, **Open in Games** should open **Games and devices**, **Games** with the game listed.
2. **From a network share.** Install another game from **From a network location**, with **Find shares** or a typed `smb://` address.
3. **Artwork.** With a SteamGridDB key, open the new game in **Games**, press **Find artwork** and pick it: the missing artwork should appear in the library.
4. **Update waits for a game.** Start any game, then open **Settings**, **Updates**: installing a version should be refused until you quit.

## 4. Both handhelds

1. **Pair.** On both, open **Games and devices**, **Other devices**, and switch on **Let other devices reach this one**.
   - On the Go 2, press **Find devices**, choose the Go and press **Pair**. Accept on the Go and type its code on the Go 2. Both should show **Paired**.
   - Run the Device checks **Link speed to the other handheld** and **Finding the other handheld** on the Go 2, then **Export results** again. Photograph it.
2. **Send a game with its saves.** Play the game from part 3 on the Go 2 until it has a save, and quit. Open it in **Games** and press **Send to Legion Go**.
   - The Go should start copying by itself, with a bar under **Moving games** and a line in the quick access menu.
   - When it says ready, start the game on the Go. Check the Proton version, artwork and launch options, and that **your save is there**.
3. **Keep in step, saves kept.**
   1. On the Go, play on and save, so the Go's save is newer. Quit.
   2. On the Go 2, change the game (a patch, or a mod file in its folder) and quit. Its page should say it changed. Press **Send update**; on the Go, **Apply update** under Moving games.
   3. The change should be on the Go, and **the Go's own newer save should still be there**, not the Go 2's.
4. **Stop and remove.** Send another game and press **Stop and remove** part way: it should leave the Go's library, and its folder should be gone.
5. **Emulators.** Open **Games and devices**, **Emulators** on the Go 2 and send one emulator game; accept it on the Go.
6. **Get a game.** On the Go, **Other devices**, **Games on Legion Go 2**, choose one and press **Get this game**.

## 5. Going back

On one handheld only, open **Settings**, **Updates** and install **0.60.0**. Saves, Conflicts and History should be back as they were, with your cloud sign-in. Then update to 0.61.0 again.

## 6. Send back

- The photos or files from parts 2 and 4.
- Any step above that did not behave as described, with its number.
