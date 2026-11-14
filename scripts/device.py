"""Shared SSH settings for scripts that talk to a development device.

Reads ``deploy.local.json`` (git-ignored) from the repository root:

    {"host": "192.168.1.50", "user": "deck", "port": 22}
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "deploy.local.json")


def load_target(path: str = CONFIG) -> tuple[str, str]:
    """Return ``(user@host, port)``. Exits with a hint if the file is missing."""
    try:
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
    except FileNotFoundError:
        sys.exit(f"Create {os.path.basename(path)} first, see docs/dev-setup.md")
    return f"{config.get('user', 'deck')}@{config['host']}", str(config.get("port", 22))
