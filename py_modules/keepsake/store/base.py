"""Backend-neutral object store contract.

Every cloud object is written once (principle 2). ``put_new`` must fail with
:class:`AlreadyExistsError` if the key exists, atomically, so two devices
racing for the same key cannot both succeed (threat model T13).

Keys are POSIX-style relative paths made of ``[A-Za-z0-9._-]`` segments, so
they map cleanly onto OneDrive, Google Drive, WebDAV, S3 and a local folder.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_KEY_LENGTH = 512


class StoreError(Exception):
    pass


class AlreadyExistsError(StoreError):
    pass


class NotFoundError(StoreError):
    pass


class StoreUnavailable(StoreError):
    """Network, sign-in or service trouble. Nothing was changed by the failed call."""


def validate_key(key: str) -> str:
    if not key or len(key) > MAX_KEY_LENGTH or key.startswith("/") or key.endswith("/"):
        raise StoreError(f"invalid store key: {key!r}")
    for segment in key.split("/"):
        if not _SEGMENT.match(segment) or segment in (".", ".."):
            raise StoreError(f"invalid store key segment in: {key!r}")
    return key


def validate_prefix(prefix: str) -> str:
    if prefix == "":
        return prefix
    validate_key(prefix.rstrip("/"))
    return prefix


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    sha256: str | None = None


class Store(ABC):
    """Abstract write-once object store."""

    @abstractmethod
    def put_new(self, key: str, data: bytes) -> ObjectInfo:
        """Create ``key``. Raises :class:`AlreadyExistsError` if it exists."""

    @abstractmethod
    def put_new_file(self, key: str, path: str) -> ObjectInfo:
        """Create ``key`` from a local file without loading it into memory."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Return the object's bytes. Raises :class:`NotFoundError`."""

    @abstractmethod
    def get_to_file(self, key: str, dest: str) -> ObjectInfo:
        """Download ``key`` to ``dest``; ``sha256`` is of the bytes received."""

    @abstractmethod
    def list(self, prefix: str = "") -> list[ObjectInfo]:
        """List objects under ``prefix``, sorted by key."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete ``key``. Only retention may call this (principle 2)."""
