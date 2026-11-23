# R30: the menu redesign (v0.57.0)

## What changed

- **Two levels** (ADR-0095).
  - **The sidebar:** the seven sections only, with Okabe-Ito coloured icons, built once from `LAYOUT`. Each section's entry lists its sub-pages, "Open <section>" first.
  - **Each section's own page:** Steam's native `Tabs`, in the pattern Decky's own store uses. L1 and R1 switch, and B goes back.
  - **Routes:** one exact route per sub-page.
  - **Memory:** the last sub-page per section is remembered while Haversack is loaded.
  - **Links:** quick menu links, toasts and old addresses land on the right sub-page.
- **The choice, with evidence.** Read in source: no well-built plugin nests `Tabs` in a `SidebarNavigation` page. Decky's store, TabMaster, CSS Loader and decky-steamgriddb either use flat sidebars or put `Tabs` on a full route. The one plugin that nests them needs remount keys, its own focus tracking and its own bumper handling.
- **The grouping review.** Device:
  - Status takes in More device settings;
  - Power and battery;
  - Controllers takes in Reconnect help;
  - Storage (was Disk use);
  - Looks.

  Settings: General takes in the quick menu's shortcuts. There are at most six sub-pages per section.
- **The desktop app:** the same sections and names, as collapsible groups. Merged pages show their parts together, and split pages show their own cards. The settings search is repointed.
- **The quick menu:** shortcut targets and links point at the new sub-pages.
- **Docs:**
  - every menu path in the user guide, the troubleshooting page, the device run and the in-app strings;
  - the Device guide page restructured;
  - the Help rebuilt;
  - ADR-0095, the ADR-0073 addendum and `docs/design/layout-v3.md`;
  - A248 and A249;
  - device run step 55, with the navigation recorder.
- **Fix: the desktop app was stuck on "Loading" from v0.52.0 to v0.56.0.**
  - The host serves only scripts matching `UI_SCRIPT`, which allowed lower case only, so `helpPage.js` (v0.52.0) and `looksPage.js` (v0.53.0) returned 404 and `main.js` failed to load.
  - Regenerating the screenshots showed it.
  - The pattern now allows mixed case and is still one path segment. `tests/test_host.py` serves a mixed-case file and checks every `desktop/src` module name against it; both tests fail without the fix.
- **Fix:** `GameArtSection` (v0.56.0) blanked on a failed check, against the v0.41.1 rule. The rule's test catches it, but it was not run for v0.56.0.

## Tests

- **`tests/frontend/sidebar.test.cjs`** (through `tests/test_frontend_sidebar.py`):
  - the sidebar has at most eight entries, is static and in order;
  - at most six sub-pages per section;
  - every sub-page is reachable at its own address;
  - the merged panels sit where the review put them;
  - moves resolve, and old addresses land on the right sub-page with no loops.
- **`tests/test_frontend_navigation.py`:**
  - the sidebar is built once;
  - Tabs appear only on a section's own route, built once, with no `autoFocusContents`, and never inside a sidebar entry;
  - there is no home-made tab row anywhere;
  - no page takes focus by itself, and nothing blanks on a failed reload;
  - the recorder keeps the new `section-open` and `tab` events.
- **`tests/test_shortcuts.py`:** every page shortcut opens a sub-page that exists, in seven sections.
- **Checks:** `tsc` for both frontends and eslint on the changed files pass. The gate result is in the pull request.

## Threat model

No change. The menu is navigation only, and no data, request or write changes. The desktop host's script pattern now allows capitals. It is still a single path segment of letters, digits, `_` and `-` ending in `.js`, inside `dist`, so nothing new can be reached (T52's rules are unchanged).

## Known gaps

- A248 and A249 are unverified until device run step 55 (B from a section's page, and B after a quick menu link).
- The guide's screenshots were regenerated with `scripts/docs_screenshots.py` (its per-page limit is now 300 seconds, for slow machines).
- **Lesson:** a screenshot run belongs in every release that changes the desktop app. It would have caught the "Loading" fault in v0.52.0.

## On-device checklist

Device run step 55.
