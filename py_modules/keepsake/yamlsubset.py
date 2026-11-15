"""Streaming parser for the block-YAML subset used by the Ludusavi manifest.

The primary manifest is machine-generated: block mappings and sequences with
space indentation, plain or double-quoted scalars and ``{}``/``[]`` for empty
collections. A survey of the live file (slice 4 report) found no block
scalars, anchors, aliases, tags or non-empty flow collections.

Anything outside that subset raises :class:`YamlSubsetError` for the
top-level entry it appears in. The caller skips that entry and carries on,
so an unexpected construct never produces a guessed value (fail closed).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

MAX_DEPTH = 32
_INT = re.compile(r"^-?(0|[1-9][0-9]*)$")
_UNSUPPORTED_START = ("[", "{", "&", "*", "!", "|", ">", "%", "@", "`")
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t", "r": "\r", "0": "\0", "b": "\b", "f": "\f"}


class YamlSubsetError(ValueError):
    pass


Line = tuple[int, str, int]  # indent, content, line number


def _double_quoted(text: str, start: int) -> tuple[str, int]:
    """Parse a double-quoted scalar starting at ``text[start] == '"'``. Returns (value, end index)."""
    out: list[str] = []
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == '"':
            return "".join(out), i + 1
        if ch == "\\":
            if i + 1 >= len(text):
                break
            nxt = text[i + 1]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
            elif nxt in "xuU":
                width = {"x": 2, "u": 4, "U": 8}[nxt]
                digits = text[i + 2 : i + 2 + width]
                if len(digits) != width or not all(c in "0123456789abcdefABCDEF" for c in digits):
                    raise YamlSubsetError("bad escape")
                out.append(chr(int(digits, 16)))
                i += 2 + width
            else:
                raise YamlSubsetError(f"unsupported escape \\{nxt}")
        else:
            out.append(ch)
            i += 1
    raise YamlSubsetError("unterminated double-quoted string")


def _single_quoted(text: str, start: int) -> tuple[str, int]:
    out: list[str] = []
    i = start + 1
    while i < len(text):
        if text[i] == "'":
            if text[i + 1 : i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(text[i])
        i += 1
    raise YamlSubsetError("unterminated single-quoted string")


def parse_scalar(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    if text[0] in "\"'":
        value, end = (_double_quoted if text[0] == '"' else _single_quoted)(text, 0)
        if text[end:].strip():
            raise YamlSubsetError("text after quoted scalar")
        return value
    if text == "{}":
        return {}
    if text == "[]":
        return []
    if text.startswith(_UNSUPPORTED_START) or " #" in text:
        raise YamlSubsetError(f"unsupported scalar: {text[:40]!r}")
    if text in ("~", "null", "Null", "NULL"):
        return None
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    if _INT.match(text):
        return int(text)
    return text


def split_key(content: str) -> tuple[str, str] | None:
    """Split ``key: rest``. Returns None if ``content`` is not a mapping entry."""
    if content[:1] in "\"'":
        try:
            key, end = (_double_quoted if content[0] == '"' else _single_quoted)(content, 0)
        except YamlSubsetError:
            return None
        rest = content[end:]
        if rest == ":" or rest.startswith(": "):
            return key, rest[1:].strip()
        return None
    if content.startswith(_UNSUPPORTED_START) or content.startswith(("- ", "#")) or content == "-":
        return None
    index = content.find(": ")
    if index > 0:
        return content[:index], content[index + 2 :].strip()
    if content.endswith(":") and len(content) > 1:
        return content[:-1], ""
    return None


def _is_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _parse_block(lines: list[Line], i: int, indent: int, depth: int) -> tuple[Any, int]:
    if depth > MAX_DEPTH:
        raise YamlSubsetError("nesting too deep")
    if _is_item(lines[i][1]):
        return _parse_sequence(lines, i, indent, depth)
    return _parse_mapping(lines, i, indent, depth)


def _child(lines: list[Line], i: int, indent: int, depth: int) -> tuple[Any, int]:
    """Value of a ``key:`` with nothing after the colon, starting at line ``i``."""
    if i < len(lines):
        next_indent, next_content, _ = lines[i]
        if next_indent > indent:
            return _parse_block(lines, i, next_indent, depth + 1)
        if next_indent == indent and _is_item(next_content):
            return _parse_sequence(lines, i, indent, depth + 1)
    return None, i


def _parse_mapping(lines: list[Line], i: int, indent: int, depth: int) -> tuple[dict[str, Any], int]:
    out: dict[str, Any] = {}
    while i < len(lines):
        line_indent, content, number = lines[i]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise YamlSubsetError(f"unexpected indentation at line {number}")
        if _is_item(content):
            break
        parts = split_key(content)
        if parts is None:
            raise YamlSubsetError(f"expected a key at line {number}")
        key, rest = parts
        i += 1
        if rest:
            out[key] = parse_scalar(rest)
        else:
            out[key], i = _child(lines, i, indent, depth)
    return out, i


def _parse_sequence(lines: list[Line], i: int, indent: int, depth: int) -> tuple[list[Any], int]:
    out: list[Any] = []
    while i < len(lines):
        line_indent, content, number = lines[i]
        if line_indent != indent or not _is_item(content):
            if line_indent > indent:
                raise YamlSubsetError(f"unexpected indentation at line {number}")
            break
        item = content[1:].lstrip(" ")
        item_indent = indent + (len(content) - len(item))
        if not item:
            i += 1
            value, i = _child(lines, i, indent, depth)
            out.append(value)
        elif split_key(item) is not None:
            # "- key: value" starts a mapping whose keys sit at the item's column.
            lines[i] = (item_indent, item, number)
            value, i = _parse_mapping(lines, i, item_indent, depth + 1)
            out.append(value)
        else:
            out.append(parse_scalar(item))
            i += 1
    return out, i


def _parse_entry(lines: list[Line]) -> tuple[str, Any]:
    _, content, number = lines[0]
    parts = split_key(content)
    if parts is None:
        raise YamlSubsetError(f"expected a top-level key at line {number}")
    key, rest = parts
    if rest:
        if len(lines) > 1:
            raise YamlSubsetError(f"value and block both given at line {number}")
        return key, parse_scalar(rest)
    if len(lines) == 1:
        return key, None
    value, end = _parse_block(lines, 1, lines[1][0], 1)
    if end != len(lines):
        raise YamlSubsetError(f"could not parse line {lines[end][2]}")
    return key, value


def iter_entries(source: Iterable[str]) -> Iterator[tuple[str, Any] | tuple[str, YamlSubsetError]]:
    """Yield ``(key, value)`` per top-level entry, or ``(key, error)`` when an entry is unsupported.

    Memory use is one entry at a time.
    """
    pending: list[Line] = []

    def flush() -> tuple[str, Any] | tuple[str, YamlSubsetError]:
        try:
            return _parse_entry(pending)
        except YamlSubsetError as exc:
            parts = split_key(pending[0][1])
            return (parts[0] if parts else f"<line {pending[0][2]}>"), exc
        except RecursionError:
            return f"<line {pending[0][2]}>", YamlSubsetError("nesting too deep")

    for number, raw in enumerate(source, start=1):
        line = raw.rstrip("\r\n")
        stripped = line.lstrip(" ")
        if not stripped or stripped.startswith("#") or (number == 1 and stripped == "---"):
            continue
        indent = len(line) - len(stripped)
        if stripped.startswith("\t") or "\t" in line[:indent]:
            if pending:
                pending.append((indent, "\x00tab", number))
            continue
        if indent == 0 and pending:
            yield flush()
            pending = []
        if indent == 0 and stripped in ("---", "..."):
            continue
        pending.append((indent, stripped.rstrip(" "), number))
    if pending:
        yield flush()
