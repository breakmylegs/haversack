"""ISOs on network shares: use them where they are, and copy them only when that fails (ADR-0067).

- ``network_filesystem`` says whether a path is on a network or FUSE file system, from
  ``/proc/self/mounts``. An ISO there is first opened in place; if udisks cannot set up a loop
  device on it (A158), the Installer copies it to staging and opens the copy (``copy_iso``).
- ``find_network_iso`` and ``loop_test`` back the Device check that replaced the SSH loop test.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable

from . import udisks

NETWORK_FS = ("cifs", "smb3", "smbfs", "nfs", "nfs4", "9p", "afs", "ceph", "sshfs", "davfs")
CHUNK = 4 * 1024 * 1024
SPACE_MARGIN = 2 * 1024**3
FIND_DEPTH = 4
FIND_ENTRIES = 5000


class CopyCancelled(Exception):
    pass


def _mounts(mounts_file: str) -> list[tuple[str, str]]:
    try:
        with open(mounts_file, encoding="utf-8", errors="replace") as handle:
            rows = [line.split() for line in handle]
    except OSError:
        return []
    return [(r[1].replace("\\040", " "), r[2]) for r in rows if len(r) >= 3]


def network_filesystem(path: str, mounts_file: str = "/proc/self/mounts") -> str | None:
    """The file system type when ``path`` is on a network share or a FUSE mount, else None."""
    real = os.path.realpath(path).replace(os.sep, "/")
    best: tuple[str, str] | None = None
    for point, fstype in _mounts(mounts_file):
        point = point.replace(os.sep, "/")
        inside = real == point or real.startswith(point.rstrip("/") + "/")
        if inside and (best is None or len(point) > len(best[0])):
            best = (point, fstype)
    if best is None:
        return None
    fstype = best[1]
    return fstype if fstype in NETWORK_FS or fstype.startswith("fuse") else None


def copy_iso(
    source: str,
    dest_dir: str,
    progress: Callable[[int, int], None] = lambda done, total: None,
    cancelled: Callable[[], bool] = lambda: False,
    free_space: Callable[[str], int] = lambda path: shutil.disk_usage(path).free,
) -> str:
    """Copy one ISO into staging; a partial copy is deleted on failure or cancel. Returns the copy's path."""
    name = os.path.basename(source)
    if not name.lower().endswith(".iso") or name.startswith("."):
        raise ValueError("choose an .iso file")
    total = os.path.getsize(source)
    os.makedirs(dest_dir, exist_ok=True)
    if free_space(dest_dir) < total + SPACE_MARGIN:
        raise ValueError(f"there is not enough free space to copy {name} first ({total // 1024**2} MiB needed)")
    final = os.path.join(dest_dir, name)
    part = final + ".part"
    done = 0
    try:
        with open(source, "rb") as src, open(part, "wb") as out:
            digest = hashlib.sha256()
            while chunk := src.read(CHUNK):
                if cancelled():
                    raise CopyCancelled("the copy was cancelled")
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                progress(done, total)
        if done != total:
            raise ValueError("the ISO changed while it was copied")
    except BaseException:
        try:
            os.unlink(part)
        except FileNotFoundError:
            pass
        raise
    os.replace(part, final)
    return final


def find_network_iso(mounts_file: str = "/proc/self/mounts") -> tuple[str, str] | None:
    """The first ISO on a mounted network share (for the Device check): ``(path, file system type)``."""
    for point, fstype in _mounts(mounts_file):
        if not (fstype in NETWORK_FS or fstype.startswith("fuse")) or fstype in ("fuse.portal", "fusectl"):
            continue
        seen = 0
        base_depth = point.rstrip("/").count("/")
        for top, dirs, files in os.walk(point):
            seen += len(dirs) + len(files)
            if seen > FIND_ENTRIES:
                break
            if top.rstrip("/").count("/") - base_depth >= FIND_DEPTH:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in sorted(files):
                if name.lower().endswith(".iso") and not name.startswith("."):
                    return os.path.join(top, name), fstype
    return None


def loop_test(iso: str, runner: udisks.Runner = udisks.run) -> str | None:
    """Set up a read-only loop device on ``iso`` and delete it again. Returns the error, or None if it worked."""
    try:
        attached = runner(["udisksctl", "loop-setup", "--read-only", "--no-user-interaction", "--file", iso])
    except udisks.UdisksError as exc:
        return str(exc)
    loop = udisks._LOOP.search(attached)
    if not loop:
        return "udisksctl did not report a loop device"
    udisks.detach(loop.group(1), runner)
    return None
