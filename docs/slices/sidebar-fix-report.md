# Sidebar fix report (v0.39.1)

Peter's urgent report of 22 November 2026: on the full page, clicking **Saves** opened **Games and devices**, and the D-pad could then only move between **Settings** and **Diagnostics**.

## Causes found

Peter suspected the first two causes; both were confirmed, and the tests found a third.

1. **The page list changed after the first render.** `running` started as `{"saves"}`, and `modulesStatus()` then added the Install section and module tabs. `SidebarNavigation` tracks selection and focus by position, so entries shifted under the selection.
2. **The hidden legacy pages at the end** (`visible: false`) took positions in that list.
3. **A shared route.** `/keepsake/games` was both the old Games page (a hidden entry) and the new Games and devices section, so two sidebar entries claimed one route. A redirect for `/keepsake/install`, `/keepsake/settings` or `/keepsake/diagnostics` would also have looped, because those old addresses equal live section routes.

**Separators** are `SidebarNavigation`'s own supported entries. They are kept, but never first, last or doubled.

**Focus in `SectionPage`:** the tab row is a horizontal `Focusable` with no `onCancel`, so B goes back to the sidebar.

## The fix

- **`src/sidebar.ts`** builds the sidebar as plain data from the loaded module state, with no hidden entries. `sidebarKey` changes whenever the sections or tabs change, so a change rebuilds the sidebar and the selection follows the route.
- **`KeepsakeRoute`** shows "Loading" until the module state arrives, or for 3 seconds, after which it falls back to Saves and Core.
- **Games and devices moves** to `/keepsake/games-devices`.
- **Old routes are exact redirect routes** (`LegacyRedirect`), added before Keepsake's own route. An old address that is a live section's address gets no redirect.
- **`src/routeData.ts`** holds the route constants with no Steam imports, so the logic can be tested.

## Tests

- **New:** `tests/frontend/sidebar.test.cjs`, run through pytest by `tests/test_frontend_sidebar.py`. The script compiles `sidebar.ts` with `tsc` and runs Node's test runner, with no new dependency. It has 7 tests:
  - every entry maps to its own section before and after the module state changes;
  - tabs follow the modules;
  - no hidden or legacy pages are in the sidebar;
  - separators are never first, last or doubled;
  - each old route lands on the right section and tab, and none shares a live section's route;
  - a trailing separator is dropped;
  - a module that only adds tabs still rebuilds the sidebar.
- **Mutation tests:** 6 mutations. 2 survived, which led to the last two tests, and now all 6 are caught. One mutation reintroduces the `games` route clash, and the tests catch it.
- **The rest:** frontend type check, lint and the gate.

## Not verified

A224 (the order in which routes match) needs the device run, step 30.

## Threat model

No change. This is navigation only, with no new data, endpoint or write.
