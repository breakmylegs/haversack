"""Status colours stay distinct for the common kinds of colour blindness (v0.50.0, R27).

The palette is Okabe-Ito, defined once in ``src/format.ts`` (``STATUS``) and in the desktop app's CSS
variables. No screen writes its own red or green any more: the old pair was a red and a green of
similar lightness, which deuteranopes and protanopes cannot tell apart."""

from __future__ import annotations

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OKABE_ITO = {"ok": "#009E73", "warn": "#E69F00", "fail": "#D55E00", "info": "#56B4E9"}
OLD = ("#59bf40", "#e5b33a", "#e04f4f", "#d9534f", "#3fae5b", "#e0a030", "#1f8a4c", "#c0392b")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_the_status_palette_is_okabe_ito() -> None:
    text = read(os.path.join(ROOT, "src", "format.ts"))
    for name, value in OKABE_ITO.items():
        assert re.search(rf'^\s*{name}: "{value}"', text, re.MULTILINE), name


def test_no_screen_keeps_the_old_red_and_green() -> None:
    files = glob.glob(os.path.join(ROOT, "src", "**", "*.ts*"), recursive=True)
    files += [os.path.join(ROOT, "desktop", "app.css"), *glob.glob(os.path.join(ROOT, "desktop", "src", "*.ts"))]
    found = [f"{os.path.relpath(f, ROOT)}: {c}" for f in files for c in OLD if c in read(f).lower()]
    assert found == []


def test_status_colours_come_from_one_place() -> None:
    """Pages use ``STATUS`` rather than writing a status colour of their own."""
    offenders = []
    for path in glob.glob(os.path.join(ROOT, "src", "pages", "*.tsx")):
        for value in OKABE_ITO.values():
            if value.lower() in read(path).lower():
                offenders.append(os.path.relpath(path, ROOT))
    assert offenders == []


def test_the_desktop_has_status_colours_in_both_modes() -> None:
    css = read(os.path.join(ROOT, "desktop", "app.css"))
    dark = css[css.index("prefers-color-scheme: dark") :]
    for name in ("--ok", "--warn", "--fail"):
        assert css.count(f"{name}:") == 2, name
        assert f"{name}:" in dark, name
