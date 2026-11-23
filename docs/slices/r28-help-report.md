# R28: README and in-app Help (v0.52.0)

## What changed

- **Settings, Help** in Gaming Mode (`src/pages/HelpPage.tsx`) and the desktop app (`desktop/src/helpPage.ts`). It shows the whole user guide: choose a topic, then move from section to section.
- **`scripts/help.py`** builds `src/help.ts` and an identical `desktop/src/help.ts` from `docs/user`:
  - in the index order, plus the troubleshooting page;
  - images and diagrams left out, links shown as text, bold kept, numbered steps keeping their numbers.
- **The gate** runs `scripts/help.py --check`, so a guide change that is not rebuilt into the Help fails it (ADR-0090).
- **The README** is rewritten for Haversack: the modules, the principles, install on a handheld and on PCs, the rename, and help.
- **The user guide is updated** for the new name and the current layout:
  - the sidebar sections and entries, including Emulators, the Device pages, Quick menu and Help;
  - Replication described as available, not "in development";
  - a "Keepsake is now Haversack" section in Updates;
  - notes on the folders and cloud folder that keep the old name.
- **THIRD_PARTY_NOTICES** credits the logo and icons as original artwork, with no third-party artwork, and cites the Okabe-Ito palette. This was R27's request.

## Tests

- **New:** `tests/test_help.py`, 5 tests.
  - Topic order and every block kind, from a synthetic guide.
  - Both copies written, a stale copy refused, and the repository's copy in step.
  - The gate step, and the page registered in the sidebar and the desktop app with no focus taken by itself.
- **Mutation testing:** 11 mutants of `scripts/help.py`, all killed, after two survivors led to stronger tests (an inline image, and the real target list).
- **Regression tests for the touched files:** `test_frontend_sidebar`, `test_frontend_navigation`, `test_desktop_calls` and `test_docs_checks` pass.
- **Checks:** `tsc` for both frontends and eslint on the changed files pass. The gate result is in the pull request.

## Threat model

No change. The Help is static text compiled into the bundle. It makes no requests and reaches the screen only as React text or DOM text nodes, never as markup.

## Known gaps

- Whether `Field` focus scrolls a long section into view is unverified (A245, device run step 51).

## On-device checklist

Device run step 51.
