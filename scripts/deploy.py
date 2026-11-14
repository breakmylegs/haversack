"""Deploy a development build to a device over SSH.

Reads ``deploy.local.json`` (git-ignored) from the repository root:

    {"host": "steamdeck.local", "user": "deck", "port": 22}

Builds the zip with scripts/package.py, copies it to the device, replaces
~/homebrew/plugins/Keepsake and restarts Decky Loader. The plugins folder is
owned by root on a standard Decky install, so the remote step uses sudo and
prompts for the device password in the terminal. This is a development
convenience only: the plugin itself never runs as root.

Uses the OpenSSH client that ships with Windows 10 and later, macOS and Linux.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import device
import package

ROOT = package.ROOT


def main() -> int:
    host, port = device.load_target()
    name = package.plugin_name()
    zip_path = package.build(os.path.join(ROOT, "out"))
    # scp paths without a leading slash are relative to the remote home folder.
    zip_name = os.path.basename(zip_path)
    remote_zip = f"$HOME/{shlex.quote(zip_name)}"

    subprocess.run(["scp", "-P", port, zip_path, f"{host}:{zip_name}"], check=True)
    plugin_dir = f"$HOME/homebrew/plugins/{name}"
    script = " && ".join(
        [
            f"sudo rm -rf {plugin_dir}",
            f"sudo bsdtar -xpf {remote_zip} -C $HOME/homebrew/plugins",
            f"rm -f {remote_zip}",
            "sudo systemctl restart plugin_loader",
            f"echo Deployed {name}",
        ]
    )
    subprocess.run(["ssh", "-t", "-p", port, host, script], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
