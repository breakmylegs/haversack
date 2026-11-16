"""File lists before and after an install, and ranking of the executables it created (v2 spec 8.3).

Read-only. Lists skip symlinks and stop at a size cap, so a huge or looping tree
cannot stall the plugin. Ranking excludes uninstallers, redistributables, crash
reporters and setup stubs, then scores the rest by how well the name matches the
game's title, by size and by how close the file is to the install folder. The
user always confirms the choice.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any

MAX_ENTRIES = 200_000
EXCLUDE = re.compile(
    r"(unins|uninstall|setup|install|redist|vc_?redist|dxsetup|dxwebsetup|directx|dotnet|ndp\d|physx|crash|"
    r"report|bugsplat|ue[45]?prereq|prereq|easyanticheat|be_service|battleye|oalinst|update|patch|"
    r"config|touchup|cleanup|helper|activation|register|dxdiag)",
    re.IGNORECASE,
)
INSTALLER = re.compile(r"^(setup|install|autorun|installer)[^/\\]*\.exe$", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")


def file_list(root: str) -> dict[str, tuple[int, float]]:
    """``{relative path: (size, mtime)}`` for every regular file under ``root``, symlinks skipped."""
    out: dict[str, tuple[int, float]] = {}
    if not os.path.isdir(root):
        return out
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(folder, d))]
        for name in files:
            path = os.path.join(folder, name)
            if os.path.islink(path):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            out[os.path.relpath(path, root).replace(os.sep, "/")] = (stat.st_size, stat.st_mtime)
            if len(out) >= MAX_ENTRIES:
                return out
    return out


def new_files(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Files added or changed between two lists."""
    return sorted(path for path, info in after.items() if before.get(path) != info)


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 1}


def rank_game_exes(paths: list[tuple[str, int]], title: str) -> list[dict[str, Any]]:
    """Rank ``(absolute path, size)`` executables for the game called ``title``. Excluded files are dropped."""
    wanted = _words(title)
    ranked = []
    for path, size in paths:
        name = os.path.basename(path)
        if not name.lower().endswith(".exe") or EXCLUDE.search(name):
            continue
        stem = name[:-4]
        overlap = len(wanted & _words(stem)) / len(wanted) if wanted else 0.0
        depth = path.replace("\\", "/").count("/")
        score = overlap * 10 + math.log10(max(size, 1)) - depth * 0.2
        if "launcher" in stem.lower():
            score -= 2
        ranked.append({"path": path, "size": size, "score": round(score, 2)})
    return sorted(ranked, key=lambda r: (-r["score"], r["path"]))


def find_installers(source: str) -> list[str]:
    """Likely installer programs in a mounted disc or folder, most likely first (relative paths)."""
    found: list[tuple[int, str]] = []
    for path in file_list(source):
        if not path.lower().endswith(".exe") or path.count("/") > 2:
            continue
        name = os.path.basename(path)
        # Autorun is usually a disc menu that starts setup, so the real installer ranks above it.
        score = (10 if INSTALLER.match(name) else 0) + (5 if "/" not in path else 0) - path.count("/")
        score -= 1 if name.lower().startswith("autorun") else 0
        found.append((score, path))
    return [path for _score, path in sorted(found, key=lambda f: (-f[0], f[1]))]
