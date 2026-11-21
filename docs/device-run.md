# Device run for v0.27.0-beta.1

No SSH, terminal or laptop is needed. Do the first two parts on each handheld, then the rest with both. "Go" is the Legion Go and "Go 2" the Legion Go 2.

## 1. Install v0.27.0-beta.1 (each handheld)

1. Open the Quick Access Menu, then Decky, then Keepsake, then the full Keepsake page.
2. Open **Updates**, set the channel to **Pre-release**, press **Check for updates**, then **Update now**. Confirm Decky's prompt to install v0.27.0-beta.1, and Decky reloads Keepsake.
3. In **Settings**, then **Modules**, switch on **Replication**. On **Devices**, switch on **Let other devices reach this one**.

## 2. Device checks (each handheld)

1. Put the SD card in.
2. In Keepsake's sidebar, open **Diagnostics** and scroll to **Device checks**. Press **Run all**. It takes about a minute. Checks marked "(both)" say Skipped until part 3.
3. Press **Export results**, and photograph the QR code or the summary.

## 3. Both handhelds

1. **Pair.** On the Go, press **Let a device pair with this one**. On the Go 2, press **Find devices** and choose the Go.
   - Check that both screens show the same 6-digit code.
   - Press **The codes match** on both.
2. **Two-device checks.** On the Go 2, run **Link speed to the other handheld** and **Finding the other handheld**, then **Export results** again. Photograph it.
3. **Reconnect.** Restart the Go. On the Go 2, go to Devices and press **Check** on the Go: it should say reachable.
4. **Send a game.** On the Go 2, open an ISO-installed non-Steam game in Keepsake's Games and press **Send to Legion Go**. On the Go, go to Devices and press **Accept**. If it offers to copy the compatibility tool, say yes.
   - While it copies, press the power button once. The Go should sleep within a few seconds, and the transfer should carry on after you wake it.
   - When it says "ready", start the game on the Go. Check the Proton version, artwork and launch options, that your saves are there, and that Saves shows no conflict.
   - If you copied the tool, restart Steam first if asked.
5. **Game hold.** Send a second game. While it copies, start any game on the Go: the transfer should wait, then carry on when you quit.
6. **Keep in step.**
   1. On the Go 2, change the game (a patch, or a mod file in its folder), play, and quit. Its Keepsake page should say "Changed on this device". Press **Send update**. On the Go, go to Devices and press **Apply update**. The change should be there, and the Go's saves unchanged.
   2. Set **Updates** to **Take them by themselves** on both, change the game again on the Go 2, and check the Go takes it without asking.
   3. Change the game on both, then send an update. The Go should ask. Choose **Keep mine**: nothing should change on the Go.
7. **Stop and remove.** Send a game again, and press **Stop and remove** part way. The game should not be in the Go's library, and its folder should be gone.
8. **Saves with no cloud.**
   1. On both, go to the Cloud page and choose **Directly between my devices**.
   2. Play a game with Saves on the Go 2 and quit. On the Go, press **Sync now**. History should show the new save, and starting the game should load it.
   3. Turn the Go 2 off. Play and quit on the Go: it should not block, and should say the Go 2 was not reachable.
   4. Play on both while apart, then bring them together. A conflict should appear and resolve as usual.
9. **Remove.** On the Go, go to Devices and press **Remove** on the Go 2. On the Go 2, **Check** should say to pair again.

## 4. New in 0.27.0

1. **Steam games.** Open Keepsake's Games page on the Go.
   - It should open on **All**, show Steam games, and have a note saying how many sync automatically.
   - A Steam game you have played that has no Steam Cloud saves should say "no Steam Cloud, synced automatically". One that uses Steam Cloud should say "off until you turn it on".
   - Turn one of the automatic ones off, rescan, and check it stays off.
   - Play an automatic one on the Go and quit. Start it on the Go 2: it should load the save, and History should show it on both.

2. **Games you can stream from another device.** With Steam running on both handhelds:
   - On the Go, run the Device check **Games you can stream from another device**. It should count the Go 2's non-Steam games, and list "Split Fiction" as also installed here.
   - On the Games page, every non-Steam game installed on the Go should be listed, Split Fiction once, and none of the Go 2's games. **Show games you can stream from another device** should list them.
   - **Hidden test (A201).** In Steam on the Go, open the menu of one streaming tile and choose Hide (Manage, Hide this game). On the Go 2, check that the same game is still in the library and shows **Play**. Tell me the result. Then on the Go, show it again from Steam's Hidden collection.

3. **Uninstall** (use games you do not mind losing, ideally small test installs).
   - **Non-Steam:** on the Go, open a synced non-Steam game in Keepsake and press **Uninstall**.
     - The screen should list the Proton prefix and the game folder with sizes and free space after.
     - **Cancel** should be selected first. Press **Uninstall**.
     - Watch the progress. The tile and its artwork should leave Steam, the folders should be gone, and the job should say where to restore the saves.
     - On the Go 2, the game's History should show the final backup.
   - **Stop:** start an uninstall of a bigger game and press **Stop** part way. It should stop and say what was kept.
   - **Refusals:** try it while the game runs (refused), and on a game you can stream from the Go 2 (it should not offer Uninstall, or refuse).
   - **Steam game:** on a synced Steam game, press **Uninstall**. Take the final backup, then Steam's uninstall should open. Confirm it there.

4. **Find shares.** With a NAS or a Windows PC sharing a folder on the same network:
   - Run the Device check **Find shares on my network**. It should find at least one server and say which ways answered.
   - In Install, then From a network location, then Windows share (SMB), press **Find shares**. Pick your server: its shares should be listed. Open one and browse to an ISO, as before.

5. **Network ISO in place.** In Desktop Mode, open your NAS share in the file manager so it is mounted, with an ISO on it. Switch back to Gaming Mode, run the Device check **Network ISO in place**, and photograph it. It should say whether an ISO on that share opens in place, and whether fusermount3 and /dev/fuse are there.

6. **Desktop app.** On the Go, run the Device check **Desktop app ready** once in Gaming Mode (it says to run it in Desktop Mode for the session bus). Then switch to Desktop Mode:
   - The Keepsake icon should appear in the system tray, with no window.
   - Click it: Keepsake should open in the browser. Close the window: the icon should still be there.
   - Open Keepsake from the app menu: the same Keepsake should come up, not a second icon.
   - Right-click the icon and press **Quit**: the icon goes. Log out and back in: it comes back.
   - In Diagnostics (in the browser page), run **Desktop app ready** again: it should pass.

## 5. Send back

- The photos or files from parts 2 and 3.
- Any written step above that did not behave as described, with its number.
