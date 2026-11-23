"""v0.41.1: source-level rules for the full page's navigation, and the navigation recorder's record.

- The sidebar is built once: no state, timer or key in KeepsakeRoute, and the pages are a constant.
- No page takes focus by itself: ``focus()``, ``autoFocus`` and ``preferredFocus`` only in modals.
- A reload that fails never blanks a panel: no ``catch`` that sets a panel's data back to null.
"""

from __future__ import annotations

import glob
import os
import re

from keepsake.app import navigation_record

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = sorted(glob.glob(os.path.join(ROOT, "src", "**", "*.tsx"), recursive=True))


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_keepsake_route_builds_the_sidebar_once() -> None:
    text = read(os.path.join(ROOT, "src", "pages", "KeepsakeRoute.tsx"))
    route = text[text.index("export function KeepsakeRoute") : text.index("export function SectionRoute")]
    assert "useState" not in route and "setTimeout" not in route and "modulesStatus" not in route
    assert re.search(r"<SidebarNavigation [^>]*pages=\{SIDEBAR\}", route)
    assert "key=" not in route
    assert re.search(r"^const SIDEBAR: .*= sidebarEntries\(\)", text, re.MULTILINE)


def test_sub_pages_are_steams_native_tabs_on_their_own_page() -> None:
    """The redesign (ADR-0095): Tabs only on a section's own route, built once, never told to take focus;
    the sidebar's entries are plain lists, and there is no home-made tab row anywhere."""
    text = read(os.path.join(ROOT, "src", "pages", "KeepsakeRoute.tsx"))
    section = text[text.index("export function SectionRoute") : text.index("export function LegacyRedirect")]
    assert re.search(r"<Tabs tabs=\{tabsRef\.current\}", section) and not re.search(r"autoFocusContents\s*[=:]", text)
    lists = text[text.index("function SectionList") : text.index("const SIDEBAR")]
    assert "<Tabs" not in lists and "Focusable" not in lists  # no Tabs inside a sidebar page
    for path in SOURCES:
        source = read(path)
        assert not re.search(
            r"flow-children=\"horizontal\"[\s\S]{0,400}DialogButton[\s\S]{0,200}openSection", source
        ), path
        assert "<Tabs" not in source or path.endswith("KeepsakeRoute.tsx"), path


def test_no_page_takes_focus_by_itself() -> None:
    offenders = []
    for path in SOURCES:
        text = read(path)
        is_modal = "ModalRoot" in text or "ConfirmModal" in text
        for pattern in (r"\.focus\(", r"\bautoFocus\b", r"\bpreferredFocus\b", r"focusOnMount"):
            if re.search(pattern, text) and not is_modal:
                offenders.append(f"{os.path.relpath(path, ROOT)}: {pattern}")
    assert offenders == []


def test_no_reload_blanks_a_panel() -> None:
    offenders = []
    for path in SOURCES:
        for number, line in enumerate(read(path).splitlines(), 1):
            if re.search(r"\.catch\(\(\) => set\w+\(null\)\)", line):
                offenders.append(f"{os.path.relpath(path, ROOT)}:{number}")
    assert offenders == []


def test_the_tab_row_is_gone() -> None:
    assert not os.path.exists(os.path.join(ROOT, "src", "pages", "Section.tsx"))
    for path in SOURCES:
        assert "SectionPage" not in read(path), path


def test_navigation_record_keeps_ids_and_counts_only() -> None:
    record = {
        "summary": {"pageMounts": 3, "focusCalls": 1, "note": "free text", "bad key!": 2},
        "events": [
            {"t": 10, "kind": "page-mount", "detail": {"page": "device/reconnect"}},
            {"t": 11, "kind": "focus", "detail": {"region": "sidebar", "prompted": True}},
            {"t": 12, "kind": "focus-call", "detail": {"element": "button@page:settings/cloud"}},
            {"t": 13, "kind": "keystroke", "detail": {"key": "a"}},
            {"t": 14, "kind": "page-mount", "detail": {"page": "Peter's Elden Ring save", "count": 2}},
            {"t": "x", "kind": "page-mount"},
        ],
    }
    clean = navigation_record(record)
    assert clean["summary"] == {"pageMounts": 3, "focusCalls": 1}
    assert [e["kind"] for e in clean["events"]] == ["page-mount", "focus", "focus-call", "page-mount"]
    assert clean["events"][3] == {"t": 14, "kind": "page-mount", "detail": {"count": 2}}
    assert navigation_record(None) == {"summary": {}, "events": []}


def test_the_recorder_keeps_the_redesigns_tab_events() -> None:
    record = {
        "events": [
            {"t": 1, "kind": "section-open", "detail": {"section": "device", "page": "controllers"}},
            {"t": 2, "kind": "tab", "detail": {"section": "device", "from": "controllers", "to": "fans"}},
        ]
    }
    assert [e["detail"] for e in navigation_record(record)["events"]] == [
        {"section": "device", "page": "controllers"},
        {"section": "device", "from": "controllers", "to": "fans"},
    ]
