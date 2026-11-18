"""Screenshots of the desktop interface for the user documentation (ADR-0046).

    python scripts/docs_screenshots.py [--out docs/user/images]

Serves the real desktop interface (``desktop/``, built with ``pnpm run build:desktop``)
through the real loopback API, backed by ``SampleApp``: synthetic games, devices and
snapshots only (P12). A headless Edge or Chromium captures each page. Nothing reads
this machine's games, settings or saves, so no personal data can reach a screenshot.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "py_modules"))

from keepsake import host as pc_host  # noqa: E402

PAGES = ("overview", "conflicts", "games", "cloud", "import", "history", "health", "modules", "updates", "settings")
NOW = 1_794_000_000.0  # a fixed moment, so screenshots do not change from run to run
SIZE = "1100,820"

# Synthetic names only: no real games, devices, accounts or paths (P12).
GAMES = [
    {
        "key": "shortcut:7:3000000101",
        "name": "Example Quest",
        "kind": "shortcut",
        "method": "title",
        "title": "Example Quest",
        "gameKey": "title:example-quest",
        "candidates": [],
        "proposal": None,
        "enabled": True,
        "sync": "synced",
    },
    {
        "key": "shortcut:7:3000000102",
        "name": "Sample Racer",
        "kind": "shortcut",
        "method": "steam-id",
        "title": "Sample Racer",
        "gameKey": "steam:1999999102",
        "candidates": [],
        "proposal": None,
        "enabled": True,
        "sync": "conflict",
    },
    {
        "key": "shortcut:7:3000000103",
        "name": "Demo Tactics",
        "kind": "shortcut",
        "method": "ambiguous",
        "title": None,
        "gameKey": None,
        "candidates": ["Demo Tactics", "Demo Tactics Remastered"],
        "proposal": None,
        "enabled": False,
        "sync": "off",
    },
    {
        "key": "steam:1999999104",
        "name": "Placeholder Odyssey",
        "kind": "steam",
        "method": "steam-id",
        "title": "Placeholder Odyssey",
        "gameKey": "steam:1999999104",
        "candidates": [],
        "proposal": {"candidate": {"gameKey": "title:placeholder-odyssey", "title": "Placeholder Odyssey"}},
        "enabled": False,
        "sync": "not-synced",
    },
]

CONFLICT = {
    "key": "shortcut:7:3000000102",
    "name": "Sample Racer",
    "conflict": {"heads": ["s-cloud"], "localFiles": 4},
}

CONFLICT_DETAILS = {
    "key": "shortcut:7:3000000102",
    "sides": [
        {"side": "local", "device": "Handheld A", "created": None, "files": 4, "changedFiles": 2, "bytes": 2_400_000},
        {
            "side": "cloud",
            "snapId": "s-cloud",
            "device": "Living room PC",
            "created": (NOW - 3600) * 1000,
            "files": 4,
            "changedFiles": 3,
            "bytes": 2_650_000,
        },
    ],
}

HISTORY = {
    "errors": [],
    "snapshots": [
        {
            "name": "Example Quest",
            "created": (NOW - 600) * 1000,
            "device": "Handheld A",
            "files": 12,
            "bytes": 8_100_000,
            "quarantined": False,
        },
        {
            "name": "Sample Racer",
            "created": (NOW - 3600) * 1000,
            "device": "Living room PC",
            "files": 4,
            "bytes": 2_650_000,
            "quarantined": False,
        },
        {
            "name": "Example Quest",
            "created": (NOW - 86400) * 1000,
            "device": "Handheld B",
            "files": 12,
            "bytes": 8_000_000,
            "quarantined": False,
        },
        {
            "name": "Demo Tactics",
            "created": (NOW - 2 * 86400) * 1000,
            "device": "Handheld A",
            "files": 1,
            "bytes": 40_000,
            "quarantined": True,
        },
    ],
}

HEALTH = {
    "summary": "warn",
    "checks": [
        {"label": "Cloud sign-in", "status": "ok", "detail": "Signed in to OneDrive.", "items": []},
        {"label": "Sync", "status": "ok", "detail": "Last sync 10 minutes ago.", "items": []},
        {"label": "Conflicts", "status": "warn", "detail": "1 game needs your choice.", "items": ["Sample Racer"]},
        {"label": "Save database", "status": "ok", "detail": "The Ludusavi manifest is up to date.", "items": []},
    ],
}

MODULES = {
    "modules": [
        {
            "name": "saves",
            "title": "Saves",
            "description": "Keeps game saves in step between your devices.",
            "writes": "save files, after a snapshot",
            "available": True,
            "unavailableReason": None,
            "flag": True,
            "running": True,
            "failed": None,
        },
        {
            "name": "advisor",
            "title": "Advisor",
            "description": "Recommends settings for this device. Changes nothing.",
            "writes": "nothing",
            "available": True,
            "unavailableReason": None,
            "flag": False,
            "running": False,
            "failed": None,
        },
        {
            "name": "installer",
            "title": "Installer",
            "description": "Installs Windows games from an ISO or a folder.",
            "writes": "the game folder and its prefix",
            "available": False,
            "unavailableReason": "The Installer needs Decky to create Steam shortcuts.",
            "flag": False,
            "running": False,
            "failed": None,
        },
    ]
}


class SampleApp:
    """Answers the calls the desktop interface makes, with the synthetic data above."""

    version = "1.0.0"

    def __init__(self) -> None:
        self.jobs = type("Jobs", (), {"busy_reason": staticmethod(lambda: None)})()

    async def qam_summary(self) -> dict[str, Any]:
        return {
            "store": "onedrive",
            "signedIn": True,
            "deviceName": "Living room PC",
            "lastSync": NOW - 600,
            "health": "warn",
            "problems": ["1 game needs your choice."],
            "conflicts": 1,
            "enabledGames": 2,
            "currentGame": None,
            "busy": None,
        }

    async def list_conflicts(self) -> list[dict[str, Any]]:
        return [CONFLICT]

    async def conflict_details(self, key: str) -> dict[str, Any]:
        return CONFLICT_DETAILS

    async def recent_history(self, limit: int = 50) -> dict[str, Any]:
        return HISTORY

    async def health_checks(self, force: bool = False) -> dict[str, Any]:
        return HEALTH

    async def modules_status(self) -> dict[str, Any]:
        return MODULES

    async def match_games(self) -> list[dict[str, Any]]:
        return GAMES

    async def cloud_status(self) -> dict[str, Any]:
        return {
            "store": "onedrive",
            "name": "OneDrive",
            "problem": None,
            "onedriveSignedIn": True,
            "googleSignedIn": False,
            "methods": {"onedrive": {"browser": True, "phone": True}, "gdrive": {"browser": True, "phone": True}},
        }

    async def get_settings(self) -> dict[str, Any]:
        return {
            "deviceName": "Living room PC",
            "updateChannel": "stable",
            "idleSyncMinutes": 30,
            "toastOnSync": True,
            "gateMaxRemovedPercent": 50,
            "gateMaxSizeDropPercent": 70,
            "readOnly": False,
        }

    async def ludusavi_import_status(self) -> dict[str, Any]:
        return {"running": False, "done": 3, "total": 3, "current": None, "summary": {"imported": 3}}

    async def check_for_updates(self, force: bool = False) -> dict[str, Any]:
        return {
            "current": "1.0.0",
            "updateAvailable": True,
            "error": None,
            "latest": {"tag": "v1.1.0", "version": "1.1.0", "prerelease": False, "desktop_url": "https://github.com/x"},
        }

    async def get_status(self) -> dict[str, Any]:
        return {"ok": True}


class ClosedEvents(pc_host.Events):
    """Ends each event stream at once. A stream that stays open would stop the browser's
    virtual clock, and the screenshot would never be taken."""

    def wait(self, queue: list[tuple[str, Any]], timeout: float) -> list[tuple[str, Any]]:
        raise OSError("closed for screenshots")


class SampleControl:
    async def pc_update_status(self) -> dict[str, Any]:
        return {"installed": True, "running": "1.0.0", "current": "1.0.0", "previous": "0.26.0", "busy": None}


def find_browser() -> str:
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for name in ("chromium", "chromium-browser", "google-chrome", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise SystemExit("no Edge or Chromium found for the screenshots")


def start(app: Any = None) -> tuple[pc_host.Api, Any, asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    api = pc_host.Api(
        app or SampleApp(),
        loop,
        "docs-screenshots-synthetic-token",
        ClosedEvents(),
        pc_host.PLACEHOLDER,
        os.path.join(ROOT, "desktop"),
    )
    api.control = SampleControl()  # type: ignore[assignment]
    return api, pc_host.serve(api, port=0), loop


def capture(out_dir: str, browser: str | None = None) -> list[str]:
    if not os.path.isfile(os.path.join(ROOT, "desktop", "dist", "main.js")):
        raise SystemExit("build the desktop interface first: npx -y pnpm@9.15.9 run build:desktop")
    browser = browser or find_browser()
    os.makedirs(out_dir, exist_ok=True)
    api, server, loop = start()
    written = []
    os.makedirs(os.path.join(ROOT, "tmp"), exist_ok=True)
    profile = tempfile.mkdtemp(prefix="keepsake-shots-", dir=os.path.join(ROOT, "tmp"))
    try:
        for page in PAGES:
            target = os.path.join(out_dir, f"desktop-{page}.png")
            url = f"http://127.0.0.1:{api.port}/#token={api.token}&page={page}"
            subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-first-run",
                    "--hide-scrollbars",
                    "--force-prefers-color-scheme=light",
                    "--virtual-time-budget=5000",
                    f"--user-data-dir={profile}",
                    f"--window-size={SIZE}",
                    f"--screenshot={target}",
                    url,
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            written.append(target)
    finally:
        server.shutdown()
        server.server_close()
        loop.call_soon_threadsafe(loop.stop)
        shutil.rmtree(profile, ignore_errors=True)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "user", "images"))
    options = parser.parse_args(argv)
    for path in capture(options.out):
        print(os.path.relpath(path, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
