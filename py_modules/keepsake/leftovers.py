"""Tidying what earlier, larger versions left on the device (the strip, ADR-0098).

Up to v0.60.0, Haversack wrote two Desktop Mode entries for its tray and desktop app. Both are gone
now, so the entries would point at a program that no longer exists. They are removed, but only when
they carry Haversack's own ``X-Keepsake-Version`` line, so a file the user made is never touched.
Everything else earlier versions kept (cloud snapshots, settings, tokens) is left as it was: nothing
of the user's is deleted, and installing v0.60.0 again finds it.
"""

from __future__ import annotations

import os

ENTRIES = ((".config", "autostart", "keepsake-tray.desktop"), (".local", "share", "applications", "keepsake.desktop"))
MARKER = "X-Keepsake-Version="


def remove_desktop_entries(home: str) -> list[str]:
    """Remove the old tray and app-menu entries that Haversack wrote. Returns what was removed."""
    removed = []
    for parts in ENTRIES:
        path = os.path.join(home, *parts)
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as handle:
                ours = any(line.startswith(MARKER) for line in handle)
            if ours:
                os.remove(path)
                removed.append(path)
        except OSError:
            continue
    return removed
