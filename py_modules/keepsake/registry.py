"""Wine registry files: key-level export, merge and value writes (build prompt slice 11, ADR-0022).

Wine keeps ``HKEY_CURRENT_USER`` in ``<pfx>/user.reg`` and ``HKEY_LOCAL_MACHINE``
in ``<pfx>/system.reg``, as text::

    WINE REGISTRY Version 2
    ;; All keys relative to \\\\User\\\\S-1-5-21-0-0-0-1000

    [Software\\\\Company\\\\Game] 1700000000
    #time=1d9c6e1f2a3b4c5
    "Name"="value"
    "Count"=dword:00000002

Keepsake syncs only the keys the manifest lists for a game, as a canonical
fragment (the same format, without timestamps) stored in the snapshot as
``registry/user.reg``. Merging replaces exactly those keys and nothing else.

Every write (:func:`apply_text`) is guarded against corruption: the current
file must parse; the new text must re-parse, keep every other key byte for
byte and contain exactly the intended managed keys; a copy of the original is
kept in Keepsake's runtime folder; the new file is written beside the old one,
flushed and atomically renamed over it, then read back. Any failure leaves the
original file in place. Callers only write while the game is not running.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass

HEADER = "WINE REGISTRY Version 2"
FRAGMENT_COMMENT = ";; Keepsake registry fragment"
_SECTION = re.compile(r"^\[(.*)\](?: (\d+))?$")
_VALUE_START = ('"', "@", "#")
MAX_REG_BYTES = 256 * 1024 * 1024
KEEP_BACKUPS = 5


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Section:
    raw_key: str  # as written in the file, backslashes escaped
    header: str  # the whole header line
    body: tuple[str, ...]  # following lines up to the next section, as written

    @property
    def key(self) -> str:
        return normalise_key(self.raw_key.replace("\\\\", "\\"))

    def canonical(self) -> tuple[str, ...]:
        """Header without timestamp and body without ``#time`` lines or trailing blanks."""
        body = [line for line in self.body if not line.startswith("#time=")]
        while body and not body[-1].strip():
            body.pop()
        return (f"[{self.raw_key}]", *body)


@dataclass(frozen=True)
class RegFile:
    preamble: tuple[str, ...]
    sections: tuple[Section, ...]


def normalise_key(key: str) -> str:
    """Case-insensitive, single-backslash key path (Windows keys ignore case)."""
    return "\\".join(part for part in key.replace("/", "\\").split("\\") if part).lower()


def _under(key: str, managed: Iterable[str]) -> bool:
    return any(key == m or key.startswith(m + "\\") for m in managed)


def parse(text: str) -> RegFile:
    lines = text.split("\n")
    if not lines or not lines[0].startswith(HEADER):
        raise RegistryError("not a Wine registry file")
    preamble: list[str] = []
    sections: list[Section] = []
    current: tuple[str, str] | None = None
    body: list[str] = []
    continuing = False
    for number, line in enumerate(lines, 1):
        line = line.rstrip("\r")
        match = _SECTION.match(line) if not continuing else None
        if match:
            if current:
                sections.append(Section(current[0], current[1], tuple(body)))
            current, body = (match.group(1), line), []
            continuing = False
            continue
        if current is None:
            preamble.append(line)
            continue
        stripped = line.strip()
        if continuing and not stripped:
            raise RegistryError(f"a value is cut off before line {number}")
        if stripped and not continuing and not line.startswith(_VALUE_START):
            raise RegistryError(f"unexpected line {number} in a registry key")
        # Only hex data runs onto following lines, each ending in a backslash.
        continuing = stripped.endswith("\\") and (continuing or "=hex" in line)
        body.append(line)
    if continuing:
        raise RegistryError("the registry file ends inside a value")
    if current:
        sections.append(Section(current[0], current[1], tuple(body)))
    keys = [s.key for s in sections]
    if len(keys) != len(set(keys)):
        raise RegistryError("the registry file has a key twice")
    return RegFile(tuple(preamble), tuple(sections))


def export(text: str, managed: Iterable[str]) -> str | None:
    """The canonical fragment holding only ``managed`` keys and their subkeys, or None if there are none."""
    managed = [normalise_key(m) for m in managed]
    chosen = [s for s in parse(text).sections if _under(s.key, managed)]
    if not chosen:
        return None
    lines = [HEADER, FRAGMENT_COMMENT, ""]
    for section in chosen:
        lines.extend(section.canonical())
        lines.append("")
    return "\n".join(lines) + "\n"


def merge(text: str, fragment: str | None, managed: Iterable[str], now: float) -> str:
    """Replace the managed keys in ``text`` with the fragment's (none if ``fragment`` is None)."""
    managed = [normalise_key(m) for m in managed]
    target = parse(text)
    incoming = parse(fragment).sections if fragment else ()
    for section in incoming:
        if not _under(section.key, managed):
            raise RegistryError(f"the fragment holds a key Haversack does not manage: {section.raw_key}")
    kept = [s for s in target.sections if not _under(s.key, managed)]
    lines = list(target.preamble)
    for section in kept:
        lines.append(section.header)
        lines.extend(section.body)
    if lines and lines[-1].strip():
        lines.append("")
    stamp = int(now)
    for section in incoming:
        canonical = section.canonical()
        lines.append(f"{canonical[0]} {stamp}")
        lines.extend(canonical[1:])
        lines.append("")
    merged = "\n".join(lines)
    return merged if merged.endswith("\n") else merged + "\n"


def _others(reg: RegFile, managed: list[str]) -> list[tuple[str, tuple[str, ...]]]:
    out = []
    for section in reg.sections:
        if not _under(section.key, managed):
            body = list(section.body)
            while body and not body[-1].strip():
                body.pop()
            out.append((section.header, tuple(body)))
    return out


def _read(path: str) -> str:
    if os.path.getsize(path) > MAX_REG_BYTES:
        raise RegistryError("the registry file is too large")
    with open(path, "rb") as handle:
        data = handle.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RegistryError("the registry file is not text Haversack can read") from exc


def _write_synced(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def apply_text(
    reg_path: str, new_text: str, original: str, backup_dir: str, now: float | None = None
) -> dict[str, str]:
    """Replace ``reg_path`` (whose current content must equal ``original``) with ``new_text``, safely.

    Keeps the original in ``backup_dir`` first, writes beside the target, flushes,
    renames atomically and reads back. On any failure the original stays in place.
    """
    stamp = int(now if now is not None else time.time())
    tmp = reg_path + ".keepsake-tmp"
    if os.path.exists(tmp):
        os.unlink(tmp)  # left by an earlier interrupted write; the real file was never touched
    if new_text == original:
        return {"status": "unchanged"}
    parse(new_text)
    if _read(reg_path) != original:
        raise RegistryError("the registry file changed while Haversack was merging; nothing was written")
    os.makedirs(backup_dir, exist_ok=True)
    backup = os.path.join(backup_dir, f"{stamp}-{os.path.basename(reg_path)}")
    _write_synced(backup, original)
    try:
        _write_synced(tmp, new_text)
        os.replace(tmp, reg_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if _read(reg_path) != new_text:
        _write_synced(tmp, original)
        os.replace(tmp, reg_path)
        raise RegistryError("the registry file did not read back correctly; the original was put back")
    _prune(backup_dir, os.path.basename(reg_path))
    return {"status": "written", "backup": backup}


def _prune(backup_dir: str, name: str) -> None:
    backups = sorted(f for f in os.listdir(backup_dir) if f.endswith("-" + name))
    for old in backups[:-KEEP_BACKUPS]:
        os.unlink(os.path.join(backup_dir, old))


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_values(
    reg_path: str, key: str, values: dict[str, str], backup_dir: str, now: float | None = None
) -> dict[str, str]:
    """Core service (v2 amendment for slice 11): set raw values in one key, e.g. a Wine drive type.

    ``values`` maps a value name to its raw ``.reg`` form, such as ``'"cdrom"'`` or
    ``'dword:00000001'``. The key is created if missing; other values and keys are untouched.
    """
    for name, raw in values.items():
        if "\n" in name or "\n" in raw or not raw:
            raise RegistryError("registry values must be single-line")
    original = _read(reg_path)
    reg = parse(original)
    wanted = normalise_key(key)
    stamp = int(now if now is not None else time.time())
    lines = list(reg.preamble)
    found = False
    for section in reg.sections:
        body = list(section.body)
        header = section.header
        if section.key == wanted:
            found = True
            header = f"[{section.raw_key}] {stamp}"
            for name, raw in values.items():
                prefix = _quote(name) + "="
                body = [line for line in body if not line.startswith(prefix)]
                insert_at = len(body)
                while insert_at and not body[insert_at - 1].strip():
                    insert_at -= 1
                body.insert(insert_at, prefix + raw)
        lines.append(header)
        lines.extend(body)
    if not found:
        if lines and lines[-1].strip():
            lines.append("")
        raw_key = "\\\\".join(p for p in key.replace("/", "\\").split("\\") if p)
        lines.append(f"[{raw_key}] {stamp}")
        lines.extend(_quote(name) + "=" + raw for name, raw in values.items())
        lines.append("")
    new_text = "\n".join(lines)
    new_text = new_text if new_text.endswith("\n") else new_text + "\n"
    after = parse(new_text)
    if _others(reg, [wanted]) != _others(after, [wanted]):
        raise RegistryError("setting values would change other keys")
    return apply_text(reg_path, new_text, original, backup_dir, now)
