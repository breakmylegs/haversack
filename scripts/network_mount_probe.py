"""Network mount probe (v2 slice 22, ADR-0033): what a device offers for reaching SMB and NFS shares.

Read-only by default. It mounts nothing, starts nothing and needs no root.
Standard library only and self-contained, so it can run over SSH without
installing anything. From the laptop (PowerShell):

    Get-Content scripts\\network_mount_probe.py | ssh deck@<device> "python3 -"

Run it once in Gaming Mode and once in Desktop Mode, with a share opened in
Dolphin for the Desktop run, and paste both outputs into the slice report.

The loop test that used to run here with ``--loop-test`` is now the Device check
"Network ISO in place", run from Keepsake's Diagnostics page with no SSH (ADR-0067).

It prints no user names, host names, share names or paths: mounts are reported
by filesystem type and folder depth only.
"""

from __future__ import annotations

import json
import os
import shutil

BINARIES = (
    "gio",
    "gdbus",
    "busctl",
    "smbclient",
    "mount.cifs",
    "mount.nfs",
    "rclone",
    "sshfs",
    "fusermount3",
    "udisksctl",
)
LIBEXEC = (
    "/usr/lib/gvfsd",
    "/usr/lib/gvfs/gvfsd",
    "/usr/libexec/gvfsd",
    "/usr/lib/gvfsd-fuse",
    "/usr/lib/gvfs/gvfsd-fuse",
    "/usr/libexec/gvfsd-fuse",
    "/usr/lib/gvfsd-smb",
    "/usr/libexec/gvfsd-smb",
    "/usr/lib/kio-fuse",
    "/usr/libexec/kio-fuse",
)
DBUS_SERVICES = (
    "/usr/share/dbus-1/services/org.kde.KIOFuse.service",
    "/usr/share/dbus-1/services/org.gtk.vfs.Daemon.service",
)
STAGING = ("~/homebrew/data/Keepsake/installer/staging", "~/homebrew/data/Keepsake", "~")
NETWORK_FS = ("cifs", "smb3", "nfs", "nfs4", "fuse.sshfs", "fuse.rclone", "fuse.gvfsd-fuse", "fuse.kio-fuse", "9p")


def mounts() -> list[dict[str, object]]:
    found = []
    try:
        with open("/proc/self/mounts", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return found
    for line in lines:
        parts = line.split()
        if len(parts) >= 3 and (parts[2] in NETWORK_FS or parts[2].startswith("fuse.")):
            point = parts[1]
            found.append(
                {"fstype": parts[2], "depth": point.count("/"), "underRunUser": point.startswith("/run/user/")}
            )
    return found


def staging_free() -> dict[str, object]:
    """Free space where Keepsake stages network downloads (the first folder that exists)."""
    for path in STAGING:
        full = os.path.expanduser(path)
        if os.path.isdir(full):
            return {"folder": path, "freeGiB": round(shutil.disk_usage(full).free / 1024**3, 1)}
    return {"folder": None, "freeGiB": None}


def session_bus() -> dict[str, object]:
    address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    socket_path = os.path.join(runtime, "bus") if runtime else ""
    return {
        "addressSet": bool(address),
        "defaultSocket": bool(socket_path) and os.path.exists(socket_path),
        "xdgRuntimeDir": bool(runtime),
    }


def running(names: tuple[str, ...]) -> dict[str, bool]:
    """Whether a process with each name runs as this user (from /proc; no command lines are printed)."""
    found = dict.fromkeys(names, False)
    uid = os.getuid() if hasattr(os, "getuid") else -1
    for pid in os.listdir("/proc") if os.path.isdir("/proc") else []:
        if not pid.isdigit():
            continue
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as handle:
                comm = handle.read().strip()
        except OSError:
            continue
        for name in names:
            if comm == name[:15]:
                found[name] = True
    return found


def main() -> None:
    report = {
        "binaries": {name: bool(shutil.which(name)) for name in BINARIES},
        "helpers": {path: os.path.exists(path) for path in LIBEXEC},
        "dbusServices": {os.path.basename(path): os.path.exists(path) for path in DBUS_SERVICES},
        "sessionBus": session_bus(),
        "running": running(("gvfsd", "gvfsd-fuse", "kio-fuse", "kded6", "kded5", "plasmashell", "gamescope")),
        "fuseDevice": os.access("/dev/fuse", os.R_OK | os.W_OK),
        "stagingFree": staging_free(),
        "fstabUserEntries": 0,
        "networkMounts": mounts(),
    }
    try:
        with open("/etc/fstab", encoding="utf-8", errors="replace") as handle:
            report["fstabUserEntries"] = sum(
                1
                for line in handle
                if not line.lstrip().startswith("#") and len(line.split()) >= 4 and "user" in line.split()[3].split(",")
            )
    except OSError:
        pass
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
