"""A store backed by a local folder.

Used by tests and the two-device simulator, and usable on device with a
folder on an SD card or a network mount. Create-only writes use a hard link
from a fully written temp file, which fails atomically if the target exists.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

from ..safepath import ensure_within
from .base import AlreadyExistsError, NotFoundError, ObjectInfo, Store, validate_key, validate_prefix

_TMP_DIR = ".tmp"


class LocalFolderStore(Store):
    def __init__(self, root: str) -> None:
        os.makedirs(root, exist_ok=True)
        self._root = os.path.realpath(root)

    def _path(self, key: str) -> str:
        validate_key(key)
        return ensure_within(self._root, os.path.join(self._root, *key.split("/")))

    def put_new(self, key: str, data: bytes) -> ObjectInfo:
        target = self._path(key)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp_dir = os.path.join(self._root, _TMP_DIR)
        os.makedirs(tmp_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=tmp_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(tmp, target)
            except FileExistsError as exc:
                raise AlreadyExistsError(key) from exc
        finally:
            os.unlink(tmp)
        return ObjectInfo(key=key, size=len(data), sha256=hashlib.sha256(data).hexdigest())

    def get(self, key: str) -> bytes:
        try:
            with open(self._path(key), "rb") as handle:
                return handle.read()
        except FileNotFoundError as exc:
            raise NotFoundError(key) from exc

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        validate_prefix(prefix)
        out: list[ObjectInfo] = []
        for folder, dirs, files in os.walk(self._root):
            rel_folder = os.path.relpath(folder, self._root).replace(os.sep, "/")
            if rel_folder == ".":
                rel_folder = ""
                dirs[:] = [d for d in dirs if d != _TMP_DIR]
            for name in files:
                key = f"{rel_folder}/{name}" if rel_folder else name
                if key.startswith(prefix):
                    out.append(ObjectInfo(key=key, size=os.path.getsize(os.path.join(folder, name))))
        return sorted(out, key=lambda o: o.key)

    def delete(self, key: str) -> None:
        try:
            os.unlink(self._path(key))
        except FileNotFoundError as exc:
            raise NotFoundError(key) from exc
