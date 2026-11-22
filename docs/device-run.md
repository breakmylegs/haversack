# Device run for v0.41.1

No SSH, terminal or laptop is needed. Do the first two parts on each handheld, then the rest with both. "Go" is the Legion Go and "Go 2" the Legion Go 2.

## 1. Install v0.41.1 (each handheld)

1. Open the Quick Access Menu, then Decky, then Keepsake, then the full Keepsake page.
2. Open **Updates**, press **Check for updates**, then **Update now**. Confirm Decky's prompt to install v0.41.1, and Decky reloads Keepsake.
3. In **Settings**, then **Modules**, switch on **Replication**. On **Devices**, switch on **Let other devices reach this one**.

## 2. Device checks (each handheld)

1. Put the SD card in.
2. In Keepsake's sidebar, open **Diagnostics** and scroll to **Device checks**. Press **Run all**. It takes about a minute. Checks marked "(both)" say Skipped until part 3.
3. Press **Export results**, and photograph the QR code or the summary.

## 3. Both handhelds

1. **Pair** (both with **Let other devices reach this one** on). First run the Device check **The other handheld can be seen** on each.
   - On the Go 2, press **Find devices**, choose the Go and press **Pair**. The Go 2 should say "Waiting for Legion Go to accept".
   - The Go should show "Legion Go 2 wants to pair" with its address. Press **Accept**. The Go 2 should say "Legion Go accepted. Enter the code shown on it."
   - Type the Go's 6-digit code on the Go 2's number pad with the controller and press **OK**. Both should show **Paired**.
   - Also try once: a wrong code (both should say it was wrong), **Decline** on the Go, and a request while a game runs on the Go (only a notification; answer it afterwards under Devices).
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

7. **Advisor sessions.** Run the Device check **Session stats sources** and photograph it. Then play any game for 5 minutes on battery and quit. Open Keepsake's Advisor page for that game: it should show a **Last session** card with watts, temperatures and battery, and a frame rate or "frame rate not available". Run **Session stats sources** again: it should now say whether a frame rate was seen.

8. **Two save locations.** On the Go, open the Cloud page and add a second save location (for example **Directly between my devices** next to OneDrive). Play and quit a synced game. Both locations should list it as reached, with nothing left to copy. Turn the Wi-Fi off, play and quit again (it should not block), turn it back on, and after a few minutes the Cloud page should show nothing left to copy.

9. **Desktop tray responsive.** With the USB disk attached (and the EmuDeck folders on it), switch to Desktop Mode. Open the Keepsake tray menu repeatedly and use the taskbar and start menu for a minute: nothing should freeze. Run the Device check **Desktop tray responsive** from the desktop page's Diagnostics: it should pass, with both times under 200 ms.

10. **Sending a game, both sides (v0.30.2).**
    - Send Factorio (or any non-Steam game) from the Go to the Go 2 and accept it on the Go 2.
    - The Go's Devices page should change from "offered" to "copying", then "adding to Steam", then "arrived".
    - Send another game, and on the Go 2 choose a library folder without enough space, or pull the SD card while it copies. The Go 2 should show it as failed with the reason. The Go should show "did not arrive" with the same reason, and a toast.
    - On the Go 2, run **Device checks** and press **Export results**. The file should have a "replication" part with the states, and no game titles.

11. **OneDrive sign-in (v0.31.0).**
    - On the Cloud page, press **Sign in with OneDrive** and finish in Steam's browser. It should end on "You're signed in", never a "cannot connect" page.
    - Reload that page within 2 minutes: it should still say "You're signed in".
    - Start again. While the browser is open, press **Use your phone instead** and finish on your phone. The toast should say "Signed in with your phone". If you go back to the browser tab, it should say you signed in on your phone.

12. **Windows share, Windows-style (v0.30.2).**
    - In Install, then From a network location, then Windows share (SMB), press **Find shares** and pick your server. Its shares should be listed, or a plain sentence should say why (for example that it needs a user name and password). There should be no "Python" or error-type text.
    - Type the address the Windows way, `\\yourserver\yourshare`, with your user name (try `YOURPC\yourname` if the PC is not on a domain) and password, and turn on **Remember this location**. Press **Browse**: its folders should be listed.
    - Come back later, pick the remembered location and press **Browse** again: it should list the same folders.

13. **Pairing both ways (v0.31.0).** If the Go and the Go 2 are already paired, remove each from the other first. On the Go, switch off **Let other devices reach this one**. Pair from the Go to the Go 2. When it finishes, the Go should show "Games can now go both ways between you", and its toggle should be on.

14. **No Accept, and bars on both devices (v0.31.0).**
    - Send a non-Steam game from the Go to the Go 2. The Go 2 should start copying by itself, with the toast "<game> is coming from Legion Go". There should be no Accept button.
    - Both devices should show a bar on Devices: percentage, GiB done of the total, speed, time left, and the stage (Copying, then Verifying, then Adding to Steam, then Done).
    - Open the quick access menu on each device: a compact line should show the same progress.
    - Close the Keepsake page and open it again: the bar should carry on from where it was.

15. **Space check (v0.31.0).** On the Go 2, choose an SD card or folder with too little space as the library. Send a large game from the Go. The Go should stop at once with "Legion Go 2 doesn't have enough space: needs ... GiB, has ... GiB free", before it reads the game's files.

16. **Get this game (v0.31.0).** On the Go 2, on Devices, press **Games on Legion Go**, pick a game and press **Get this game**.
    - The Go should toast "<game> is being copied to Legion Go 2".
    - The Go 2's bar should go from Checking space to Preparing to Copying.
    - The game should end up in the Go 2's library with its artwork, launch options and compatibility tool.

17. **Stop and remove from each side (v0.31.0).**
    - Start a copy and press **Stop and remove** on the sending device. The receiving device should stop and delete what it made, and both bars should go.
    - Start another and press **Stop and remove** on the receiving device. The sending device should toast "<device> stopped and removed <game>".

18. **Desktop app (v0.31.0).** In Desktop Mode, open Keepsake's Devices page during a copy. The table should show the game, device, stage, a moving progress bar, GiB, speed and time left, with **Stop and remove**.

19. **New layout (v0.32.0).**
    - Open Keepsake. The sidebar should show Play, Saves, Games and devices, Device, Install, Settings and Diagnostics, with lines between the groups.
    - In each, the tabs along the top should move with the D-pad and open their page.
    - Open the quick access menu while a game runs. Now playing, then Keepsake, should fit on one screen without scrolling.
    - From the quick access menu, press a conflict or update line: it should open the right tab.

20. **Device, Status (v0.32.0).** It should name the Legion Go or Legion Go 2 (not "generic"), its power range, its screen and the battery level and charging state.

21. **Desktop app (v0.32.0).** In Desktop Mode, open Keepsake:
    - The sidebar should have the same groups.
    - Type "Background" in Search settings and press Enter: the setting should be highlighted.
    - In Games, sort by each column and filter by state.
    - Advisor should show charts of your last sessions.
    - Diagnostics, Device checks, Run all should work, and **Desktop tray responsive** (step 9) can be run here.

22. **Device readings (v0.33.0).**
    - Open Device, Status. The temperatures, fan speed, power, performance mode and BIOS lines should fill in and change every couple of seconds.
    - Run the Device check **Device readings** and photograph it: it lists what each device exposes, including fan speed, the firmware modes and the charge limit.
    - On the Legion Go and the Legion Go 2, open Legion Space's mode (Legion L plus Y) or Steam's performance overlay and change the mode. Status should follow it.

23. **Performance profiles (v0.34.0).**
    - Run the Device check **Performance control** and photograph it.
    - Start a game. In the quick access menu, set the mode to Performance and the TDP to 15 W.
    - Quit. Steam's performance overlay should show the previous values again.
    - Start the game again: the mode and TDP should come back by themselves.
    - Sleep and wake the device during the game: the profile should still be applied.

24. **Never fight (v0.34.0).**
    - In Steam's own performance settings, turn on a per-game TDP limit for that game, then start it. Within a few seconds Keepsake should say another app changed it, and leave Steam's value.
    - If SimpleDeckyTDP or another tool is installed, Device, Power should name it and show the settings read-only.

25. **Battery charge limit (v0.35.0).**
    - Run the Device check **Battery charge limit** and photograph it.
    - Open Device, Battery. Either turn on **Stop charging at 80%**, or note where it tells you to change it.
    - If you changed it in Steam's settings, Battery should show the new state.

26. **Controllers (v0.36.0).**
    - Run the Device check **Controllers** and photograph it.
    - Open Device, Controllers. It should show both controllers' batteries, and their settings and lights if the kernel shows them.
    - Detach one controller. Its battery should go, and come back when you attach it.

27. **Other (v0.37.0).**
    - Run the Device check **BIOS check** and photograph it.
    - Open Device, Other. Turn Wi-Fi power saving off and on: it should follow, or say it is not offered.

28. **Take the newest (v0.38.0).**
    - On the Go 2, set Settings, Sync and safety, **When saves differ** to **Take the newest**.
    - Turn the Wi-Fi off on the Go 2, play a synced game for a minute and quit.
    - Wait at least 2 minutes. Play the same game on the Go and quit.
    - Turn the Go 2's Wi-Fi back on and start the game there. Keepsake should keep the Go's newer save, say so in a toast, and show **Undo** in the game's History.
    - Press **Undo**: the Go 2's version should come back.

29. **Badges and streaming artwork (v0.39.0).**
    - Open a synced game's page in Steam's library. A "Keepsake · Saves: in step" label should show near the top right, and the page should otherwise work as before.
    - Open a game that streams from the other device: it should say where it streams from.
    - On Install, under **Artwork for streaming tiles**, press **Find artwork** for one, pick the game, and check the tile gets its artwork.

30. **Sidebar (v0.39.1).** Open Keepsake's full page.
    - Move with the D-pad from **Play** down to **Diagnostics** and back up again, through every entry.
    - Press each one in turn: the page that opens should match the entry pressed.
    - In a section, move right along its tabs and down into a tab, then press B: focus should go back to the sidebar.

31. **Reconnect help: the list (v0.40.0).** Open Device, Reconnect help.
    - Every paired Bluetooth device should be listed, with its class, modalias and adapter, and the clone should show the "not from a registered manufacturer" note.
    - Run the Device check "Controller reconnect help": it should pass, with the journal readable.
32. **Reconnect help: pair and commit.** Turn help on for the clone DualShock 4 only.
    - Forget it in Steam's Bluetooth settings and pair it again.
    - Then turn it off and on with PS alone, ten times: it should reconnect ten of ten.
    - Both genuine DualShock 4 pads, and any other controller, should still reconnect ten of ten, and Bluetooth audio should keep playing.
33. **Reconnect help: diagnose, USB and export.**
    - Run Diagnose on the clone: power off, wait 10 seconds, Start, press PS once. Note the outcome.
    - Connect the clone by USB and select Read stored host over USB. Note the answer.
    - Export the report bundle: this handheld's address should not appear in it.
34. **Reconnect help: Reconnect, and lasting state.**
    - With the clone off, open the quick menu, hold Share and PS, and select Reconnect: it should connect within 15 seconds.
    - Reboot, then update SteamOS when one is offered: help should still be on and step 32 should still pass.
    - Desktop Mode should stay responsive throughout.

35. **Keepsake Helper (v0.41.0).** In Device, Reconnect help, select Install helper.
    - Decky should ask to install "Keepsake Helper", and the card should then say Ready.
    - Run the Device check "Controller reconnect help": the helper should be ready.
36. **Cable pairing.** With the clone DualShock 4 on a USB cable and help on for it, select Cable pair, then Confirm.
    - Bluetooth should restart, with the genuine pads dropping and coming back.
    - Unplug the clone, turn it off and press PS, ten times: it should reconnect ten of ten. Both genuine pads should still reconnect ten of ten.
    - Restore backup should put the old pairing back.
37. **SSP gate.** Only if a diagnosis says O3: turn the SSP gate on through both warnings.
    - Note whether it said "Restart Bluetooth" (SSP off needs the adapter off).
    - The clone should reconnect with PS ten of ten, and pairing a new device from Steam should still work.
    - Switch the gate off: SSP should be on again. Turn it on again and disable Keepsake in Decky: SSP should come back on within about 2 minutes.
38. **Capture.** Run Diagnose with the helper ready: the result should say the capture was read. Export the bundle without redaction: it should contain `hci.btsnoop`.

39. **Navigation (v0.41.1).** Open Keepsake's full page.
    1. With the D-pad, go down every sidebar entry slowly, then up again. The highlight must stay on the entry you moved to, and nothing should open or move by itself.
    2. Enter every page with right or A, and come back with B.
    3. Do it once straight after opening Keepsake, and once after a minute.
    4. If anything jumps, open Diagnostics, Tools, select Record navigation, repeat the moves for 60 seconds, then export the Device checks results.

40. **Reconnect help in the desktop app (v0.42.0).** In Desktop Mode, open Keepsake's desktop app, Device, Reconnect help.
    - The paired devices and their help switches should match Gaming Mode.
    - Run Diagnose on the clone from there.
    - The app should stay responsive throughout.

## 5. Send back

- The photos or files from parts 2 and 3.
- Any written step above that did not behave as described, with its number.
