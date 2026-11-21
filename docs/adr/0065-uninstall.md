# ADR-0065: Uninstall Steam and non-Steam games from Keepsake

- Status: accepted (Peter's request of 21 November 2026, decided under ADR-0037). Extends ADR-0015.
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

Peter wants an **Uninstall** on each game's page:
- **Steam games:** through Steam's own uninstall.
- **Non-Steam games:** everything for the game on this device:
  1. a final save backup;
  2. the shortcut and its artwork;
  3. the Proton prefix and the install folder;
  4. Keepsake's own records.

ADR-0015 only let Keepsake remove shortcuts it created itself (the Installer's `Install:` shortcuts). Deleting folders is the most dangerous thing Keepsake has done so far: a mistake loses a game, someone else's files or a home folder.

## Decision

1. **Steam games: Steam stays in charge.**
   - Keepsake offers a final backup if the game is synced, then opens `SteamClient.Installs.OpenUninstallWizard([appid], false)`, verified in the `@decky/ui` 4.16.5 types, through the Steam Operations Executor as a new `open-uninstall` kind.
   - Steam's wizard asks for confirmation and removes the install folder, manifest and library state. Keepsake deletes nothing for a Steam game.
2. **Non-Steam games, in this order, in the background, with progress and Stop:**
   1. **Final backup** if the game is synced: a push to the cloud or the paired devices.
      - It counts as done when the push is published, published as a fork, unchanged, or had nothing to save.
      - Anything else stops the uninstall before anything changes. The user can then choose **Uninstall without a final backup**.
      - The job then says where to restore from: the game's History on any device syncing with the same store.
   2. **Shortcut and artwork,** through the executor as `remove-shortcut` with `clearArtwork`:
      - `ClearCustomArtworkForApp` for asset types 0 to 4, then `RemoveShortcut`;
      - read back with `appStore.GetAppOverviewByAppID`, then app details;
      - nothing is deleted unless Steam no longer lists the app;
      - if Steam does not answer within 5 minutes (no Gaming Mode frontend), the job stops before deleting anything.
   3. **Prefix and install folder,** each through the guards below, checked when the plan is made and again just before deleting. A folder that fails the second check is kept and reported.
   4. **Keepsake's records:** the game's settings on this device, an open match proposal, a Replication link for the app ID, and finished Installer jobs for it. History in the cloud stays, so the saves can come back.
3. **The guards** (`keepsake/uninstall.py`):
   - **Prefix:** exactly `<library>/steamapps/compatdata/<appid>` of a known library, for this game's app ID. Not a link, not a mount point, present.
   - **Install folder** (the shortcut's start folder, else the exe's folder). Every one of these must hold:
     - a full path, not a link, present, not a mount point;
     - strictly inside the home folder, a Steam library or a removable drive;
     - deleting it removes no protected folder. Protected folders are:
       - the home folder, and in it Desktop, Documents, Downloads, Music, Pictures, Videos, Games, `.local`, `.local/share`, `.config`, `.cache`, `.steam`, `.var`, `homebrew` and Applications;
       - every Steam root, and in each library `steamapps`, `steamapps/common`, `steamapps/compatdata` and `steamapps/shadercache`;
       - Keepsake's settings, runtime and log folders, and the Installer's library folder;
       - every removable drive's mount point, `/run/media`, `/media` and `/`;
     - no other game's folder, exe or prefix is inside it, and it is not inside one: other shortcuts' start folders, exes and prefixes, Steam games' install folders, other launchers' Wine prefixes.
   - **A game installed inside its prefix** goes with the prefix.
   - **Deletion** walks bottom up and never follows links: a link is removed, never what it points at. It stops between files on Stop.
4. **Refusals:**
   - while the game runs;
   - while another module holds the game's lock (P19): the job holds it throughout;
   - for a streaming entry (ADR-0064), and for any shortcut Steam says is installed on another device;
   - for anything that is not a Steam game or a non-Steam shortcut.
5. **Confirmation:**
   - The screen lists exactly which folders will be deleted, with their sizes and the free space after, plus what will not be deleted and why. It says whether a final backup is taken and where.
   - **Cancel** comes first and is focused (`Focusable autoFocus`, A204). **Uninstall** needs an explicit press.
6. **Desktop app:** no Uninstall button there, because removing a shortcut needs the Gaming Mode frontend (ADR-0015 executor); a request from Desktop Mode would only wait and time out. The Gaming Mode page is where it applies.
7. **ADR-0015 extended.** `remove-shortcut` may now remove any real local shortcut the user uninstalls, with its custom artwork, after the confirmation screen; `open-uninstall` opens Steam's wizard. Nothing else changes: no VDF writes, no shortcut field edits.
8. **Logged:** the start, the outcome (done, cancelled, failed with the reason) and the app ID go to the log.

## Consequences

- Stopping part way leaves a folder partly deleted. The job says so, and the rest is kept.
- A folder that the guards refuse is kept, and the screen says why. The user can delete it themselves if they mean to.
- T124 in `docs/threat-model.md`; A203 to A205 in `docs/assumptions.md`.
