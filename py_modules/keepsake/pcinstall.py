"""Install Keepsake on a PC from its signed package (ADR-0038, P5).

Everything stays in the user's own folders and needs no administrator rights:

- the program in a folder per version (Windows ``%LOCALAPPDATA%\\Keepsake\\app\\<version>``,
  Linux ``~/.local/share/keepsake/app/<version>``), with ``current.json`` naming the one
  in use and the previous one kept, so an update can switch and roll back;
- a small launcher, ``keepsake.pyw``, next to them, which runs the current version;
- start at sign-in: a ``HKCU`` Run value with ``pythonw.exe`` on Windows (no console
  window, no shortcut file to create); XDG autostart and app-menu ``.desktop`` files on Linux.

Settings, state and saves live elsewhere (``keepsake.host.platform_paths``) and are never
touched by installing, updating or uninstalling.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

from . import hosts
from .fsutil import atomic_write_json, read_json

CURRENT = "current.json"
LAUNCHER = "keepsake.pyw"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Keepsake"
KEEP_VERSIONS = 2  # the current one and the previous one, for a rollback
_VERSION_CHARS = set("0123456789.-abcdefghijklmnopqrstuvwxyz")

LAUNCHER_TEXT = '''"""Starts the installed Haversack version (written by Haversack's installer, ADR-0038)."""
import json
import os
import sys

root = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(root, "current.json"), encoding="utf-8") as handle:
    version = json.load(handle)["version"]
sys.path.insert(0, os.path.join(root, version, "py_modules"))

from keepsake import launcher  # noqa: E402

sys.exit(launcher.main(sys.argv[1:]))
'''


class InstallError(Exception):
    pass


def app_root(host: str, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    if host == "windows":
        local = env.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(local, "Keepsake", "app")
    data = env.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(data, "keepsake", "app")


def package_version(package_dir: str) -> str:
    try:
        with open(os.path.join(package_dir, "VERSION"), encoding="utf-8") as handle:
            text = handle.read().strip()
    except OSError as exc:
        raise InstallError("this folder is not a Haversack package (no VERSION file)") from exc
    if not text or len(text) > 40 or set(text) - _VERSION_CHARS or text.startswith("."):
        raise InstallError("the package's VERSION is not valid")
    return text


def installed(host: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    try:
        data = read_json(os.path.join(app_root(host, env), CURRENT), default={})
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def pythonw(python: str) -> str:
    """``pythonw.exe`` next to ``python.exe`` on Windows, so start-up opens no console window."""
    candidate = os.path.join(os.path.dirname(python), "pythonw.exe")
    return candidate if os.path.isfile(candidate) else python


def install(
    package_dir: str,
    host: str,
    env: Mapping[str, str] | None = None,
    python: str = sys.executable,
    autostart: bool = True,
    registry: Any = None,
    entries: bool = True,
) -> dict[str, Any]:
    """Copy the package into its version folder, switch ``current.json``, write the launcher and start-up entries.

    ``entries=False`` (self-update) leaves the start-up and menu entries as the user set them.
    """
    if host not in ("windows", "linux-desktop"):
        raise InstallError("on a Decky device Haversack is installed through Decky, not this installer")
    version = package_version(package_dir)
    root = app_root(host, env)
    os.makedirs(root, exist_ok=True)
    target = os.path.join(root, version)
    staging = target + ".installing"
    if os.path.exists(staging):
        shutil.rmtree(staging)
    shutil.copytree(package_dir, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "install.pyw"))
    if os.path.exists(target):
        shutil.rmtree(target)
    os.replace(staging, target)
    previous = installed(host, env).get("version")
    record = {"version": version, "previous": previous if previous and previous != version else None}
    atomic_write_json(os.path.join(root, CURRENT), record)
    launcher = os.path.join(root, LAUNCHER)
    with open(launcher, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(LAUNCHER_TEXT)
    pruned = _prune(root, {version, record["previous"]})
    written = _start_entries(host, launcher, python, env, autostart, registry) if entries else []
    return {"version": version, "folder": target, "launcher": launcher, "pruned": pruned, "entries": written}


def _prune(root: str, keep: set[str | None]) -> list[str]:
    removed = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path) and name not in keep and os.path.isfile(os.path.join(path, "VERSION")):
            shutil.rmtree(path)
            removed.append(name)
    return removed


def _desktop_entry(command: str, comment: str) -> str:
    return (
        "[Desktop Entry]\nType=Application\nName=Haversack\n"
        f"Comment={comment}\nExec={command}\nTerminal=false\nCategories=Game;Utility;\n"
    )


def _start_entries(
    host: str, launcher: str, python: str, env: Mapping[str, str] | None, autostart: bool, registry: Any
) -> list[str]:
    written: list[str] = []
    if host == "windows":
        if autostart:
            command = f'"{pythonw(python)}" "{launcher}" --background'
            _set_run_value(command, registry)
            written.append("HKCU Run: Keepsake")
        return written
    env = os.environ if env is None else env
    home = os.path.expanduser("~")
    config = env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    data = env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    menu = os.path.join(data, "applications", "keepsake.desktop")
    os.makedirs(os.path.dirname(menu), exist_ok=True)
    with open(menu, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_desktop_entry(f'"{python}" "{launcher}"', "Keeps game saves in step between your devices"))
    written.append(menu)
    if autostart:
        start = os.path.join(config, "autostart", "keepsake.desktop")
        os.makedirs(os.path.dirname(start), exist_ok=True)
        with open(start, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_desktop_entry(f'"{python}" "{launcher}" --background', "Starts Haversack when you sign in"))
        written.append(start)
    return written


def _set_run_value(command: str | None, registry: Any = None) -> None:
    """Write (or with None remove) the HKCU Run value. ``registry`` is ``winreg`` (a fake in tests)."""
    if registry is None:
        import winreg as registry  # Windows only
    with registry.CreateKey(registry.HKEY_CURRENT_USER, RUN_KEY) as key:
        if command is None:
            try:
                registry.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass
        else:
            registry.SetValueEx(key, RUN_VALUE, 0, registry.REG_SZ, command)


def uninstall(host: str, env: Mapping[str, str] | None = None, registry: Any = None) -> list[str]:
    """Remove the program and its start-up entries. Settings, state and saves stay."""
    removed = []
    if host == "windows":
        _set_run_value(None, registry)
        removed.append("HKCU Run: Keepsake")
    else:
        env = os.environ if env is None else env
        home = os.path.expanduser("~")
        for path in (
            os.path.join(env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "autostart", "keepsake.desktop"),
            os.path.join(
                env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"), "applications", "keepsake.desktop"
            ),
        ):
            if os.path.isfile(path):
                os.unlink(path)
                removed.append(path)
    root = app_root(host, env)
    if os.path.isdir(root):
        shutil.rmtree(root)
        removed.append(root)
    return removed


def main(package_dir: str, argv: list[str]) -> int:
    host = hosts.host()
    try:
        if "--uninstall" in argv:
            for item in uninstall(host):
                print(f"Removed {item}")
            print("Haversack is removed. Your settings and saves are kept.")
            return 0
        result = install(package_dir, host, autostart="--no-autostart" not in argv)
    except (InstallError, OSError) as exc:
        print(f"Haversack could not be installed: {exc}", file=sys.stderr)
        return 1
    print(f"Haversack {result['version']} is installed in {result['folder']}.")
    if "--no-start" not in argv:
        subprocess.Popen([pythonw(sys.executable), result["launcher"]], close_fds=True)
    return 0
