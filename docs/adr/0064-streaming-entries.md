# ADR-0064: Games you can stream from another device (Steam Remote Play entries)

- Status: accepted (Peter's requests and correction of 21 November 2026, decided under ADR-0037). Amends ADR-0015.
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

Peter's two handhelds are on the same Steam account but not paired in Keepsake. Each shows the other's non-Steam games as blank tiles whose menu offers **Stream**. Some share a name with a game installed locally. Peter checked on the devices: these are **Steam Remote Play** entries for games installed on the other handheld. Keepsake did not create them, and Steam is not malfunctioning. Related Steam reports describe the same entries and how they behave:
- [steam-for-linux #13141](https://github.com/ValveSoftware/steam-for-linux/issues/13141): entries from other devices appear, come back after removal, and go away when Steam on the other device stops.
- [#12315](https://github.com/ValveSoftware/steam-for-linux/issues/12315): with the same game on both devices, Play can turn into Stream.

Keepsake must never treat a streaming entry as a game on this device, for save sync, Send to, Replication, Advisor or Uninstall. It must also never lose a real local game from its lists.

## Findings

These are verified from the `@decky/ui` 4.16.5 types and the reports above. What a device actually shows is in `docs/assumptions.md` (A199 to A202) for Peter's device run.

1. **Not in `shortcuts.vdf`.** A streaming entry vanishes as soon as the other device's Steam stops, and comes back when it starts. That is a live entry from the other client, not a line in this device's `shortcuts.vdf`, which Steam reads at start (A199). Anything Keepsake finds in `shortcuts.vdf` is therefore a real shortcut of this device, even with an unusual exe path, a removed SD card or no prefix.
2. **Steam's own view, from the frontend.** `appStore.m_mapApps` holds every library entry as an `IAppOverview`:
   - `BIsShortcut()` marks non-Steam shortcuts;
   - `GetPerClientData("local")` (or `local_per_client_data`) carries this client's `installed`;
   - `per_client_data` lists each client that has the app, with `clientid`, `client_name` and `installed`.

   A streaming entry is one this client does not have installed while another client does (A200).
3. **App IDs and the hidden collection.**
   - A shortcut's app ID comes from its exe and name, so a streaming entry very probably has the same app ID as the real shortcut on the other device.
   - Steam keeps collections, the hidden one included, in the account's cloud storage.
   - So hiding a streaming entry here could hide the real, playable game on the other device (A201).
   - Removing an entry does not last (#13141).

## Decision

1. **Presence of each shortcut in `shortcuts.vdf`:**
   - **From the file** (`discovery.shortcut_presence`): `local` if the exe or the start folder exists, or there is a prefix; otherwise `unsure`. **Never remote.**
   - **With Steam's report** (`remotecopies.combine`): Steam saying installed here makes it `local`. Steam saying another device has it makes it `unsure`, labelled, never hidden. Otherwise the file decides.

   An `unsure` shortcut stays in the Games list, matching and every other list, so a real game is never lost. The old fixtures with made-up exe paths therefore keep working unchanged. A test pins the case: a shortcut with an unusual exe path and no prefix stays listed even when Steam says it streams.
2. **Streaming entries:**
   - **Detection:** an entry only in Steam's report (`src/remotecopies.ts`, read only, every 5 minutes and on the Games page), which another client has installed and this one does not. It is never in Keepsake's game lists, because those come from `shortcuts.vdf`.
   - **Advisor:** looks games up by app ID in that list, so a streaming entry gets general advice only.
   - **Uninstall** (ADR-0065): refuses anything not in `shortcuts.vdf`, or any shortcut Steam says streams.
3. **Shown, not changed.** Under Games and Settings, **Games you can stream from another device** says how many there are. **Show games you can stream from another device** lists them, with the device Steam names and whether the same game is installed here. The user guide points to Steam's **Installed** tab, or switching off Remote Play in Steam's settings, to keep the library tidy.
4. **The tidy-up is built but off and unseen.**
   - **What exists:** hiding through the Steam Operations Executor (`set-hidden`, `SetAppsAsHidden`, read back with `BIsHidden`), the log with Undo across restarts, and the automatic option.
   - **The gate:** it is all behind `streamTidyVerified`. That setting is off, and the frontend cannot change it: it is not in `USER_KEYS`. While it is off, the button and the automatic option are not shown and the backend refuses to hide anything.
   - **What turns it on:** a later version, once Peter's device run shows that hiding a streaming tile on the Go leaves the same game visible, with Play, on the Go 2 (A201). If it does hide the real game, the tidy-up needs the devices to compare app IDs over a pairing first.
   - **When it is on,** it hides only entries Steam itself says are on another device and which are not in `shortcuts.vdf`, after a press or the automatic option the user chose.
5. **The guard stays on.** Each device remembers which of its local shortcuts were visible. If one becomes hidden without a tidy-up on this device, for example from the other device, it says so, and **Show it again** unhides it. Unhiding is allowed only for shortcuts Steam says are local.
6. **Device check:** "Games you can stream from another device":
   - counts shortcuts installed here, streaming entries and unsure ones (plus any hidden or come back, once the tidy-up exists);
   - lists games installed here that also stream;
   - fails if a synced game is one Steam says streams.

   No device names appear in its findings.
7. **ADR-0015 amended.** Setting an app's hidden state is a Steam write Keepsake may make, through `SteamClient` from the frontend and read back, on these terms only:
   - showing again a local shortcut the guard found hidden;
   - once verified, hiding streaming entries.

   Shortcut fields, launch options and VDF files are unchanged.

## Consequences

- No real game leaves Keepsake's lists because of its paths. One whose game folder is gone is labelled "not found on this device".
- The library stays as Steam shows it until the tidy-up is verified. T122 and T123 in `docs/threat-model.md`.
