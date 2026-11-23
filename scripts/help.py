"""Build the in-app Help from the user guide (R28, ADR-0090).

    python scripts/help.py           # write src/help.ts from docs/user
    python scripts/help.py --check   # fail if src/help.ts is not in step with docs/user (the gate runs this)

The topics are the guide's index (``docs/user/README.md``) in its order, starting with the index
itself. Each page is turned into plain blocks (headings, paragraphs, list items, code) that Gaming
Mode can show without a Markdown library:

- images are left out (the Help is read on the handheld itself);
- a link to another guide page becomes its text; a web link becomes "text (address)";
- ``**bold**`` stays marked, and the page shows it bold.

So the Help is the guide, word for word, and it cannot fall out of step with it: the gate refuses a
change to ``docs/user`` that is not built into ``src/help.ts`` and ``desktop/src/help.ts``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(ROOT, "docs", "user")
# The Gaming Mode page and the desktop app each get the same file (the desktop build sees only desktop/src).
TARGETS = (os.path.join(ROOT, "src", "help.ts"), os.path.join(ROOT, "desktop", "src", "help.ts"))

INDEX_LINK = re.compile(r"^\s*-\s+\[([^\]]+)\]\(((?:\.\./)?[a-z0-9-]+\.md)\)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HTML = re.compile(r"<[^>]+>")


def topics() -> list[tuple[str, str]]:
    """(file, title) for each page, in the index's order, the index first."""
    found = [("README.md", "About this guide")]
    with open(os.path.join(GUIDE, "README.md"), encoding="utf-8") as handle:
        for line in handle:
            match = INDEX_LINK.match(line)
            if match and match.group(2) not in {f for f, _ in found}:
                found.append((match.group(2), match.group(1)))  # ../troubleshooting.md is in docs/
    return found


def inline(text: str) -> str:
    """One line of Markdown as Help text: no images or HTML, links as text."""
    text = IMAGE.sub("", text)
    text = HTML.sub("", text)

    def link(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://")):
            shown = re.sub(r"^https?://", "", target).rstrip("/")
            return label if shown == label else f"{label} ({shown})"
        return label

    text = LINK.sub(link, text)
    text = re.sub(r"\s+", " ", text.replace("`", "")).strip()
    return re.sub(r" ([,.;:!?])", r"\1", text)  # no space left before punctuation where an image was


def blocks(markdown: str) -> list[dict[str, Any]]:
    """Headings, paragraphs, list items (with their depth) and code lines."""
    out: list[dict[str, Any]] = []
    paragraph: list[str] = []
    code = skip = False

    def flush() -> None:
        if paragraph:
            text = inline(" ".join(paragraph))
            if text:
                out.append({"k": "p", "t": text})
            paragraph.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            flush()
            if code or skip:
                code = skip = False
            elif line.strip() == "```mermaid":
                skip = True  # diagrams are left out, like images: the text around them says the same
            else:
                code = True
            continue
        if skip:
            continue
        if code:
            out.append({"k": "code", "t": line})
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        item = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if not line.strip() or IMAGE.fullmatch(line.strip()):
            flush()
        elif heading:
            flush()
            out.append({"k": "h", "l": len(heading.group(1)), "t": inline(heading.group(2))})
        elif item:
            flush()
            text = inline(item.group(3))
            if text and item.group(2)[0].isdigit():
                text = f"{item.group(2)} {text}"  # numbered steps keep their numbers
            if text:
                out.append({"k": "li", "d": min(len(item.group(1)) // 2, 3), "t": text})
        elif line.startswith("|"):
            flush()
            cells = [inline(c) for c in line.strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                out.append({"k": "row", "t": "  |  ".join(c for c in cells)})
        elif out and out[-1]["k"] == "li" and raw.startswith("  ") and not paragraph:
            out[-1]["t"] += " " + inline(line)  # a list item's continuation line
        else:
            paragraph.append(line)
    flush()
    return out


TYPES = """export type HelpBlock =
  | { k: "h"; l: number; t: string }
  | { k: "p"; t: string }
  | { k: "li"; d: number; t: string }
  | { k: "row"; t: string }
  | { k: "code"; t: string };

export interface HelpTopic {
  id: string;
  title: string;
  blocks: HelpBlock[];
}
"""


def build() -> str:
    data = []
    for name, title in topics():
        with open(os.path.join(GUIDE, name), encoding="utf-8") as handle:
            data.append({"id": os.path.basename(name)[:-3].lower(), "title": title, "blocks": blocks(handle.read())})
    body = json.dumps(data, ensure_ascii=False, indent=1)
    return (
        "// Built by scripts/help.py from docs/user: do not edit by hand (R28, ADR-0090).\n"
        "// Run `python scripts/help.py` after changing the user guide; the gate checks it is in step.\n"
        + TYPES
        + f"\nexport const HELP: HelpTopic[] = {body};\n"
    )


def main(argv: list[str]) -> int:
    text = build()
    stale = []
    for target in TARGETS:
        name = os.path.relpath(target, ROOT).replace(os.sep, "/")
        if "--check" in argv:
            try:
                with open(target, encoding="utf-8", newline="") as handle:
                    current = handle.read()
            except FileNotFoundError:
                current = ""
            if current != text:
                stale.append(name)
        else:
            with open(target, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            print(f"wrote {name} ({len(text)} characters)")
    if stale:
        print(f"{', '.join(stale)} not in step with docs/user: run python scripts/help.py")
        return 1
    if "--check" in argv:
        print("help: in step with the user guide")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
