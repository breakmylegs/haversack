"""Central path validation used by every write (threat model T8).

Every path the plugin writes to must resolve, after ``realpath``, to a location
inside one of the allowed roots. Callers register roots once and pass every
target through :func:`ensure_within` before writing.
"""

from __future__ import annotations

import os
import posixpath


class PathEscapeError(ValueError):
    """Raised when a path would leave its allowed root."""


def _real(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))


def is_within(root: str, path: str) -> bool:
    """Return True if ``path`` resolves to ``root`` or somewhere beneath it."""
    real_root = _real(root)
    real_path = _real(path)
    try:
        common = os.path.commonpath([real_root, real_path])
    except ValueError:
        # Different drives on Windows.
        return False
    return os.path.normcase(common) == os.path.normcase(real_root)


def ensure_within(root: str, path: str) -> str:
    """Return the resolved ``path`` or raise :class:`PathEscapeError`.

    Symlinks are followed, so a link inside ``root`` that points outside it is
    rejected.
    """
    if not is_within(root, path):
        raise PathEscapeError(f"path escapes its root: {path!r}")
    return _real(path)


def validate_relative(rel: str) -> str:
    """Validate a relative POSIX path taken from untrusted data.

    Rejects empty paths, absolute paths, drive letters, backslashes, NUL bytes
    and any ``..`` or ``.`` segment. Returns the path unchanged when valid.
    """
    if not rel or "\x00" in rel or "\\" in rel:
        raise PathEscapeError(f"invalid relative path: {rel!r}")
    if rel.startswith("/") or posixpath.isabs(rel) or (len(rel) > 1 and rel[1] == ":"):
        raise PathEscapeError(f"absolute path not allowed: {rel!r}")
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            raise PathEscapeError(f"invalid path segment in: {rel!r}")
    return rel


def join_within(root: str, rel: str) -> str:
    """Join a validated relative path onto ``root`` and confirm it stays inside."""
    validate_relative(rel)
    return ensure_within(root, os.path.join(root, *rel.split("/")))
