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

## Addendum (v0.39.1): the sidebar fix

Three faults made the sidebar unpredictable on the device:
- it was drawn from a guess (Saves only) and then grew when the real module state arrived;
- the old pages were hidden sidebar entries at the end of the list;
- `/keepsake/games` was both the old Games page and the new Games and devices section.

`SidebarNavigation` tracks selection and focus by position, so each fault moved clicks and the D-pad onto the wrong entry.

The sidebar is now built once, from the loaded module state (`src/sidebar.ts`, tested with Node). It is keyed so that a module change rebuilds it, and it has no hidden entries. Games and devices lives at `/keepsake/games-devices`. Old links are exact redirect routes, added before the page's route. An old address that is also a live section's address (install, settings, diagnostics) gets no redirect, because one would loop.

## Addendum (v0.41.1): a static sidebar, one entry per tab

**What was still wrong.** After v0.39.1 the sidebar still jumped on the device. Five causes were confirmed in the code:
1. **A late rebuild.** `KeepsakeRoute` fell back to "Saves only" after 3 seconds. When `modulesStatus()` answered later, the sidebar key changed, and `SidebarNavigation` remounted, losing the selection and focus. On a busy handheld the backend often takes longer than 3 seconds.
2. **A tab row inside each page.** Each sidebar page held its own row of tabs (`Focusable flow-children="horizontal"`), a pattern that neither Steam's settings nor Decky's own settings use: both give every page its own sidebar entry.
3. **A page that took focus.** `CloudSection` called `focus()` on a timer after a browser sign-in (ADR-0044). `SidebarNavigation` in route mode opens each page as the focus moves down the list, so a page taking focus pulls the player out of the sidebar. The other focus uses, `autoFocus` in the uninstall dialog and `preferredFocus` in the conflict dialog, are inside modals and stay.
4. **Panels that blanked on a failed reload.** `NowPlaying`, `InStepPanel`, `SendPanel`, `TidyCopies` and `SnapshotsPanel` set their data back to null when a background reload failed, which unmounted the element that had focus.
5. **Redirects.** These were checked and found sound: a redirect route is exact, and mounts only when that address is opened. With pages now under `/keepsake/<section>/<tab>`, each section's old address joins the redirects, and each goes to a different address, so none can loop.

**The fix:**
- **A static sidebar.** `src/routeData.ts` `LAYOUT` lists every section and tab. `src/sidebar.ts` `sidebarEntries()` takes no input and builds one entry per tab, with a line between sections. `KeepsakeRoute` builds `PAGES` once, when the plugin loads, and renders `SidebarNavigation` with no key, no state and no timer.
- **Modules that are off.** A page whose module is off keeps its entry and shows "This is off. Turn it on in Settings, Modules" (or "not available here"). The v2 rule that a disabled module has no UI still holds for its content; only its place in the list stays.
- **Focus.** No page or tab takes focus by itself. `focus()`, `autoFocus` and `preferredFocus` are allowed only in modals, and a source-level test enforces it.
- **Reloads.** A reload that fails keeps what is shown, and a source-level test forbids `catch` resets to null.
- **Routes.** Each sidebar page is `/keepsake/<section>/<tab>`, and `openSection(section, tab)` opens it.
- **The navigation recorder.** `src/navlog.ts` and Diagnostics, Tools, "Record navigation for 60 seconds" log:
  - route and page mounts;
  - redirects and navigations;
  - focus moves, with prompted or unprompted;
  - focus calls.

  The log holds page ids and counts only. The backend filters it (`app.navigation_record`), saves it as `navigation-<time>.json` and adds it to the Device checks export.

**Not done.** Full render tests need `react-dom` as a development dependency. This urgent patch adds none. The rules are tested at source level and in the sidebar's pure logic instead.

## Addendum (v0.46.0): quick menu shortcuts

Peter asked for Keepsake's quick access menu panel to be configurable.

**The registry.** `keepsake/shortcuts.py` lists every shortcut: an ID, a kind (page, action or status line), a label, its module and, where needed, a feature.
- **Every new feature registers its pages and actions there.** This release adds Reconnect help, Fans and More device settings, and the controller Reconnect status line.
- **What is offered:** only entries whose module is on (Core always is) and whose feature this device has (updates, performance modes, the charge limit).

**The setting.** `qamShortcuts` holds the user's choice in order. `None` means the defaults:
- Sync now;
- games moving between devices;
- open conflicts;
- the controller Reconnect buttons, kept because helped controllers have had them in the menu since v0.40.0.

Unknown IDs are kept in the setting, so a later version's shortcuts survive a downgrade; they are only shown when they exist.

**The panel.** Some parts are always shown and are not shortcuts: Now playing, the battery line, the attention items and the status line. The chosen shortcuts follow them, then Open Keepsake, always last. The panel reloads on `keepsake_shortcuts`, which Keepsake sends when the setting changes, so changes show at once.

**The editors.**
- **Gaming Mode:** Settings, Quick menu has tick boxes with Up and Down. Nothing in it is disabled while saving (the v0.41.1 focus rule).
- **Desktop app:** Settings, Quick menu orders by dragging, with arrows as well.

## Consequences

- **Every existing feature stays reachable.** Each old page is a tab, and the old paths still open.
- **No new endpoint, scope, binary or write.** `device_status` only reads the model strings and battery that Advisor and Replication already read.
- **Threat model:** T139 records that nothing new is exposed. The layout moves controls without changing what they do, and `device_status` reads only the public model strings and battery state that Advisor and Replication already read.
- **Assumptions:** A219 and A220.
- **The user guide** (`docs/user/`) uses the new names, with the desktop screenshots regenerated from the real interface.
- **Device run:** part 4, steps 19 to 21.

## Addendum (v0.57.0): the menu redesign

Peter asked for fewer top-level entries with the sub-pages inside each section, on Steam's native tabs. ADR-0095 records the decision and its evidence. In short:
- **The sidebar** is the seven sections only, static, each with a coloured icon.
- **Each section's own page** holds its sub-pages as Steam's `Tabs`, in the pattern Decky's own store uses, so L1 and R1 switch them and B goes back to the sidebar.
- **No nesting:** `Tabs` is never placed inside a sidebar page, because no well-built plugin does that without heavy workarounds.
- **The grouping review:**
  - Reconnect help joins Controllers;
  - Battery joins Power;
  - More device settings joins Status;
  - Disk use becomes Device, Storage;
  - the quick menu's shortcuts join Settings, General.
- **The v0.41.1 rules stand,** and a source-level test keeps the home-made tab row out.
