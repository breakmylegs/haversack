"""Small filesystem helpers: atomic writes with restrictive modes."""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any

PRIVATE_FILE_MODE = 0o600


def atomic_write_bytes(path: str, data: bytes, mode: int = PRIVATE_FILE_MODE) -> None:
    """Write ``data`` to ``path`` atomically: temp file, fsync, rename.

    The temp file sits in the same folder so the rename never crosses a
    filesystem boundary.
    """
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        _replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    _fsync_dir(folder)


def _replace(src: str, dst: str) -> None:
    """``os.replace``, retried briefly on Windows where scanners can hold a file open.

    On Linux (the devices) this is a single atomic rename.
    """
    if os.name != "nt":
        os.replace(src, dst)
        return
    for attempt in range(10):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05)


def atomic_write_json(path: str, value: Any, mode: int = PRIVATE_FILE_MODE) -> None:
    data = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
    atomic_write_bytes(path, data, mode)


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))
    except FileNotFoundError:
        return default


def _fsync_dir(folder: str) -> None:
    if os.name != "posix":
        return
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
