"""Desktop Mode probe (v2 slice 23, assumption A79): does the Decky backend keep running in Desktop Mode?

Read-only: it starts, stops and changes nothing, and needs no root. Standard
library only and self-contained, so it runs over SSH without installing
anything:

    ssh deck@<device> python3 - < scripts/desktop_mode_probe.py

Run it in Gaming Mode, switch to Desktop Mode, wait two minutes and run it
again, then paste both outputs into the slice 23 report. It prints no user,
device or game names.
"""

from __future__ import annotations

import json
import os
import time

DECKY_PORT = 1337


def processes() -> dict[str, bool]:
    wanted = {"PluginLoader": False, "gamescope": False, "plasmashell": False, "steamwebhelper": False}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                cmdline = handle.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        for name in wanted:
            if name in cmdline:
                wanted[name] = True
    return wanted


def listening(port: int) -> bool:
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(table, encoding="ascii") as handle:
                rows = handle.read().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) > 3 and fields[3] == "0A" and int(fields[1].rsplit(":", 1)[1], 16) == port:
                return True
    return False


def newest_age(folder: str) -> float | None:
    newest = None
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                mtime = os.stat(os.path.join(root, name)).st_mtime
            except OSError:
                continue
            newest = mtime if newest is None else max(newest, mtime)
    return None if newest is None else round(time.time() - newest)


def main() -> None:
    home = os.path.expanduser("~")
    report = {
        "processes": processes(),
        "deckyListening": listening(DECKY_PORT),
        "keepsakeLogAgeSeconds": newest_age(os.path.join(home, "homebrew", "logs", "Keepsake")),
        "keepsakeDataAgeSeconds": newest_age(os.path.join(home, "homebrew", "data", "Keepsake")),
        "sessionType": os.environ.get("XDG_SESSION_TYPE") or None,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
