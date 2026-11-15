"""Safety gates for new snapshots (build prompt section 9).

Defaults refuse a snapshot that:

* has zero files when the base had files,
* removes more than 50% of the base's files,
* shrinks the total size by more than 70% against the base.

Users may tighten the two percentage gates but never loosen them beyond the
defaults (loosening is an escalation item), and the hard floor stops either
being effectively disabled. The zero-files gate cannot be switched off.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .snapshot import FileEntry

DEFAULT_MAX_REMOVED_PERCENT = 50
DEFAULT_MAX_SIZE_DROP_PERCENT = 70
MIN_PERCENT = 5  # tightest allowed setting


def clamp_threshold(value: Any, default: int) -> int:
    """User threshold limited to [MIN_PERCENT, default]; anything invalid means the default."""
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return max(MIN_PERCENT, min(default, value))


def check(base: list[FileEntry] | None, new: list[FileEntry], settings: Mapping[str, Any] | None = None) -> list[str]:
    """Return the reasons a snapshot is refused (empty when it passes)."""
    if not base:
        return []
    settings = settings or {}
    max_removed = clamp_threshold(settings.get("gateMaxRemovedPercent"), DEFAULT_MAX_REMOVED_PERCENT)
    max_drop = clamp_threshold(settings.get("gateMaxSizeDropPercent"), DEFAULT_MAX_SIZE_DROP_PERCENT)
    reasons: list[str] = []
    if not new:
        reasons.append("no files left where the last snapshot had files")
        return reasons
    base_keys = {(e.root, e.rel) for e in base}
    new_keys = {(e.root, e.rel) for e in new}
    removed = len(base_keys - new_keys)
    if removed * 100 > max_removed * len(base_keys):
        reasons.append(f"removes {removed} of {len(base_keys)} files (limit {max_removed}%)")
    base_size = sum(e.size for e in base)
    new_size = sum(e.size for e in new)
    if base_size > 0 and (base_size - new_size) * 100 > max_drop * base_size:
        reasons.append(f"total size falls from {base_size} to {new_size} bytes (limit {max_drop}%)")
    return reasons
