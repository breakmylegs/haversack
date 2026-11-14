"""On-device diagnostics for slice 1.

Collects the facts ADR-0001 and ADR-0002 depend on and writes a redacted
export to the settings folder. Nothing here writes outside the plugin's own
folders: write access to ``compatdata`` is checked with ``os.access`` only.
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from .discovery import (
    Shortcut,
    find_compatdata,
    library_folders,
    read_shortcuts,
    real_home,
    steam_roots,
    steam_user_ids,
)
from .fsutil import atomic_write_json, read_json
from .log import tail
from .procs import find_game_processes
from .redact import redact
from .vdf import VdfError

PROBE_FILE = "probe-events.json"
PROBE_LIMIT = 200
ENV_NAMES = (
    "HOME",
    "USER",
    "XDG_RUNTIME_DIR",
    "DECKY_VERSION",
    "DECKY_USER",
    "DECKY_USER_HOME",
    "DECKY_HOME",
    "DECKY_PLUGIN_SETTINGS_DIR",
    "DECKY_PLUGIN_RUNTIME_DIR",
    "DECKY_PLUGIN_LOG_DIR",
    "DECKY_PLUGIN_DIR",
    "DECKY_PLUGIN_NAME",
    "DECKY_PLUGIN_VERSION",
    "DECKY_PLUGIN_AUTHOR",
    "DECKY_PLUGIN_LOG",
)
HTTPS_TEST_URL = "https://api.github.com/zen"


def _module_info(name: str, attr: str | None = None) -> dict[str, Any]:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - any import failure is a finding
        return {"available": False, "error": type(exc).__name__}
    info: dict[str, Any] = {"available": True}
    if attr:
        info["version"] = str(getattr(module, attr, "unknown"))
    return info


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if name in ("USER", "DECKY_USER") and value not in (None, "deck", "root"):
        # Usernames other than the stock ones are personal data.
        return "[other user]"
    return value


def _os_release() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                key, sep, value = line.strip().partition("=")
                if sep and key in ("ID", "ID_LIKE", "VERSION_ID", "VARIANT_ID", "BUILD_ID", "NAME"):
                    out[key] = value.strip('"')
    except OSError:
        pass
    return out


def environment() -> dict[str, Any]:
    home = os.environ.get("DECKY_USER_HOME") or os.path.expanduser("~")
    verify = ssl.get_default_verify_paths()
    return {
        "python": {
            "version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "modules": {
            "sqlite3": _module_info("sqlite3", "sqlite_version"),
            "ssl": {"available": True, "version": ssl.OPENSSL_VERSION},
            "aiohttp": _module_info("aiohttp", "__version__"),
            "certifi": _module_info("certifi", "__version__"),
            "zipfile": _module_info("zipfile"),
            "hashlib_blake2b": {"available": hasattr(__import__("hashlib"), "blake2b")},
        },
        "sslDefaults": {
            "cafile": verify.cafile,
            "cafileExists": bool(verify.cafile and os.path.exists(verify.cafile)),
            "capath": verify.capath,
            "capathExists": bool(verify.capath and os.path.isdir(verify.capath)),
        },
        "env": {name: _env_value(name) for name in ENV_NAMES},
        "uid": os.getuid() if hasattr(os, "getuid") else None,
        "userIsDeck": os.environ.get("DECKY_USER", os.environ.get("USER")) == "deck",
        "home": {
            "realpath": real_home(home),
            "isSymlinkOrUnderVar": real_home(home) != os.path.abspath(home) or real_home(home).startswith("/var/home"),
        },
        "osRelease": _os_release(),
        "platform": platform.platform(),
    }


def steam() -> dict[str, Any]:
    roots = steam_roots()
    out: dict[str, Any] = {"roots": []}
    for root in roots:
        libraries = library_folders(root)
        root_info: dict[str, Any] = {
            "path": root,
            "libraries": [
                {
                    "path": lib,
                    "compatdataExists": os.path.isdir(os.path.join(lib, "steamapps", "compatdata")),
                    "compatdataWritable": os.access(os.path.join(lib, "steamapps", "compatdata"), os.W_OK),
                }
                for lib in libraries
            ],
            "users": [],
        }
        for user_id in steam_user_ids(root):
            path = os.path.join(root, "userdata", user_id, "config", "shortcuts.vdf")
            user: dict[str, Any] = {"userIndex": len(root_info["users"]), "shortcutsFileExists": os.path.exists(path)}
            if user["shortcutsFileExists"]:
                try:
                    user["shortcuts"] = [_shortcut_facts(sc, libraries) for sc in read_shortcuts(path)]
                except (OSError, VdfError) as exc:
                    user["error"] = f"{type(exc).__name__}: {exc}"
            root_info["users"].append(user)
        out["roots"].append(root_info)
    return out


def _shortcut_facts(sc: Shortcut, libraries: list[str]) -> dict[str, Any]:
    compat = find_compatdata(sc.appid_unsigned, libraries)
    library_index = None
    exe_inside = False
    if compat is not None:
        library_index = libraries.index(os.path.dirname(os.path.dirname(os.path.dirname(compat))))
        exe_inside = os.path.realpath(sc.exe.strip('"')).startswith(compat + os.sep)
    return {
        "name": sc.name,
        "appidSigned": sc.appid_signed,
        "appidUnsigned": sc.appid_unsigned,
        "compatdataFound": compat is not None,
        "compatdataLibraryIndex": library_index,
        "compatdataWritable": os.access(compat, os.W_OK) if compat else None,
        "exeInsidePrefix": exe_inside,
        "lastPlayTime": sc.last_play_time,
    }


def game_processes(appid: int) -> list[dict[str, Any]]:
    if not os.path.isdir("/proc"):
        return []
    return [
        {
            "pid": p.pid,
            "ppid": p.ppid,
            "comm": p.comm,
            "cmdline": p.cmdline,
            "match": p.match,
            "env": p.env,
        }
        for p in find_game_processes(appid)
    ]


def https_test(url: str = HTTPS_TEST_URL, timeout: float = 10.0) -> dict[str, Any]:
    """Make one unauthenticated HTTPS request with the default SSL context."""
    started = time.monotonic()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Keepsake-diagnostics"})
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            status = response.status
        return {"ok": True, "status": status, "ms": int((time.monotonic() - started) * 1000)}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc.reason}"}
    except Exception as exc:  # noqa: BLE001 - report whatever went wrong
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# Frontend probe events (lifetime notifications, game actions, suspend and resume)


def record_probe_event(runtime_dir: str, kind: str, payload: Any) -> int:
    path = os.path.join(runtime_dir, PROBE_FILE)
    events = read_json(path, default=[])
    if not isinstance(events, list):
        events = []
    text = json.dumps(payload, default=str)
    if len(text) > 8000:
        payload = {"truncated": text[:8000]}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    events.append({"ts": now, "kind": str(kind)[:64], "payload": payload})
    events = events[-PROBE_LIMIT:]
    atomic_write_json(path, events)
    return len(events)


def probe_events(runtime_dir: str) -> list[Any]:
    events = read_json(os.path.join(runtime_dir, PROBE_FILE), default=[])
    return events if isinstance(events, list) else []


def export(
    settings_dir: str,
    runtime_dir: str,
    log_dir: str,
    frontend: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Write a redacted diagnostics file and return its path."""
    report: dict[str, Any] = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": environment(),
        "steam": steam(),
        "probeEvents": probe_events(runtime_dir),
        "frontend": frontend or {},
        "recentLog": tail(log_dir, 100),
    }
    if extra:
        report.update(extra)
    name = time.strftime("diagnostics-%Y%m%d-%H%M%S.json", time.gmtime())
    path = os.path.join(settings_dir, name)
    atomic_write_json(path, redact(report), mode=0o600)
    return path
