# ADR-0095: The menu redesign: seven sections, and Steam's native tabs on each section's own page

- Status: accepted (Peter's request of 23 November 2026; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

The v0.41.1 fix (ADR-0073 addendum) made every sub-page its own sidebar entry. That stopped the jumping, but left about 26 entries in one flat list, with only lines between the seven sections. Peter asked for:

- **Top level:** at most seven or eight entries, each with a coloured icon, static as in v0.41.1.
- **Sub-pages:** inside each section, using `@decky/ui`'s native `Tabs` (Steam's own, switched with L1 and R1), never the home-made `Focusable` row of `DialogButton`s that caused the focus trouble.
- **The fallback:** if native `Tabs` inside a sidebar page proves unreliable, a two-level structure, chosen with evidence.
- **Behaviour:**
  - moving down the sidebar opens nothing by itself;
  - Right or A enters, L1 and R1 switch sub-pages, and B goes back;
  - the last sub-page is remembered;
  - links land directly;
  - every v0.41.1 focus rule is kept.
- **A grouping review,** at most about six sub-pages per section, with the quick menu and the desktop app following the same structure.

## Evidence

The sources were read on 23 November 2026, through `gh`. These are facts only; no code was taken.

- **decky-loader:**
  - `frontend/src/components/store/Store.tsx` renders `Tabs` as the whole route, not inside a sidebar: a wrapper with `marginTop: 40px`, `height: calc(100% - 40px)`, `activeTab` in state, and no `autoFocusContents`.
  - Its settings (`frontend/src/components/settings/index.tsx`) is a flat `SidebarNavigation`, one route per page, with no `Tabs`.
- **TabMaster** (`src/components/settings/SettingsRouter.tsx`), **CSS Loader** (`src/pages/settings/SettingsPageRouter.tsx`) and **decky-steamgriddb** (`src/components/plugin-pages/AssetTabs.tsx`) follow the same patterns. Either a flat `SidebarNavigation`, or `Tabs` as a full page. None puts `Tabs` inside a sidebar page.
- **GabeCubeAura** (`src/components/SimpleSettings.tsx`) is the only plugin found that nests `Tabs` in a `SidebarNavigation` page. It needs all of these:
  - a remounting `key`;
  - its own focus tracking between sidebar and content;
  - its own L1 and R1 handler, because "Tabs handles shoulders in its own header/content", so the bumpers do nothing while focus is in the sidebar;
  - props that are not in the typings (`wrapAround`, `cancelSkipTabHeader`, `disableRouteReporting`).
- **`autoFocusContents`** moves focus into the content when a tab shows. Inside a sidebar page, that would pull focus out of the sidebar: the v0.41.1 fault.
- **No public issue** was found either way.

## Decision

1. **Two levels, with native Tabs where they are proven.**
   - **The sidebar (`/keepsake`)** is a static `SidebarNavigation` with exactly seven entries:
     - Play, Saves, Games and devices, Device, Install, Settings and Diagnostics;
     - each with an Okabe-Ito coloured icon (ADR-0088).

     It is built once from `LAYOUT` alone. A section's entry shows a short list of its sub-pages, "Open <section>" first (the last sub-page used), then each sub-page with one line about it. The list takes no focus and loads nothing, so moving down the sidebar opens nothing. Right moves into the list, and A on an item opens it.
   - **A section's own page (`/keepsake/<section>/<sub-page>`)** is Steam's native `Tabs`, in the store's pattern: a full route, 40 px from the top, `activeTab` in state and no `autoFocusContents`. L1 and R1 switch sub-pages natively, the D-pad moves along the tab bar, and B goes back to the sidebar (the route's history).

     The tab list is built once per section. Every sub-page has its own exact route, with no route parameters to parse.

   This meets the request with Steam's own component, keeps the home-made row out, and avoids the nesting no well-built plugin uses. A home or overview entry is not added: Play's Now playing is that page.
2. **Remembered and direct.** The last sub-page of each section is kept while Haversack is loaded. Links from the quick menu, toasts and pages (`openSection`) navigate to the section's sidebar entry first, then to the sub-page, so B from a link also lands on the sidebar. Every old address still lands:
   - the v0.41.1 sub-page addresses that moved;
   - the pages from before v0.32.0.
3. **The grouping review** (at most six sub-pages per section):
   - **Play:** Now playing, Advisor.
   - **Saves:** Games, Conflicts, History, Activity, Import and export.
   - **Games and devices:** Moving games, Other devices, Emulators.
   - **Device:** Status (with More device settings), Power and battery, Fans, Controllers (with Reconnect help), Storage (was Disk use), Looks.
   - **Install:** Install.
   - **Settings:** General (with the quick menu's shortcuts), Cloud, Sync and safety, Modules, Updates, Help.
   - **Diagnostics:** Health, Device checks, Tools, Logs.

   The reasons:
   - **Reconnect help** is about controllers, so it sits with them, as in Peter's path "Device, Controllers, Reconnect help".
   - **Disk use** is about this device's storage, and its actions (clearing caches, resetting prefixes) are local.
   - **Power and Battery** are both power. **More device settings** was a page of two switches, now under Status.
   - **The quick menu's shortcuts** are a general preference.

   A merged sub-page shows its panels one after another. Each panel says when its module is off.
4. **The same everywhere.**
   - **The desktop app** uses the same sections and sub-page names, as collapsible groups in its left navigation, with the section of the current page open. A merged sub-page shows its parts together, and a split one shows only its own cards.
   - **The quick menu's** shortcut links point at the new sub-pages.
5. **The rules kept from v0.41.1:**
   - no page or tab takes focus by itself;
   - nothing focused is removed on a refresh;
   - the sidebar never changes while it is open;
   - a module that is off keeps its entries and says so inside.

   The navigation recorder also logs `section-open` and `tab`.

## Consequences

- **Device runs:** the device run (step 55) checks the bumpers, B, links straight after opening, and after a minute, with the recorder on.
- **The unverified points** are recorded as A248 and A249:
  - that B from a section's page returns to the sidebar;
  - that two navigations in a row leave the sidebar behind a link.
- **The fall-back:** if Steam's `Tabs` misbehaves on the device, the sub-pages can become each section's own short `SidebarNavigation` on the same routes, without changing the layout data.
- **ADR-0073 is amended,** and `docs/design/layout-v3.md` updated.
