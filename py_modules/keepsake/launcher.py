"""Open Keepsake on a PC: reuse the running host, or start one (ADR-0038, P5).

    python -m keepsake.launcher [--background]

``host.json`` (port and token) is trusted only after the host it names answers a
token-protected call: a file left by a host that has stopped, or a port now used
by another program, never gets the browser or the token.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser
from typing import Any

from . import host as pc_host
from . import hosts

CHECK_TIMEOUT = 3.0


def running_host(runtime_dir: str, opener: Any = urllib.request.urlopen) -> str | None:
    """The launcher link of a host that is alive and holds the recorded token, or None."""
    try:
        with open(os.path.join(runtime_dir, pc_host.STATE_FILE), encoding="utf-8") as handle:
            state = json.load(handle)
        port, token = int(state["port"]), str(state["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not 1 <= port <= 65535 or not token:
        return None
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/call/get_status",
        data=b'{"args": []}',
        headers={"Content-Type": "application/json", "X-Keepsake-Token": token},
        method="POST",
    )
    try:
        with opener(request, timeout=CHECK_TIMEOUT) as response:
            body = json.loads(response.read(65536))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if not isinstance(body, dict) or body.get("ok") is not True:
        return None
    return f"http://127.0.0.1:{port}/#token={token}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    background = "--background" in argv
    paths = pc_host.platform_paths(hosts.host())
    link = running_host(paths.runtime_dir)
    if link:
        if not background:
            webbrowser.open(link)
        return 0
    asyncio.run(pc_host.run(pc_host.DEFAULT_PORT, open_browser=not background))
    return 0


if __name__ == "__main__":
    sys.exit(main())
