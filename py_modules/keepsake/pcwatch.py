"""Which games run on a PC host, and the watcher that turns that into start and exit events (ADR-0038, P4).

On Decky, Steam's frontend reports launches. A PC host has no such hook, so it
looks at the user's own processes every few seconds:

- Windows: ``EnumProcesses`` and ``QueryFullProcessImageNameW`` through ``ctypes``.
- Linux without Decky: ``/proc/<pid>/exe``.

A process belongs to a game when its program is the shortcut's program, or sits
inside the Steam game's install folder (or a specific folder of the shortcut's
program). Broad folders such as a drive root or the home folder never count, so
an odd shortcut cannot make every program look like a game.

A start seen here only records that the game runs: the game has already started,
so no save is pulled under it (P6). Saves are pushed when it exits.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any

from .log import log_event

INTERVAL = 5.0
MIN_FOLDER_DEPTH = 3  # e.g. C:/Games/Quest: a drive root or a top-level folder is too broad


def _norm(path: str) -> str:
    real = os.path.realpath(path)
    return os.path.normcase(real) if sys.platform == "win32" else real


def list_processes() -> list[str]:
    """Program paths of the processes this user may inspect. Never raises."""
    try:
        return _windows_processes() if sys.platform == "win32" else _linux_processes()
    except OSError:
        return []


def _linux_processes(proc_root: str = "/proc") -> list[str]:
    found = []
    for name in os.listdir(proc_root):
        if name.isdigit():
            try:
                found.append(os.readlink(os.path.join(proc_root, name, "exe")))
            except OSError:
                continue  # another user's process, or it has just ended
    return found


def _windows_processes() -> list[str]:
    import ctypes
    from ctypes import wintypes

    psapi = ctypes.windll.psapi  # type: ignore[attr-defined, unused-ignore]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined, unused-ignore]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    pids = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(needed)):
        return []
    found = []
    query_limited = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION: enough for the program path, nothing more
    for pid in pids[: needed.value // ctypes.sizeof(wintypes.DWORD)]:
        if not pid:
            continue
        handle = kernel32.OpenProcess(query_limited, False, pid)
        if not handle:
            continue
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                found.append(buffer.value)
        finally:
            kernel32.CloseHandle(handle)
    return found


def _specific(folder: str | None, home: str | None) -> str | None:
    if not folder:
        return None
    norm = _norm(folder)
    parts = [p for p in norm.replace("\\", "/").split("/") if p]
    if len(parts) < MIN_FOLDER_DEPTH or (home and norm == _norm(home)):
        return None
    return norm


def game_running(game: Mapping[str, Any], processes: Iterable[str], home: str | None = None) -> bool:
    """True when one of ``processes`` (program paths) belongs to ``game``."""
    exe = game.get("exe")
    program = _norm(str(exe)) if exe else None
    folders = []
    if game.get("kind") == "steam":
        folders.append(_specific(game.get("base_dir"), home))
    elif program:
        folders.append(_specific(os.path.dirname(str(exe)), home))
    wanted = [f for f in folders if f]
    for path in processes:
        current = _norm(path)
        if program and current == program:
            return True
        if any(current.startswith(folder + os.sep) for folder in wanted):
            return True
    return False


Event = Callable[[str, int], Awaitable[Any]]


class Watcher:
    """Turns the set of running games into ``start`` and ``exit`` events for the app's lifecycle."""

    def __init__(
        self,
        games: Callable[[], Awaitable[list[dict[str, Any]]]],
        on_event: Event,
        lister: Callable[[], list[str]] = list_processes,
        home: str | None = None,
        interval: float = INTERVAL,
    ) -> None:
        self.games, self.on_event, self.lister, self.home, self.interval = games, on_event, lister, home, interval
        self.running: dict[str, int] = {}  # game key -> app ID

    async def poll(self) -> tuple[list[str], list[str]]:
        """One look: send ``start`` for games that began and ``exit`` for games that ended."""
        games = await self.games()
        processes = await asyncio.to_thread(self.lister)
        now = {g["key"]: int(g["appid"]) for g in games if game_running(g, processes, self.home)}
        started = [k for k in now if k not in self.running]
        ended = [k for k in self.running if k not in now]
        for key in started:
            await self.on_event("start", now[key])
        for key in ended:
            await self.on_event("exit", self.running[key])
        self.running = now
        return started, ended

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.poll()
            except Exception as exc:  # noqa: BLE001 - watching must never stop the host
                log_event(logging.WARNING, "pcwatch.failed", "Could not check running games", error=type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), self.interval)
            except TimeoutError:
                pass
