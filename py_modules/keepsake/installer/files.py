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


NETWORK_FS = frozenset(
    {"cifs", "smb3", "nfs", "nfs4", "fuse.sshfs", "fuse.rclone", "fuse.gvfsd-fuse", "fuse.kio-fuse", "9p"}
)
REMOVABLE_FS = frozenset({"vfat", "exfat", "ntfs", "ntfs3", "fuseblk", "ext4", "btrfs", "f2fs", "iso9660", "udf"})


def _unescape(field: str) -> str:
    # /proc/mounts writes space, tab, newline and backslash as octal escapes.
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), field)


def mounted_sources(mounts_text: str, user_run_dirs: tuple[str, ...]) -> dict[str, list[str]]:
    """Network shares and removable drives the user has already mounted, from ``/proc/self/mounts``.

    Keepsake never mounts a share itself (that needs root or a binary; see the
    network mount spike). Network mounts count wherever they are; removable
    drives only under the user's ``/run/media/<user>`` or ``/media`` folders.
    """
    network: list[str] = []
    removable: list[str] = []
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        point, fstype = _unescape(parts[1]), parts[2]
        if fstype in NETWORK_FS or (fstype.startswith("fuse.") and "/gvfs" in point):
            network.append(point)
        elif fstype in REMOVABLE_FS and point.startswith(user_run_dirs):
            removable.append(point)
    return {"network": sorted(set(network)), "removable": sorted(set(removable))}


def compat_mounts(paths: list[str], home: str) -> str:
    """``STEAM_COMPAT_MOUNTS`` for paths outside the home folder, which the Steam runtime container hides.

    Refuses paths that would break the colon-separated, quoted launch option.
    """
    outside = []
    for path in paths:
        if path == home or path.startswith(home.rstrip("/") + "/") or path in outside:
            continue
        if any(c in path for c in ':"%\n'):
            raise ValueError('a folder name contains : " or %, which Steam launch options cannot carry')
        outside.append(path)
    return ":".join(outside)


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


# Installer III (ADR-0053): the other discs of a set, and runtime installers shipped with a game

RUNTIMES = (
    ("Visual C++ runtime", ("vcredist", "vc_redist")),
    ("DirectX", ("dxsetup",)),
    (".NET Framework", ("dotnetfx", "ndp4", "ndp3", "ndp2")),
    ("PhysX", ("physx",)),
    ("XNA Framework", ("xnafx",)),
    ("OpenAL", ("oalinst",)),
)


def sibling_discs(source: str) -> list[str]:
    """The other ``.iso`` files in the same folder as ``source``, in name order (disc 2, disc 3...)."""
    folder = os.path.dirname(source)
    try:
        names = sorted(os.listdir(folder), key=str.lower)
    except OSError:
        return []
    own = os.path.basename(source)
    return [n for n in names if n.lower().endswith(".iso") and n != own and os.path.isfile(os.path.join(folder, n))][
        :10
    ]


def find_runtimes(*listings: dict[str, tuple[int, float]]) -> list[dict[str, str]]:
    """Runtime installers a game ships (``_CommonRedist`` and the like): name and relative path, at most 20.

    Guidance only: Proton already provides most of these, so they are run only if the game will not start.
    """
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for listing in listings:
        for rel in sorted(listing):
            name = os.path.basename(rel).lower()
            if not name.endswith((".exe", ".msi")) or rel in seen:
                continue
            for label, needles in RUNTIMES:
                if any(name.startswith(n) or n in name for n in needles):
                    found.append({"runtime": label, "path": rel})
                    seen.add(rel)
                    break
            if len(found) >= 20:
                return found
    return found
