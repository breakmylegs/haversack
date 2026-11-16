"""Network mount spike probe (v2 slice 22): what a device offers for reaching SMB and NFS shares.

Read-only. It mounts nothing, starts nothing and needs no root. Standard library
only and self-contained, so it can run over SSH without installing anything:

    ssh deck@<device> python3 - < scripts/network_mount_probe.py

Run it once in Gaming Mode and once in Desktop Mode, with a share opened in
Dolphin for the Desktop run, and paste both outputs into the slice 22 report.
It prints no user names, host names or share names: mounts are reported by
filesystem type and folder depth only.
"""

from __future__ import annotations

import json
import os
import shutil

BINARIES = ("gio", "smbclient", "mount.cifs", "mount.nfs", "rclone", "sshfs", "fusermount3", "udisksctl")
LIBEXEC = ("/usr/lib/gvfsd", "/usr/lib/gvfs/gvfsd", "/usr/libexec/gvfsd", "/usr/lib/kio-fuse", "/usr/libexec/kio-fuse")
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


def main() -> None:
    report = {
        "binaries": {name: bool(shutil.which(name)) for name in BINARIES},
        "helpers": {path: os.path.exists(path) for path in LIBEXEC},
        "sessionBus": bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")),
        "xdgRuntimeDir": bool(os.environ.get("XDG_RUNTIME_DIR")),
        "fuseDevice": os.access("/dev/fuse", os.R_OK | os.W_OK),
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
