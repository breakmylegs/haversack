# Keepsake layout v3: the quick access menu, the full page and the desktop app

Peter's request of 21 November 2026 (item 2): Keepsake is becoming his main Legion Go app, so review the whole information architecture before the device controls arrive. The decisions are in ADR-0073. This document is the reference for where everything lives from v0.32.0.

## 1. The structure today (v0.31.1)

### Quick access menu

One long "Status" section, then the Advisor's section:

1. A status line: health, the save location, the last sync and the version.
2. Up to three problems.
3. Set up Keepsake (until setup is done).
4. Playing: the game and its sync state.
5. Save checkpoint.
6. A line for each newer save on another device.
7. A first-run tip, with Got it.
8. Conflicts waiting.
9. Safe mode.
10. Update available.
11. Moving games (v0.31.0).
12. Sync now.
13. Open Keepsake.
14. Advisor: recommendation lines and Open Advisor.

### Full page (Gaming Mode)

13 sidebar items in one flat list, each shown while its module runs:

| Item | Holds |
|---|---|
| Games | Search, the game list; each game opens a detail page with identity, sync, launch gate, snapshots, save locations, Send, linked copies and Uninstall |
| Conflicts | Each conflict, compare and choose |
| History | Snapshots by game, restore and pins |
| Import saves | The Ludusavi import |
| Advisor | Recommendations, last sessions, PCGamingWiki, AI |
| Devices | Moving games, updates waiting, low-level transfers, pairing, the listener, paired devices, Games on a device |
| Install | Disc images, network locations, the queue |
| Settings | Safe mode, device name, pre-releases, safety gates, timeouts, background sync, toasts, Steam games, registry keys, Steam Cloud, sleep snapshots, other launchers, the Cloud section, zip export, tidy copies, modules, device ID, Setup |
| Updates | Check, update, release notes, roll back |
| Activity | What Keepsake did, newest first |
| Storage | Disk use per game, shader caches, prefix reset |
| Logs | The log tail |
| Diagnostics | Health, probes, the freeze test, the sign-in browser test, device checks, the diagnostics export |

### Desktop app

12 pages: Overview, Conflicts, Games, Cloud, Import, Devices, History, Activity, Health, Modules, Updates, Settings. These are mostly the Gaming Mode pages drawn as cards. There is no Advisor, Install, Disk use, Logs or Device checks.

## 2. Problems

1. **Too many top-level items.**
   - 13 in Gaming Mode and 12 on the desktop, in no order a player would guess.
   - Related things are apart: History and Activity, Logs and Diagnostics, Settings and Updates.
   - Storage stands alone.
2. **Settings are scattered.**
   - Saves' options sit in Settings.
   - The other modules' settings sit in their own pages: the AI keys in Advisor, the listener in Devices, the library folder in Install.
   - The Cloud section is half-way down Settings.
   - Updates is its own tab, but its pre-release switch is in Settings.
3. **The names are unclear or about to clash.**
   - "Devices" (your other handhelds) will clash with the coming "Device" (this handheld's controls).
   - "Storage" means disk use, not cloud storage.
   - "Activity" and "History" sound alike.
   - "Import saves" sits next to "Install".
4. **The quick access menu is a scroll.** A game in play competes with tips, update notices and setup. The Advisor is a second section. There is no room for the device controls Peter will touch while playing.
5. **The desktop app copies Gaming Mode** in a bigger window. It has lists, not tables, and no sorting, charts or search. Whole features are missing, and the device-run step for "Desktop tray responsive" points at a Diagnostics page the desktop app does not have.
6. **The patterns are inconsistent.**
   - Errors show raw on most pages ("Python ValueError: ...").
   - Confirmations are a modal on some pages and a second press on others.
   - Similar lists use cards on one page and rows on another.

## 3. The proposed structure

### Principles

- **Seven sections in the full page**, grouped by what the player is doing. They are the same seven, in the same order, on the desktop.
- **v0.41.1: every sub-page is its own sidebar entry**, grouped by section with a line between sections, as in Steam's own settings. The list is fixed: a module that is off keeps its entries, which say so inside. (Until v0.41.1 sub-pages were a row of tabs inside each page; see the ADR-0073 addendum for why that changed.)
- **A module's settings live with the module**, in its own tab. Settings holds only what is everyone's: this device, cloud, modules, updates.
- **The same patterns everywhere:**
  - one confirmation pattern: a modal in Gaming Mode, a dialog on the desktop;
  - one plain-error helper;
  - bars for anything that moves;
  - rows (Field) for lists of things.

### Quick access menu: one screen, nothing deeper

1. **Now playing** (only while a game runs).
   - The game, its sync state and **Save checkpoint**.
   - The Advisor's top recommendation, one line.
   - Device controls, from R21: the performance profile, TDP, fan mode and charge limit, as one line or slider each.
2. **Moving games.** One line and a thin bar per game (v0.31.0).
3. **Needs attention.** At most three lines, most urgent first: conflicts, setup, problems, newer saves, safe mode, an update. Each opens the right section.
4. **Footer.** The status line (health, location, last sync), **Sync now** and **Open Keepsake**.

The first-run tips leave the quick access menu: they are on the first page shown after setup, and in What's new.

### Full page (Gaming Mode)

| Section | Tabs | From today |
|---|---|---|
| **Play** | Now playing, Advisor | Now playing is new: the running or last game, its sync state, Save checkpoint, the last session card and the Advisor's top recommendations. Advisor is today's Advisor page. |
| **Saves** | Games, Conflicts, History, Activity, Import and export | Games (with each game's detail page), Conflicts, History and Activity as they are. Import and export joins the Ludusavi import and the zip export (from Settings). |
| **Games and devices** | Moving games, Other devices, Disk use | Moving games holds the bars, updates waiting and low-level transfers. Other devices holds pairing, the listener, paired devices and Games on a device. Disk use is today's Storage. |
| **Device** | Status, then Power, Fans, Battery, Controllers, Display as R21's stages ship | Status is new: the model and profile Keepsake detected, battery and charging. |
| **Install** | Install (as today) | Today's Install page. Its library folder setting moves into it from Settings. |
| **Settings** | General, Cloud, Sync and safety, Modules, Updates | General: device name, device ID, safe mode, Setup. Cloud: today's Cloud section. Sync and safety: background sync, safety gates, the launch check timeout, toasts, Steam games, registry keys, Steam Cloud, sleep snapshots, other launchers, tidy copies. Modules: as today. Updates: today's Updates page and the pre-release switch. |
| **Diagnostics** | Health, Device checks, Tools, Logs | Health, the device checks and Logs as today. Tools holds the probes, the freeze test, the sign-in browser test and the diagnostics export. |

**Names.**
- "Devices" becomes **Other devices**, inside Games and devices, so **Device** is free for this handheld.
- "Storage" becomes **Disk use**.
- "Import saves" becomes **Import and export**.

**Old links still work.** `/games`, `/conflicts`, `/history`, `/import`, `/advisor`, `/devices`, `/install`, `/settings`, `/updates`, `/activity`, `/storage`, `/logs` and `/diagnostics` open the new section at the right tab.

### Desktop app

The same seven sections in the left navigation, with the tabs as sub-items. It is designed for a mouse, a keyboard and a bigger screen:

- **A search box** above the navigation finds any setting by name. Choosing a result opens its tab with that setting highlighted.
- **Overview:** health, moving games, conflicts, the last session's numbers and recent activity on one page.
- **Saves.**
  - Games is a table sorted by any column (name, kind, sync on, state, last sync) and filtered by text and by sync state, with bulk actions.
  - Conflicts compares the versions side by side before you choose (as today).
  - History is a table you can filter by game.
  - Activity and Import as today.
- **Games and devices.** A transfer dashboard you can sort, with a bar, GiB, speed, time left and Stop and remove per game. Other devices as today.
- **Play: Advisor.** Charts of the last 20 sessions: average and peak watts, CPU and GPU temperature, battery used, and frame rate where it was seen. The recommendations sit beside them.
- **Device (from R21):**
  - status;
  - a power-history chart;
  - a fan-curve editor with a draggable graph, with the device profile's safe minimum drawn on it and enforced;
  - battery and controller settings.
- **Settings:** the same tabs as Gaming Mode, plus the search.
- **Diagnostics:** Health, Device checks (Run all, Export results) and Logs.
- **Install:** Gaming Mode only for now. The desktop app links to it, because the Installer's steps (mounting, Steam's install run) are built around Gaming Mode. A desktop Install page is in the backlog.

## 4. What v0.32.0 builds, and what follows

**v0.32.0 (R20):**
- **Gaming Mode:**
  - the seven sections with tabs;
  - the renames;
  - the old links;
  - Now playing;
  - Device: Status;
  - settings regrouped;
  - the plain-error helper on every page.
- **The quick access menu:** reorganised as above.
- **The desktop app:**
  - grouped navigation;
  - the settings search;
  - the sortable, filterable games table;
  - the sortable transfer dashboard;
  - Advisor with session charts;
  - Diagnostics with Device checks and Logs.

**Later, in their own releases:**
- R21's Device tabs, with their quick access menu controls and desktop pages (the power chart and the fan-curve editor);
- a desktop Install page (backlog).
