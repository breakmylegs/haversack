"""The Desktop Mode entries the plugin writes for its tray and app menu (ADR-0068).

Two files in the user's own folders, and nothing else (write allowlist, ADR-0017):

- ``~/.config/autostart/keepsake-tray.desktop``: starts the tray, minimised, at Desktop login;
- ``~/.local/share/applications/keepsake.desktop``: the app-menu entry, which opens Keepsake
  (or brings up the running tray's window).

Both run the plugin's own tray script with the system ``python3`` (ADR-0018) and use the plugin's
own icon, so no icon file is written. Each carries ``X-Keepsake-Version``: a plugin update rewrites
them, so the desktop app never runs a different version from the plugin. Removing deletes only files
Keepsake wrote (they carry that key), never a user's own file of the same name.
"""

from __future__ import annotations

import os
from typing import Any

AUTOSTART = (".config", "autostart", "keepsake-tray.desktop")
APP_MENU = (".local", "share", "applications", "keepsake.desktop")
MARKER = "X-Keepsake-Version"
TRAY_SCRIPT = ("py_modules", "keepsake", "desktop", "tray.py")
ICON_DIR = ("assets", "icons")
ICON_NAME = "keepsake-tray"


def paths(home: str) -> dict[str, str]:
    return {"autostart": os.path.join(home, *AUTOSTART), "appMenu": os.path.join(home, *APP_MENU)}


def _quote(argument: str) -> str:
    """An Exec argument quoted as the Desktop Entry specification asks."""
    if not any(c in argument for c in " \t\n\"'\\><~|&;$*?#()`"):
        return argument
    escaped = argument.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def _linux(folder: str, *parts: str) -> str:
    """A path for a desktop entry: always "/"-separated, as only Linux desktops read these files."""
    return "/".join([folder.replace(os.sep, "/").rstrip("/"), *parts])


def render(kind: str, plugin_dir: str, runtime_dir: str, version: str) -> str:
    script = _linux(plugin_dir, *TRAY_SCRIPT)
    command = ["python3", script, "--runtime", runtime_dir.replace(os.sep, "/")] + (
        ["--open"] if kind == "appMenu" else []
    )
    exec_line = " ".join(_quote(a) for a in command).replace("%", "%%")
    icon = _linux(plugin_dir, *ICON_DIR, "hicolor", "256x256", "apps", f"{ICON_NAME}.png")
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Keepsake",
        "Comment=Your saves, games and devices, in Desktop Mode",
        f"Exec={exec_line}",
        f"Icon={icon}",
        "Terminal=false",
        "StartupNotify=false",
    ]
    if kind == "autostart":
        lines += ["NoDisplay=true", "X-GNOME-Autostart-enabled=true", "X-KDE-autostart-phase=2"]
    else:
        lines += ["Categories=Game;Utility;", "Keywords=saves;sync;backup;games;"]
    lines.append(f"{MARKER}={version}")
    return "\n".join(lines) + "\n"


def ours(path: str) -> bool:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return any(line.startswith(MARKER + "=") for line in handle)
    except OSError:
        return False


def install(home: str, plugin_dir: str, runtime_dir: str, version: str) -> list[str]:
    """Write both entries (only when they differ). Returns the ones written."""
    written = []
    for kind, path in paths(home).items():
        text = render(kind, plugin_dir, runtime_dir, version)
        try:
            with open(path, encoding="utf-8") as handle:
                if handle.read() == text:
                    continue
        except OSError:
            pass
        if os.path.exists(path) and not ours(path):
            continue  # a file of the user's own with this name: left alone
        os.makedirs(os.path.dirname(path), exist_ok=True)
        part = path + ".keepsake-new"
        with open(part, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(part, 0o644)
        os.replace(part, path)
        written.append(path)
    return written


def remove(home: str) -> list[str]:
    """Delete both entries if Keepsake wrote them. Returns the ones removed."""
    removed = []
    for path in paths(home).values():
        if ours(path):
            os.unlink(path)
            removed.append(path)
    return removed


def read(path: str) -> dict[str, str]:
    """The keys of a desktop entry's ``[Desktop Entry]`` group."""
    keys: dict[str, str] = {}
    group = None
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    group = line[1:-1]
                elif group == "Desktop Entry" and "=" in line:
                    key, value = line.split("=", 1)
                    keys[key.strip()] = value.strip()
    except OSError:
        return {}
    return keys


def check(home: str, plugin_dir: str, version: str) -> dict[str, Any]:
    """Whether both entries exist, name this version, and are valid (for the Device check)."""
    out: dict[str, Any] = {}
    script = _linux(plugin_dir, *TRAY_SCRIPT)
    for kind, path in paths(home).items():
        keys = read(path)
        problems = []
        if not keys:
            problems.append("missing")
        else:
            if keys.get("Type") != "Application" or not keys.get("Name") or not keys.get("Exec"):
                problems.append("not a valid application entry")
            if keys.get(MARKER) != version:
                problems.append(f"names version {keys.get(MARKER) or 'none'}")
            if script not in keys.get("Exec", "").replace('\\"', '"'):
                problems.append("does not run this plugin's tray")
            if not os.path.isfile(keys.get("Icon", "")):
                problems.append("its icon is missing")
        out[kind] = problems
    return out
