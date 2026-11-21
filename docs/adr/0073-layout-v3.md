# ADR-0073: Layout v3: seven sections, tabs, a one-screen quick access menu and a fuller desktop app

- Status: accepted (Peter's request of 21 November 2026, item 2, decided under ADR-0037)
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

Keepsake is becoming Peter's main Legion Go app, and the device controls (R21) are next. Peter asked for a review of the whole information architecture before they arrive, covering:

- the quick access menu;
- the full Gaming Mode page, with its sidebar, pages, sub-pages and settings;
- the desktop app.

The review is to be written up in `docs/design/layout-v3.md` and built in its own release, keeping every feature reachable.

That document records the structure today, its problems and the proposal. In short:

- the full page has 13 flat items, and the desktop app 12;
- settings are scattered;
- "Devices" is about to clash with "Device";
- the quick access menu is a scroll;
- the desktop app copies Gaming Mode and lacks whole features.

## Decision

1. **Seven sections in the full page,** with sidebar separators (`SidebarNavigation` takes `"separator"`; verified from `@decky/ui`'s types, A219):
   - Play;
   - Saves;
   - Games and devices;
   - Device;
   - Install;
   - Settings;
   - Diagnostics.

   A module's tabs, and a section left with none, show only while the module runs, as before (v2 spec 7.3).
2. **Sub-pages are tabs: a row of buttons at the top of the section** (`Section.tsx`).
   - **Why not Steam's `Tabs` component:** it is in `@decky/ui`, but nesting it inside a `SidebarNavigation` page is unverified (A220). Its full-height layout could break scrolling with the controller.
   - **The tab row:** plain `DialogButton`s in a `Focusable` row. The D-pad moves along them in the same way as the rest of the page.
   - **Which tab opens:** the chosen tab is remembered while Keepsake is open, and `openSection(section, tab)` opens any tab from anywhere.
3. **The tabs.**

   | Section | Tabs |
   |---|---|
   | Play | Now playing (new), Advisor |
   | Saves | Games, Conflicts, History, Activity, Import and export |
   | Games and devices | Moving games, Other devices, Disk use |
   | Device | Status (new). R21 adds Power, Fans, Battery, Controllers and Display. |
   | Install | Install |
   | Settings | General, Cloud, Sync and safety, Modules, Updates |
   | Diagnostics | Health, Device checks, Tools, Logs |
4. **Names.**
   - "Devices" becomes **Other devices**, so **Device** means this handheld.
   - "Storage" becomes **Disk use**.
   - "Import saves" becomes **Import and export**, which now also holds the zip export.
   - The pre-release switch moves next to Updates.
5. **Old links keep working.** Each old page path (`/games`, `/devices`, `/updates` and the rest) is a hidden sidebar page (`visible: false`) that opens the new section at the right tab.
6. **The quick access menu is one screen** (`index.tsx`), with nothing deeper:
   - **Now playing** (only while a game runs): the game and its sync state, **Save checkpoint**, and the Advisor's top advice as one row. The Advisor's separate section is gone.
   - **Moving games** (v0.31.0).
   - **At most three lines that need attention,** most urgent first: setup, conflicts, safe mode, problems, newer saves, then an update. Each opens the right tab.
   - **The status line,** then **Sync now** and **Open Keepsake**.

   The first-run tip moves to **Now playing**. The device controls (R21) will join Now playing as one row each.
7. **Device, Status** reads this handheld from Core only (`device_status`):
   - the profile Keepsake detected from the model strings, which never include a serial number;
   - the power range, the screen;
   - battery and charging.

   It writes nothing, and it uses no Advisor internals, so module isolation holds (P13).
8. **The desktop app has the same seven groups, in the same order,** in a left sidebar, with:
   - **a settings search:** each setting's name, with the page it is on; choosing one opens that page and highlights the setting;
   - **Games** as a table you can sort by any column and filter by name and by state, with the full card under a row on Details;
   - **a sortable transfer table,** with the order kept while the page redraws every second;
   - **Advisor,** with charts of the last 20 sessions: power, temperatures, frame rate and battery. The charts are drawn as SVG with no library, coloured by CSS classes, because the page's security policy forbids inline styles;
   - **Device, Status;**
   - **Diagnostics,** with Device checks (Run all, Export results) and Logs. This also gives the "Desktop tray responsive" device-run step the Diagnostics page it names.
9. **One error pattern.** Every Gaming Mode toast shows `plainError(err)` (from v0.30.2) instead of a raw "Python ValueError: ...".
10. **Not in this release:**
    - **The device controls,** with their quick access menu rows, power-history chart and draggable fan-curve editor. These come with R21's stages.
    - **A desktop Install page.** The Installer's steps are built around Gaming Mode, so it stays there for now (backlog).

## Consequences

- **Every existing feature stays reachable.** Each old page is a tab, and the old paths still open.
- **No new endpoint, scope, binary or write.** `device_status` only reads the model strings and battery that Advisor and Replication already read.
- **Threat model:** T139 records that nothing new is exposed. The layout moves controls without changing what they do, and `device_status` reads only the public model strings and battery state that Advisor and Replication already read.
- **Assumptions:** A219 and A220.
- **The user guide** (`docs/user/`) uses the new names, with the desktop screenshots regenerated from the real interface.
- **Device run:** part 4, steps 19 to 21.
