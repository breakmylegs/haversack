"""Checks the user documentation (ADR-0046). Part of ``scripts/check.py``; quick and offline.

- Every relative link and image in ``README.md`` and ``docs/user/*.md`` points at a file that exists.
- Every image in ``docs/user/images`` is used somewhere, so stale screenshots do not linger.
- Every Mermaid block starts with a diagram type GitHub renders.
- Screenshots carry no text chunks (PNG ``tEXt``, ``iTXt``, ``zTXt``), which could hold a path or a name.
- The screenshot sample data uses synthetic app IDs only (P12).
"""

from __future__ import annotations

import os
import re
import struct
import sys
from collections.abc import Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_DOCS = os.path.join(ROOT, "docs", "user")
IMAGES = os.path.join(USER_DOCS, "images")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)
DIAGRAMS = ("flowchart", "graph", "sequenceDiagram", "stateDiagram-v2", "stateDiagram", "classDiagram", "gantt", "pie")
TEXT_CHUNKS = {b"tEXt", b"iTXt", b"zTXt"}
# Synthetic app IDs: Steam ones from 1999999000, shortcuts from 2^31 (CLAUDE.md, P12).
APPID = re.compile(r"(?:steam|shortcut:\d+):(\d+)")


def doc_files(root: str = ROOT) -> list[str]:
    files = [os.path.join(root, "README.md")]
    user = os.path.join(root, "docs", "user")
    if os.path.isdir(user):
        files += sorted(os.path.join(user, n) for n in os.listdir(user) if n.endswith(".md"))
    return [f for f in files if os.path.isfile(f)]


def rel(path: str, root: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def link_problems(path: str, text: str, root: str = ROOT) -> list[str]:
    problems = []
    for target in LINK.findall(text):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue  # web links and anchors are not checked offline
        file_part = target.split("#", 1)[0]
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), file_part))
        if not os.path.exists(resolved):
            problems.append(f"{rel(path, root)}: missing {target}")
    return problems


def mermaid_problems(path: str, text: str, root: str = ROOT) -> list[str]:
    problems = []
    for block in MERMAID.findall(text.replace("\r\n", "\n")):
        first = block.strip().split(None, 1)[0] if block.strip() else ""
        if first not in DIAGRAMS:
            problems.append(f"{rel(path, root)}: unknown Mermaid diagram {first!r}")
    return problems


def png_text_chunks(data: bytes) -> list[str]:
    """The names of any text chunks in a PNG; an error for a file that is not a PNG."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ["not a PNG"]
    found, offset = [], 8
    while offset + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[offset : offset + 8])
        if kind in TEXT_CHUNKS:
            found.append(kind.decode())
        offset += 12 + length
    return found


def image_problems(docs: Iterable[tuple[str, str]], images_dir: str = IMAGES) -> list[str]:
    if not os.path.isdir(images_dir):
        return []
    used = {os.path.normpath(os.path.join(os.path.dirname(p), t)) for p, text in docs for t in LINK.findall(text)}
    problems = []
    for name in sorted(os.listdir(images_dir)):
        path = os.path.normpath(os.path.join(images_dir, name))
        if path not in used:
            problems.append(f"docs/user/images/{name}: not used by any page")
        if name.endswith(".png"):
            with open(path, "rb") as handle:
                chunks = png_text_chunks(handle.read())
            if chunks:
                problems.append(f"docs/user/images/{name}: {', '.join(chunks)}")
    return problems


def sample_problems(source: str) -> list[str]:
    problems = []
    for match in APPID.finditer(source):
        appid = int(match.group(1))
        steam_ok = match.group(0).startswith("steam:") and appid >= 1999999000
        shortcut_ok = match.group(0).startswith("shortcut:") and appid >= 2**31
        if not (steam_ok or shortcut_ok):
            problems.append(f"sample data: {match.group(0)} is not a synthetic app ID")
    return problems


def check(root: str = ROOT) -> list[str]:
    docs = []
    for path in doc_files(root):
        with open(path, encoding="utf-8") as handle:
            docs.append((path, handle.read()))
    problems: list[str] = []
    for path, text in docs:
        problems += link_problems(path, text, root) + mermaid_problems(path, text, root)
    problems += image_problems(docs, os.path.join(root, "docs", "user", "images"))
    sample = os.path.join(root, "scripts", "docs_screenshots.py")
    if os.path.isfile(sample):
        with open(sample, encoding="utf-8") as handle:
            problems += sample_problems(handle.read())
    return problems


def main() -> int:
    problems = check()
    for problem in problems:
        print(problem)
    print("docs: clean" if not problems else f"docs: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
