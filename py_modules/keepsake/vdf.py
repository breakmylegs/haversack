"""Read-only parsers for Valve's KeyValues formats.

* Binary VDF, used by ``shortcuts.vdf``.
* Text VDF, used by ``libraryfolders.vdf`` and ``appmanifest_*.acf``.

Keepsake never writes either format (editing ``shortcuts.vdf`` is an
escalation item), so there is deliberately no writer here.
"""

from __future__ import annotations

import struct
from typing import Any, Union

VdfValue = Union[str, int, float, "VdfMap"]
VdfMap = dict[str, Any]

# Binary type markers.
_MAP = 0x00
_STRING = 0x01
_INT32 = 0x02
_FLOAT32 = 0x03
_POINTER = 0x04
_WSTRING = 0x05
_COLOR = 0x06
_UINT64 = 0x07
_END = 0x08
_INT64 = 0x0A
_END_ALT = 0x0B

MAX_DEPTH = 32


class VdfError(ValueError):
    pass


# Binary format


def loads_binary(data: bytes) -> VdfMap:
    """Parse binary VDF. Raises :class:`VdfError` on malformed input."""
    result, pos = _read_map(data, 0, 0)
    # Steam sometimes writes extra end markers after the root; anything else is suspect.
    if data[pos:].strip(bytes([_END])):
        raise VdfError("unexpected data after root map")
    return result


def _read_cstring(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b"\x00", pos)
    if end < 0:
        raise VdfError("unterminated string")
    return data[pos:end].decode("utf-8", errors="replace"), end + 1


def _read_map(data: bytes, pos: int, depth: int) -> tuple[VdfMap, int]:
    if depth > MAX_DEPTH:
        raise VdfError("nesting too deep")
    out: VdfMap = {}
    while True:
        if pos >= len(data):
            if depth == 0:
                return out, pos
            raise VdfError("unexpected end of data")
        kind = data[pos]
        pos += 1
        if kind in (_END, _END_ALT):
            return out, pos
        key, pos = _read_cstring(data, pos)
        if kind == _MAP:
            value, pos = _read_map(data, pos, depth + 1)
            out[key] = value
        elif kind == _STRING:
            out[key], pos = _read_cstring(data, pos)
        elif kind in (_INT32, _POINTER, _COLOR):
            out[key], pos = _unpack("<i", data, pos)
        elif kind == _FLOAT32:
            out[key], pos = _unpack("<f", data, pos)
        elif kind == _UINT64:
            out[key], pos = _unpack("<Q", data, pos)
        elif kind == _INT64:
            out[key], pos = _unpack("<q", data, pos)
        elif kind == _WSTRING:
            end = pos
            while end + 1 < len(data) and data[end : end + 2] != b"\x00\x00":
                end += 2
            if end + 1 >= len(data):
                raise VdfError("unterminated wide string")
            out[key] = data[pos:end].decode("utf-16-le", errors="replace")
            pos = end + 2
        else:
            raise VdfError(f"unknown type byte 0x{kind:02x} at offset {pos - 1}")


def _unpack(fmt: str, data: bytes, pos: int) -> tuple[Any, int]:
    size = struct.calcsize(fmt)
    if pos + size > len(data):
        raise VdfError("unexpected end of data")
    return struct.unpack_from(fmt, data, pos)[0], pos + size


# Text format


def loads_text(text: str) -> VdfMap:
    """Parse text VDF. Duplicate keys keep the last value."""
    tokens = _tokenise(text)
    result, index = _parse_text_map(tokens, 0, 0, top=True)
    if index != len(tokens):
        raise VdfError("unexpected tokens after root")
    return result


def _tokenise(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n﻿":
            i += 1
        elif text.startswith("//", i):
            nl = text.find("\n", i)
            i = n if nl < 0 else nl + 1
        elif ch in "{}":
            tokens.append((ch, ch))
            i += 1
        elif ch == "[":
            # Platform conditional such as [$WIN32]; ignored.
            end = text.find("]", i)
            if end < 0:
                raise VdfError("unterminated conditional")
            i = end + 1
        elif ch == '"':
            i += 1
            buf: list[str] = []
            while True:
                if i >= n:
                    raise VdfError("unterminated quoted string")
                c = text[i]
                if c == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(nxt, "\\" + nxt))
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    buf.append(c)
                    i += 1
            tokens.append(("str", "".join(buf)))
        else:
            start = i
            while i < n and text[i] not in ' \t\r\n{}"':
                i += 1
            tokens.append(("str", text[start:i]))
    return tokens


def _parse_text_map(tokens: list[tuple[str, str]], index: int, depth: int, top: bool = False) -> tuple[VdfMap, int]:
    if depth > MAX_DEPTH:
        raise VdfError("nesting too deep")
    out: VdfMap = {}
    while index < len(tokens):
        kind, value = tokens[index]
        if kind == "}":
            if top:
                raise VdfError("unbalanced closing brace")
            return out, index + 1
        if kind != "str":
            raise VdfError("expected a key")
        key = value
        index += 1
        if index >= len(tokens):
            raise VdfError("key without value")
        kind, value = tokens[index]
        if kind == "{":
            child, index = _parse_text_map(tokens, index + 1, depth + 1)
            out[key] = child
        elif kind == "str":
            out[key] = value
            index += 1
        else:
            raise VdfError("unexpected closing brace after key")
    if not top:
        raise VdfError("missing closing brace")
    return out, index
