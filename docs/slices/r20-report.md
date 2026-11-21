# R20 report: layout v3 (v0.32.0)

Peter's item 2 of 21 November 2026: review the whole information architecture before the device controls, write it up, decide, and build the new structure in its own release with every feature still reachable. The review is `docs/design/layout-v3.md`, and the decisions are in ADR-0073.

## What changed

- **Gaming Mode, the full page.**
  - **Seven sections,** with lines between the groups: Play, Saves, Games and devices, Device, Install, Settings, Diagnostics.
  - **Tabs along the top of each section** (`Section.tsx`). The D-pad moves along them, and the chosen tab is remembered while Keepsake is open.
  - **Every old page is a tab.** Each old path (`/games`, `/devices`, `/updates` and the rest) opens the new section at the right tab, through hidden sidebar pages.
  - **Settings is split** into General, Cloud, Sync and safety, Modules and Updates. The pre-release switch moves to Updates. Diagnostics is split into Health, Device checks, Tools and Logs. Devices is split into Moving games and Other devices.
  - **Renamed:** Other devices, Disk use, Import and export. Import and export also holds the zip export.
  - **New tabs:**
    - **Now playing:** the game, its saves, Save checkpoint, the Advisor's top advice, the last session card and the first-run tip.
    - **Device, Status:** model and profile, power range, screen, battery and charging, from Core (`device_status`).
  - **Plain errors.** Every toast in `src/` now shows `plainError(err)`, the remaining part of v0.30.2's known gap.
- **The quick access menu fits on one screen:**
  - Now playing, with the game, Save checkpoint and the Advisor's top advice as one row;
  - Moving games;
  - at most three lines that need attention, each opening the right tab;
  - the status line, then Sync now and Open Keepsake.
- **The desktop app.**
  - **Layout:** the same seven groups in a left sidebar, with a settings search above them.
  - **Tables:** Games is a table you can sort by any column and filter by name and state, with each game's card under its row. The transfer table sorts too. Both keep their order while the page redraws (`table.ts`).
  - **New pages:**
    - **Advisor,** with SVG charts of the last 20 sessions (power, temperatures, frame rate, battery; `charts.ts`). The charts are coloured by CSS classes, because the page's security policy forbids inline styles.
    - **Device, Status.**
    - **Device checks.** The device-run step for "Desktop tray responsive" now has the Diagnostics page it names.
    - **Logs.**
- **User guide.**
  - `docs/user/` uses the new names. The guide's start page gains "Where things are".
  - The Replication guide covers 0.31.0: both ways, Get this game, the bars, and Stop and remove on either side.
  - The desktop screenshots are regenerated from the real interface with sample data (`scripts/docs_screenshots.py`).

## Not done, and why

- **The device controls** (Power, Fans, Battery, Controllers, Display tabs, their quick access menu rows, the power chart and the fan-curve editor) are R21, in stages.
- **A desktop Install page** stays in the backlog. The Installer's steps are built around Gaming Mode.
- **Steam's own `Tabs` component** is not used. Nesting it in a sidebar page is unverified (A220). The tab row is plain buttons, which behave like the rest of the page.
- **Frontend tests.** There is no frontend test runner. The layout is covered by the type check, lint, the build, the regenerated screenshots, and steps 19 to 21 of the device run.

## Tests

- **New:** `tests/test_layout_v3.py`, 2 tests. A known handheld on battery gives its profile, power range and battery, and no serial number is read. An unknown device gets safe generic limits, and a device with no battery is reported as having none.
- **Mutation tests:** 3 mutations, all caught: always generic, the battery flag, and reading a captured dump as this system.
- **Regression tests:** the frontend changes have no backend counterpart. `device_status` is new and touches no existing call.

The gate (`python scripts/check.py`) result is in the pull request.

## Threat model and assumptions

- **Threat model:** T139. Nothing new is exposed.
- **Assumptions:**
  - A219, verified from the types: `SidebarNavigation` takes separators and hidden pages.
  - A220, unverified, so avoided: Steam's `Tabs` inside a sidebar page.

## On-device checklist

In `docs/device-run.md`, part 4:

- **Step 19:** the new layout and the one-screen quick access menu.
- **Step 20:** Device, Status.
- **Step 21:** the desktop app (search, tables, Advisor charts, Device checks).
