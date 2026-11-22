# Quick menu shortcuts (R25, v0.46.0)

## What changed

- **The registry:** `py_modules/keepsake/shortcuts.py`, ported from the earlier work in progress.
  - Page targets are updated for the static sidebar.
  - New entries: Reconnect help, Fans, More device settings and the controller Reconnect status line.
  - The always-shown status line and Now playing are no longer offered as shortcuts.
- **The setting and calls:** `qamShortcuts` (None means the defaults), `qam_shortcuts`, `run_shortcut`, and the `keepsake_shortcuts` event when the setting changes.
- **The panel** (`src/index.tsx`) shows the chosen shortcuts in order, then Open Keepsake.
- **The editors:**
  - Gaming Mode, Settings, Quick menu (`src/pages/ShortcutsEditor.tsx`): tick boxes, Up and Down, nothing disabled while saving.
  - The desktop app's Quick menu page: drag to order.
- **Docs:** ADR-0073 addendum, the handheld guide, device run step 46, CHANGELOG and plan.

## Tests

- `tests/test_shortcuts.py`: 8 passed. It covers the registry, the defaults, every page target existing in the sidebar, hiding by module and feature, order and unknown IDs, the setting's checks, and the app's calls.
- Regressions: `tests/test_settings.py`, `tests/test_host.py`, `tests/test_frontend_sidebar.py`, `tests/test_frontend_navigation.py`, `tests/test_desktop_calls.py`. With the new tests, 43 passed and 1 skipped.
- Mutation tests: 6 mutations (module ignored, feature ignored, order lost, defaults ignored, the old section target, repeats kept), all caught.
- Threat model: no change. Shortcuts only call existing actions, each with its own checks.

## On-device checklist

Device run step 46.
