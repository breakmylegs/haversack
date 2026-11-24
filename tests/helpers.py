"""Synthetic fixture builders. No real save files or personal data here."""

from __future__ import annotations

import os
import struct
from typing import Any


def dumps_binary_vdf(value: dict[str, Any]) -> bytes:
    """Encode a dict as binary VDF, the way Steam writes ``shortcuts.vdf``.

    Test-only: Keepsake itself never writes VDF.
    """

    def encode(mapping: dict[str, Any]) -> bytes:
        out = bytearray()
        for key, item in mapping.items():
            name = key.encode("utf-8") + b"\x00"
            if isinstance(item, dict):
                out += b"\x00" + name + encode(item)
            elif isinstance(item, str):
                out += b"\x01" + name + item.encode("utf-8") + b"\x00"
            elif isinstance(item, int):
                out += b"\x02" + name + struct.pack("<i", item if item < 2**31 else item - 2**32)
            else:
                raise TypeError(type(item))
        out += b"\x08"
        return bytes(out)

    return encode(value) + b"\x08"


def shortcut_entry(appid_signed: int, name: str, exe: str, start_dir: str = "", last_play: int = 0) -> dict[str, Any]:
    return {
        "appid": appid_signed,
        "AppName": name,
        "Exe": f'"{exe}"',
        "StartDir": f'"{start_dir}"',
        "LaunchOptions": "",
        "LastPlayTime": last_play,
        "tags": {},
    }


def files_in(roots):
    """``{root: [rel, ...]}`` for every file under each root, skipping Keepsake's own folders."""
    out = {}
    for name, path in roots.items():
        rels = []
        for folder, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".keepsake-")]
            for f in files:
                rels.append(os.path.relpath(os.path.join(folder, f), path).replace(os.sep, "/"))
        out[name] = sorted(rels)
    return out


def tree_state(roots):
    """``{(root, rel): bytes}`` for comparing folder contents."""
    state = {}
    for name, rels in files_in(roots).items():
        for rel in rels:
            with open(os.path.join(roots[name], *rel.split("/")), "rb") as handle:
                state[(name, rel)] = handle.read()
    return state


def write_tree(roots, state):
    for (name, rel), data in state.items():
        path = os.path.join(roots[name], *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)


STEAMID64_BASE = 76561197960265728


def make_fake_steam(home, users=None, apps=None, extra_libraries=(), most_recent=None, prefixes=()):
    """Build a synthetic Steam install under ``home`` and return its root.

    ``users`` maps id3 to a list of shortcut entries (see ``shortcut_entry``).
    ``apps`` is a list of ``(library_or_None, appid, name, installdir)``; None
    means the base library. ``prefixes`` is a list of ``(library_or_None, id)``
    that get a ``compatdata/<id>/pfx`` folder.
    """
    root = home / ".local" / "share" / "Steam"
    (root / "steamapps").mkdir(parents=True)
    lines = ['"libraryfolders"', "{", f'"0" {{ "path" "{root.as_posix()}" }}']
    for i, lib in enumerate(extra_libraries, start=1):
        (lib / "steamapps").mkdir(parents=True, exist_ok=True)
        lines.append(f'"{i}" {{ "path" "{lib.as_posix()}" }}')
    lines.append("}")
    (root / "steamapps" / "libraryfolders.vdf").write_text("\n".join(lines))

    login = ['"users"', "{"]
    for id3, shortcuts in (users or {}).items():
        config = root / "userdata" / id3 / "config"
        config.mkdir(parents=True)
        if shortcuts is not None:
            (config / "shortcuts.vdf").write_bytes(
                dumps_binary_vdf({"shortcuts": {str(i): s for i, s in enumerate(shortcuts)}})
            )
        flag = "1" if id3 == most_recent else "0"
        login.append(
            f'"{int(id3) + STEAMID64_BASE}" {{ "AccountName" "acct{id3}" "MostRecent" "{flag}" "Timestamp" "1" }}'
        )
    login.append("}")
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "loginusers.vdf").write_text("\n".join(login))

    for library, appid, name, installdir in apps or []:
        lib = library or root
        (lib / "steamapps" / "common" / installdir).mkdir(parents=True, exist_ok=True)
        (lib / "steamapps" / f"appmanifest_{appid}.acf").write_text(
            f'"AppState" {{ "appid" "{appid}" "name" "{name}" "installdir" "{installdir}" "LastPlayed" "1700000000" }}'
        )
    for library, appid in prefixes:
        lib = library or root
        (lib / "steamapps" / "compatdata" / str(appid) / "pfx").mkdir(parents=True)
    return root


def write_fake_proc(
    root: str,
    pid: int,
    ppid: int,
    comm: str,
    uid: int = 1000,
    starttime: int = 1000,
    env: dict[str, str] | None = None,
    cmdline: str = "",
) -> None:
    """Create a minimal ``/proc/<pid>`` entry under ``root``."""
    base = os.path.join(root, str(pid))
    os.makedirs(base, exist_ok=True)
    # Fields after "(comm)": state ppid pgrp session tty tpgid flags minflt cminflt majflt cmajflt
    # utime stime cutime cstime priority nice threads itrealvalue starttime
    fields = ["S", str(ppid)] + ["0"] * 17 + [str(starttime)] + ["0"] * 10
    with open(os.path.join(base, "stat"), "w", encoding="utf-8") as handle:
        handle.write(f"{pid} ({comm}) " + " ".join(fields) + "\n")
    with open(os.path.join(base, "status"), "w", encoding="utf-8") as handle:
        handle.write(f"Name:\t{comm}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    with open(os.path.join(base, "cmdline"), "wb") as handle:
        handle.write(cmdline.replace(" ", "\x00").encode("utf-8"))
    with open(os.path.join(base, "environ"), "wb") as handle:
        handle.write(b"\x00".join(f"{k}={v}".encode() for k, v in (env or {}).items()))


MANIFEST = '---\nExample Quest:\n  files:\n    "<winLocalAppData>/ExampleQuest":\n      tags:\n        - save\n'


class Device:
    """One simulated handheld with one non-Steam shortcut, "Example Quest", in its own prefix.

    Two devices give the shortcut different app IDs, as Steam does (ADR-0011).
    """

    def __init__(self, tmp_path, name, appid):
        from keepsake.app import KeepsakeApp
        from keepsake.paths import PluginPaths

        base = tmp_path / name
        home = base / "home"
        home.mkdir(parents=True)
        root = make_fake_steam(
            home, users={"7": [shortcut_entry(appid - 2**32, "Example Quest", "/g.exe")]}, prefixes=[(None, appid)]
        )
        self.key = f"shortcut:7:{appid}"
        prefix = root / "steamapps/compatdata" / str(appid) / "pfx"
        self.saves = prefix / "drive_c/users/steamuser/AppData/Local/ExampleQuest"
        self.saves.mkdir(parents=True)
        self.events: list[tuple[str, tuple[Any, ...]]] = []

        async def emit(event, *args):
            self.events.append((event, args))

        paths = PluginPaths(*(str(base / n) for n in ("settings", "runtime", "logs", "plugin")))
        self.app = KeepsakeApp(
            paths, emit=emit, proc_root=str(base / "proc"), version="0.9.0", home=str(home), auto_refresh_manifest=False
        )
        manifest_file = base / "manifest.yaml"
        manifest_file.write_text(MANIFEST)
        self.app.manifest.import_file(str(manifest_file))
        self.app.settings.set("deviceName", f"Handheld {name.upper()}")

    def toasts(self):
        return [args[0] for event, args in self.events if event == "keepsake_toast"]
