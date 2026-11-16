"""Read-only ISO mounting through ``udisksctl`` (System Binary Register, ADR-0018).

``udisksctl`` sets up a loop device and mounts it as the user, under polkit, with
no root (assumption A85). Only fixed argument lists are used, never a shell, with
a timeout, and the ISO path is passed as one argument. A missing ``udisksctl``
disables ISO sources with a clear message; folder sources still work.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Sequence

TIMEOUT = 60
Runner = Callable[[Sequence[str]], str]
_LOOP = re.compile(r"\bas (/dev/loop\d+)\b")
_MOUNTED = re.compile(r"\bMounted (/dev/loop\d+) at (.+?)\.?\s*$")


class UdisksError(Exception):
    pass


def available() -> bool:
    return shutil.which("udisksctl") is not None


def run(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(list(command), capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UdisksError(f"udisksctl did not run: {exc}") from exc
    if result.returncode != 0:
        raise UdisksError((result.stderr or result.stdout).strip()[:300] or "udisksctl failed")
    return result.stdout


def mount_iso(iso: str, runner: Runner = run) -> tuple[str, str]:
    """Attach ``iso`` read-only and mount it. Returns ``(loop device, mount point)``."""
    attached = runner(["udisksctl", "loop-setup", "--read-only", "--no-user-interaction", "--file", iso])
    loop = _LOOP.search(attached)
    if not loop:
        raise UdisksError("udisksctl did not report a loop device")
    device = loop.group(1)
    try:
        mounted = runner(["udisksctl", "mount", "--no-user-interaction", "--block-device", device])
    except UdisksError:
        detach(device, runner)
        raise
    point = _MOUNTED.search(mounted.strip())
    if not point:
        detach(device, runner)
        raise UdisksError("udisksctl did not report a mount point")
    return device, point.group(2)


def detach(device: str, runner: Runner = run) -> None:
    """Unmount (if mounted) and delete the loop device. Errors are ignored: it may already be gone."""
    for command in (
        ["udisksctl", "unmount", "--no-user-interaction", "--block-device", device],
        ["udisksctl", "loop-delete", "--no-user-interaction", "--block-device", device],
    ):
        try:
            runner(command)
        except UdisksError:
            pass
