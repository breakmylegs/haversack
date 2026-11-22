# The full page's navigation, second fix (v0.41.1)

## What Peter saw

In v0.40.0 the sidebar still jumped about with the controller and with clicks, and the settings were hard to reach. v0.39.1 had not fixed it all.

## Causes, as confirmed in the code

| Suspected cause | Confirmed? | What the code did |
|---|---|---|
| 1. The sidebar is rebuilt after it appears | Yes | A 3 s fallback rendered "Saves only". The real module state arriving later changed `sidebarKey`, and `SidebarNavigation` remounted. |
| 2. Pages take focus on mount | Yes, one | `CloudSection` focused its buttons on a timer after a browser sign-in. `UninstallPanel` (`autoFocus`) and `ConflictModal` (`preferredFocus`) are modals and stay. No other focus calls were found. |
| 3. Focused elements removed on refresh | Yes | `NowPlaying`, `InStepPanel`, `SendPanel`, `TidyCopies` and `SnapshotsPanel` set their data to null when a reload failed. `GameDetail` and the library badge did the same on their single load, which was harmless but is changed for consistency. Panels that poll (`DeviceReadings`, `GameTransfers`, `ReplicationPage`) keep stable keys. |
| 4. The tab row inside each page | Replaced | A non-standard pattern: Steam's settings and Decky's own settings give every page its own sidebar entry. Every tab is now an entry. |
| 5. Redirects firing during sidebar moves | No | The routes are exact and mount only on their own address. Each section's old address is now also a redirect to its first page, and none can loop. |

## The fix

- A static sidebar:
  - `LAYOUT` in `src/routeData.ts`, and `sidebarEntries()` in `src/sidebar.ts`, which takes no input;
  - `PAGES` is built once in `KeepsakeRoute.tsx`, and `SidebarNavigation` has no key, state or timer;
  - a page whose module is off shows "This is off. Turn it on in Settings, Modules".
- No page takes focus by itself; the Cloud page's refocus is removed.
- A reload that fails keeps what is shown.
- The navigation recorder:
  - `src/navlog.ts`, `src/pages/NavigationRecorder.tsx` and `App.save_navigation_record`, filtered by `navigation_record`;
  - Diagnostics, Tools, "Record navigation for 60 seconds";
  - saved as `navigation-<time>.json` and included in the Device checks export.
- Docs:
  - ADR-0073 addendum;
  - A234;
  - device run step 39;
  - the layout doc and the user guide's entry names;
  - CHANGELOG.

## Tests

- `tests/frontend/sidebar.test.cjs` (through `tests/test_frontend_sidebar.py`) checks the sidebar:
  - it takes no input and is identical on every call;
  - every section and tab is present whatever its module;
  - titles and routes are unique;
  - separators are right;
  - old addresses go to a page, never to themselves or to another redirect.
- `tests/test_frontend_navigation.py`:
  - `KeepsakeRoute` builds the sidebar once (no state, timer or key);
  - no page uses `focus()`, `autoFocus` or `preferredFocus` outside a modal;
  - no `catch` blanks a panel;
  - the tab row is gone;
  - the recorder's record keeps only ids and counts.
- Mutation tests: 11 mutations, all caught:
  - the key put back, a timer put back;
  - a page calling `focus()`, `autoFocus` outside a modal, a reload blanking a panel;
  - the record keeping free text or unknown kinds;
  - the sidebar hiding a module or taking module input;
  - a looping section redirect, doubled separators.

## Known gaps

- Full render tests (mounting the panels and firing a reload) need `react-dom` as a development dependency. This urgent patch adds none. The rules are tested at source level instead.
- Route changes are recorded as page mounts, which is how `SidebarNavigation` shows them. Steam's router history is not read, as its API is unverified.

## On-device checklist

Device run step 39.
