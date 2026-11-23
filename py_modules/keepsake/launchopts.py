"""Launch option presets for a game (R29 stage 5, ADR-0097).

Proton reads its settings from environment variables set in front of ``%command%`` in a game's
launch options (Proton's README, "Runtime Config Options"). Haversack offers a few of them as
switches, all plain variables, so no program is added or needed (P9):

- ``PROTON_LOG=1``: write a Proton log (``steam-<appid>.log`` in the home folder);
- ``PROTON_USE_WINED3D=1``: OpenGL-based WineD3D instead of DXVK, for graphics problems;
- ``PROTON_NO_FSYNC=1`` and ``PROTON_NO_ESYNC=1``: for games that hang (esync only before Proton 11);
- ``PROTON_OLD_GL_STRING=1``: for old games that crash on a long OpenGL extension string.

The rest of the launch options are kept exactly: other variables, wrappers such as ``gamemoderun``,
and the game's own arguments after ``%command%``. A line without ``%command%`` is all arguments, so a
preset puts ``%command%`` in front of them, as Steam expects.

The first time a game's options are changed here, the line as it was is kept, so **Put back original**
restores it exactly. Steam itself is changed only through ``SteamClient`` after the user presses a
button, and the frontend reads the result back (P15).
"""

from __future__ import annotations

import json
import os
import re
import shlex
from typing import Any

from .fsutil import atomic_write_json

PRESETS: list[dict[str, str]] = [
    {
        "id": "log",
        "var": "PROTON_LOG",
        "label": "Write a Proton log",
        "about": "Saved as steam-<app>.log in your home folder, for troubleshooting.",
    },
    {
        "id": "wined3d",
        "var": "PROTON_USE_WINED3D",
        "label": "Use WineD3D instead of DXVK",
        "about": "For games with graphics problems. Usually slower.",
    },
    {"id": "nofsync", "var": "PROTON_NO_FSYNC", "label": "Turn off fsync", "about": "For games that hang or stutter."},
    {
        "id": "noesync",
        "var": "PROTON_NO_ESYNC",
        "label": "Turn off esync",
        "about": "For games that hang, on Proton versions before 11.",
    },
    {
        "id": "oldgl",
        "var": "PROTON_OLD_GL_STRING",
        "label": "Short OpenGL extension list",
        "about": "For old games that crash at start.",
    },
]
BY_ID = {p["id"]: p for p in PRESETS}
COMMAND = "%command%"
MAX_LENGTH = 1024
ASSIGN = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")
RECORD = "launch-presets.json"


class LaunchError(ValueError):
    pass


def parse(options: str) -> tuple[list[str], list[str]]:
    """The words before ``%command%`` and the words after it (all of them when it is missing)."""
    try:
        words = shlex.split(options)
    except ValueError as exc:
        raise LaunchError("these launch options have an unmatched quote, so Haversack leaves them alone") from exc
    if COMMAND not in words:
        return [], words
    at = words.index(COMMAND)
    return words[:at], words[at + 1 :]


def active(options: str) -> list[str]:
    """The presets switched on in ``options`` (variable set to 1 before ``%command%``)."""
    before, _after = parse(options)
    on = {m.group(1) for w in before if (m := ASSIGN.match(w)) and m.group(2) == "1"}
    return [p["id"] for p in PRESETS if p["var"] in on]


def compose(options: str, wanted: list[str]) -> str:
    """``options`` with exactly the ``wanted`` presets on, and everything else kept as it was."""
    unknown = [w for w in wanted if w not in BY_ID]
    if unknown:
        raise LaunchError("unknown preset")
    before, after = parse(options)
    ours = {p["var"] for p in PRESETS}
    kept = [w for w in before if not ((m := ASSIGN.match(w)) and m.group(1) in ours)]
    envs = [f"{BY_ID[w]['var']}=1" for w in [p["id"] for p in PRESETS] if w in wanted]
    prefix = envs + kept
    had_command = COMMAND in shlex.split(options) if options.strip() else False
    if not prefix and not had_command:
        words = after  # nothing in front: the line stays arguments only, as it was
    else:
        words = [*prefix, COMMAND, *after]
    result = shlex.join(words).replace(shlex.quote(COMMAND), COMMAND)
    if len(result) > MAX_LENGTH:
        raise LaunchError("the launch options would be too long")
    return result


class Originals:
    """The launch options of each game before Haversack first changed them."""

    def __init__(self, runtime_dir: str) -> None:
        self.path = os.path.join(runtime_dir, RECORD)

    def _load(self) -> dict[str, str]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                found = json.load(handle)
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in found.items()} if isinstance(found, dict) else {}

    def keep(self, appid: int, options: str) -> None:
        """Record ``options`` as the original, unless one is already recorded (the first one wins)."""
        record = self._load()
        if str(appid) not in record:
            record[str(appid)] = options
            atomic_write_json(self.path, record)

    def get(self, appid: int) -> str | None:
        return self._load().get(str(appid))

    def forget(self, appid: int) -> None:
        record = self._load()
        if record.pop(str(appid), None) is not None:
            atomic_write_json(self.path, record)


def status(options: str, original: str | None) -> dict[str, Any]:
    try:
        on = active(options)
        problem = None
    except LaunchError as exc:
        on, problem = [], str(exc)
    return {
        "presets": [{**p, "on": p["id"] in on} for p in PRESETS],
        "options": options,
        "original": original,
        "problem": problem,
    }
