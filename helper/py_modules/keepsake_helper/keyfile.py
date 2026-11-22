"""BlueZ's per-device ``info`` file: change only the pairing key and Trusted (ADR-0083).

``/var/lib/bluetooth/<ADAPTER>/<DEVICE>/info`` is a GLib key file. Cable pairing needs
``[LinkKey]`` Key, Type and PINLength, and ``[General]`` Trusted=true. Every other byte of the
file is kept as it was: lines are replaced in place, missing keys are added at the end of their
section, and a missing section is added at the end of the file.
"""

from __future__ import annotations

import re

_SECTION = re.compile(r"^\[(.+)\]\s*$")


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def set_values(text: str, section: str, values: dict[str, str]) -> str:
    """``text`` with ``values`` set in ``section``; every other line unchanged."""
    nl = _newline(text)
    lines = text.splitlines(keepends=True)
    start = end = None
    for i, line in enumerate(lines):
        found = _SECTION.match(line.rstrip("\r\n"))
        if found and start is not None and end is None:
            end = i
        if found and found.group(1) == section:
            start, end = i, None
    if start is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
        block = [f"{nl}" if lines and lines[-1].strip() else "", f"[{section}]{nl}"]
        block += [f"{k}={v}{nl}" for k, v in values.items()]
        return "".join(lines + [b for b in block if b])
    end = len(lines) if end is None else end
    remaining = dict(values)
    for i in range(start + 1, end):
        name = lines[i].split("=", 1)[0].strip()
        if "=" in lines[i] and name in remaining:
            ending = lines[i][len(lines[i].rstrip("\r\n")) :] or nl
            lines[i] = f"{name}={remaining.pop(name)}{ending}"
    if remaining:
        # After the section's last non-blank line, so a blank separator line stays where it was.
        at = end
        while at > start + 1 and not lines[at - 1].strip():
            at -= 1
        if not lines[at - 1].endswith(("\n", "\r")):
            lines[at - 1] += nl
        lines[at:at] = [f"{k}={v}{nl}" for k, v in remaining.items()]
    return "".join(lines)


def get_values(text: str, section: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        found = _SECTION.match(line)
        if found:
            current = found.group(1)
        elif current == section and "=" in line:
            name, value = line.split("=", 1)
            out[name.strip()] = value.strip()
    return out


def install_key(text: str, key: bytes, key_type: int) -> str:
    """The info file with this link key installed and the device trusted."""
    if len(key) != 16 or not 0 <= key_type <= 8:
        raise ValueError("a link key is 16 bytes with a type from 0 to 8")
    text = set_values(text, "General", {"Trusted": "true"})
    return set_values(text, "LinkKey", {"Key": key.hex().upper(), "Type": str(key_type), "PINLength": "0"})
