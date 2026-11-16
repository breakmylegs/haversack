# Cutover from Ludusavi and rclone to Keepsake

Build prompt section 19. The interim setup (the Ludusavi flatpak with decky-ludusavi, syncing to OneDrive through rclone, with five Ludusavi redirects) keeps running until Keepsake has proved itself, then it is removed. At no point do both tools restore over each other.

## 1. Legion Go 2 first (the starting source)

1. Install Keepsake from `https://github.com/breakmylegs/keepsake/releases/latest/download/Keepsake.zip` (Decky, Settings, Developer, Install Plugin from URL).
2. Open it and complete the setup wizard: device name, OneDrive sign-in (`docs/setup-entra.md`), scan, review matches, choose the non-Steam games.
3. In decky-ludusavi, turn off automatic sync for every game Keepsake now syncs. Keepsake's health check warns while decky-ludusavi is active alongside synced games.
4. Play and quit each game once, or use Sync now: the first pushes upload the current saves.

## 2. Legion Go

1. Install Keepsake the same way and complete the wizard, choosing the same games.
2. Games whose saves are already the same as the Legion Go 2's adopt silently, because the hashes match. Any that differ raise a conflict: choose which save to keep. The other is kept and pinned.
3. Turn off decky-ludusavi's automatic sync for those games on this device too.

## 3. Optional: bring in the Ludusavi history

On either device: Keepsake, Import, read `~/ludusavi-backup` (or choose the folder), then Import all for the games you care about. Old backups appear in History with their original dates. They never replace current saves; restore one only if you need it.

## 4. Two weeks of both

Keep decky-ludusavi installed but with automatic sync off for Keepsake's games. Check Diagnostics, Run checks now and then. Any problem: the Ludusavi backups are still there and untouched.

## 5. Remove the interim setup

After two weeks without issues:

1. Remove decky-ludusavi from Decky.
2. Remove the Ludusavi flatpak. Its five redirects go with it.
3. Optionally delete the rclone remote and the old OneDrive folder once you no longer want those backups. Keepsake never touches them; it uses only `Apps/Keepsake`.
