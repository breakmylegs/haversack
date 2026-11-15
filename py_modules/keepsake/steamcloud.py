"""Steam Cloud detection for Steam apps (build prompt slice 11).

Steam keeps per-user, per-app cloud state under ``userdata/<id3>/<appid>``:
``remotecache.vdf`` lists the files Steam Cloud tracks and ``remote/`` holds
them. Either one means the game uses Steam Cloud, so Keepsake can leave it
alone. A game that has been played with neither has no Steam Cloud saves and
is a candidate for Keepsake. A game never played is unknown. Read-only.
"""

from __future__ import annotations

import os

CLOUD = "cloud"
NO_CLOUD = "no-cloud"
UNKNOWN = "unknown"


def cloud_state(steam_root: str | None, user_id3: str | None, appid: int, last_played: int) -> str:
    if not steam_root or not user_id3 or not str(user_id3).isdigit():
        return UNKNOWN
    base = os.path.join(steam_root, "userdata", str(user_id3), str(int(appid)))
    if os.path.isfile(os.path.join(base, "remotecache.vdf")):
        return CLOUD
    remote = os.path.join(base, "remote")
    try:
        if os.path.isdir(remote) and any(os.scandir(remote)):
            return CLOUD
    except OSError:
        return UNKNOWN
    return NO_CLOUD if last_played else UNKNOWN
