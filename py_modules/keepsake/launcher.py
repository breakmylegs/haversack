"""Open Keepsake on a PC: reuse the running host, or start one (ADR-0038, P5).

    python -m keepsake.launcher [--background] [--restart]

``--restart`` (after a self-update, ADR-0043) first waits for the old host to stop,
then starts the version ``current.json`` names and opens it in the browser, since the
old page's token is gone with the old host.

``host.json`` (port and token) is trusted only after the host it names answers a
token-protected call: a file left by a host that has stopped, or a port now used
by another program, never gets the browser or the token.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from typing import Any

from . import host as pc_host
from . import hosts

CHECK_TIMEOUT = 3.0
RESTART_WAIT = 30.0


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


def wait_for_exit(
    runtime_dir: str,
    check: Callable[[str], str | None] = running_host,
    sleep: Callable[[float], None] = time.sleep,
    timeout: float = RESTART_WAIT,
) -> bool:
    """After an update, wait for the old host to stop, so the new one gets the port. False on timeout."""
    waited = 0.0
    while check(runtime_dir):
        if waited >= timeout:
            return False
        sleep(0.5)
        waited += 0.5
    return True


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    background = "--background" in argv
    paths = pc_host.platform_paths(hosts.host())
    if "--restart" in argv and not wait_for_exit(paths.runtime_dir):
        return 1  # the old host is still running: leave it be
    link = running_host(paths.runtime_dir)
    if link:
        if not background:
            webbrowser.open(link)
        return 0
    asyncio.run(pc_host.run(pc_host.DEFAULT_PORT, open_browser=not background))
    return 0


if __name__ == "__main__":
    sys.exit(main())
