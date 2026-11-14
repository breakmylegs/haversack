"""Running-process inspection through ``/proc`` (Linux only).

The ``proc_root`` argument lets tests point at a synthetic folder tree.
Only processes owned by the plugin's user are considered (threat model T7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

ENV_KEYS = ("STEAM_COMPAT_DATA_PATH", "SteamGameId", "SteamAppId", "SteamOverlayGameId")
SHORTCUT_GAMEID_FLAG = 0x02000000


@dataclass
class ProcInfo:
    pid: int
    ppid: int
    uid: int
    comm: str
    starttime: int
    cmdline: str
    env: dict[str, str] = field(default_factory=dict)
    match: str = ""


def _read(path: str) -> bytes | None:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def read_proc(pid: int, proc_root: str = "/proc") -> ProcInfo | None:
    base = os.path.join(proc_root, str(pid))
    stat = _read(os.path.join(base, "stat"))
    status = _read(os.path.join(base, "status"))
    if stat is None or status is None:
        return None
    text = stat.decode("utf-8", errors="replace")
    open_paren = text.find("(")
    close_paren = text.rfind(")")
    if open_paren < 0 or close_paren < 0:
        return None
    comm = text[open_paren + 1 : close_paren]
    rest = text[close_paren + 2 :].split()
    try:
        ppid = int(rest[1])
        starttime = int(rest[19])
    except (IndexError, ValueError):
        return None
    uid = -1
    for line in status.decode("utf-8", errors="replace").splitlines():
        if line.startswith("Uid:"):
            parts = line.split()
            if len(parts) > 1 and parts[1].isdigit():
                uid = int(parts[1])
            break
    raw_cmd = _read(os.path.join(base, "cmdline")) or b""
    cmdline = raw_cmd.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()[:300]
    env: dict[str, str] = {}
    raw_env = _read(os.path.join(base, "environ"))
    if raw_env:
        for item in raw_env.split(b"\x00"):
            key, sep, value = item.partition(b"=")
            if sep:
                name = key.decode("utf-8", errors="replace")
                if name in ENV_KEYS:
                    env[name] = value.decode("utf-8", errors="replace")
    return ProcInfo(pid=pid, ppid=ppid, uid=uid, comm=comm, starttime=starttime, cmdline=cmdline, env=env)


def list_procs(proc_root: str = "/proc", uid: int | None = None) -> list[ProcInfo]:
    try:
        names = os.listdir(proc_root)
    except OSError:
        return []
    out: list[ProcInfo] = []
    for name in names:
        if not name.isdigit():
            continue
        info = read_proc(int(name), proc_root)
        if info is None:
            continue
        if uid is not None and info.uid != uid:
            continue
        out.append(info)
    return out


def _ancestors(pid: int, by_pid: dict[int, ProcInfo]) -> set[int]:
    seen: set[int] = set()
    current = by_pid.get(pid)
    while current is not None and current.ppid not in seen and current.ppid > 1:
        seen.add(current.ppid)
        current = by_pid.get(current.ppid)
    return seen


def match_reason(info: ProcInfo, appid: int, compat_path: str | None = None) -> str:
    """Explain why ``info`` belongs to the game ``appid``, or return ''."""
    appid = int(appid) & 0xFFFFFFFF
    compat = info.env.get("STEAM_COMPAT_DATA_PATH", "").rstrip("/")
    if compat:
        if compat_path and os.path.realpath(compat) == os.path.realpath(compat_path):
            return "compat-path"
        if compat.endswith(f"/compatdata/{appid}"):
            return "compat-id"
    shortcut_gameid = str((appid << 32) | SHORTCUT_GAMEID_FLAG)
    game_id = info.env.get("SteamGameId", "")
    if game_id and game_id in (str(appid), shortcut_gameid):
        return "steam-game-id"
    if info.env.get("SteamAppId", "") == str(appid):
        return "steam-app-id"
    return ""


def find_game_processes(
    appid: int,
    compat_path: str | None = None,
    proc_root: str = "/proc",
    uid: int | None = None,
    self_pid: int | None = None,
) -> list[ProcInfo]:
    """Return the game's processes and their descendants, owned by ``uid``.

    The plugin's own process and its ancestors (Decky, Steam) are never
    included, whatever their environment says.
    """
    if uid is None:
        uid = os.getuid() if hasattr(os, "getuid") else -1
    if self_pid is None:
        self_pid = os.getpid()
    procs = list_procs(proc_root, uid=uid)
    by_pid = {p.pid: p for p in procs}
    protected = {self_pid} | _ancestors(self_pid, by_pid)

    selected: dict[int, ProcInfo] = {}
    for info in procs:
        if info.pid in protected:
            continue
        reason = match_reason(info, appid, compat_path)
        if reason:
            info.match = reason
            selected[info.pid] = info

    children: dict[int, list[ProcInfo]] = {}
    for info in procs:
        children.setdefault(info.ppid, []).append(info)
    stack = list(selected)
    while stack:
        for child in children.get(stack.pop(), []):
            if child.pid not in selected and child.pid not in protected:
                child.match = "descendant"
                selected[child.pid] = child
                stack.append(child.pid)
    return sorted(selected.values(), key=lambda p: p.pid)
