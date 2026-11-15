"""Game lifecycle: launch gate, exit push, strict wrapper and played-without-Keepsake (build prompt section 10).

Freeze mode (default):

1. Poll every 100 ms for up to 5 s for the game's processes.
2. Freeze them (``SIGSTOP``); the PIDs are persisted first and a 30 second
   watchdog releases them whatever happens (principle 11).
3. Run the pull, with a timeout (default 20 s). The game is frozen, so a
   restore is allowed (principle 6).
4. Release every frozen process in ``finally``.

If the processes cannot be found in time, nothing is frozen and the pull runs
with the game treated as running: a newer cloud save is not restored, the game
is marked pending and the player is told to quit to load it.

If the pull times out, the game is released, marked pending, and the late
pull can no longer restore: its view of the game switches to "running".

Strict mode (opt-in per game): the launch options start ``keepsake-gate``,
which writes a request with a one-off token and waits for a matching ready
file before starting the game.
"""

from __future__ import annotations

import os
import posixpath
import re
import secrets
import shlex
import threading
import time
from collections.abc import Callable
from typing import Any

from .fsutil import atomic_write_json, read_json

POLL_INTERVAL = 0.1
FIND_PROCESS_SECONDS = 5.0
EXIT_WAIT_SECONDS = 30.0
DEFAULT_PULL_TIMEOUT = 20
PULL_TIMEOUT_RANGE = (5, 60)
GATE_DIR = "gate"
GATE_SCRIPT = os.path.join("bin", "keepsake-gate")
LAUNCH_OPTIONS_FILE = "launch-options.json"
PLAYED_WITHOUT_SLACK_SECONDS = 120

TOAST_TIMEOUT = "Cloud check timed out. Playing the local save."
TOAST_CLOUD_NEWER = "Cloud has a newer save. Quit the game to load it."


def normalise_appid(value: Any) -> int:
    """Accept a signed or unsigned 32-bit app ID, or a 64-bit shortcut game ID; return the unsigned app ID."""
    number = int(value)
    if number >= 2**32:
        number >>= 32  # 64-bit game ID: (appid << 32) | 0x02000000
    return number & 0xFFFFFFFF


def wait_for(
    predicate: Callable[[], bool],
    timeout: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    interval: float = POLL_INTERVAL,
) -> bool:
    deadline = clock() + timeout
    while True:
        if predicate():
            return True
        if clock() >= deadline:
            return False
        sleep(interval)


class Abort:
    """Set when a launch pull is abandoned (timeout); the late pull then treats the game as running."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


# Strict wrapper: launch options


def gate_command(plugin_dir: str) -> str:
    # A path on the device: always POSIX separators, whatever system builds the string.
    return shlex.quote(posixpath.join(plugin_dir.replace("\\", "/"), "bin", "keepsake-gate"))


def wrap_launch_options(original: str, plugin_dir: str) -> str:
    """Put the gate in front of the game command, keeping the user's options intact.

    * no options: ``<gate> %command%``
    * options with ``%command%``: the first ``%command%`` becomes ``<gate> %command%``
    * options without it (Steam appends them to the command): ``<gate> %command% <options>``
    """
    gate = gate_command(plugin_dir)
    if gate in original:
        return original  # already wrapped
    if not original.strip():
        return f"{gate} %command%"
    if "%command%" in original:
        return original.replace("%command%", f"{gate} %command%", 1)
    return f"{gate} %command% {original}"


class LaunchOptionsStore:
    """Originals saved before any change, so turning strict mode off restores them exactly."""

    def __init__(self, runtime_dir: str) -> None:
        self._path = os.path.join(runtime_dir, LAUNCH_OPTIONS_FILE)

    def _all(self) -> dict[str, str]:
        data = read_json(self._path, default={})
        return data if isinstance(data, dict) else {}

    def save_original(self, appid: int, original: str) -> None:
        data = self._all()
        data.setdefault(str(appid), original)  # never overwrite an already saved original
        atomic_write_json(self._path, data)

    def original(self, appid: int) -> str | None:
        value = self._all().get(str(appid))
        return value if isinstance(value, str) else None

    def forget(self, appid: int) -> None:
        data = self._all()
        data.pop(str(appid), None)
        atomic_write_json(self._path, data)


# Strict wrapper: handshake files

_TOKEN = re.compile(r"^[0-9a-f]{8,64}$")


class GateFiles:
    def __init__(self, runtime_dir: str) -> None:
        self.dir = os.path.join(runtime_dir, GATE_DIR)

    def waiting_token(self, appid: int) -> str | None:
        try:
            with open(os.path.join(self.dir, f"{appid}.waiting"), encoding="ascii") as handle:
                token = handle.read().strip()
        except (OSError, UnicodeDecodeError):
            return None
        return token if _TOKEN.match(token) else None

    def release(self, appid: int, token: str) -> None:
        os.makedirs(self.dir, exist_ok=True)
        path = os.path.join(self.dir, f"{appid}.ready")
        tmp = path + "." + secrets.token_hex(4)
        with open(tmp, "w", encoding="ascii") as handle:
            handle.write(token)
        os.replace(tmp, path)

    def write_timeout(self, seconds: int) -> None:
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, "timeout"), "w", encoding="ascii") as handle:
            handle.write(str(int(seconds)))


# Played without Keepsake


def played_without_keepsake(last_played: int, last_session_start: float | None) -> bool:
    """Steam recorded a play that Keepsake never saw start (section 10)."""
    if not last_played:
        return False
    if last_session_start is None:
        return True
    return last_played > last_session_start + PLAYED_WITHOUT_SLACK_SECONDS
