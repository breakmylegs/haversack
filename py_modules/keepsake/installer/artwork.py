"""SteamGridDB artwork with the user's own key (v2 spec 6.2 and 8.3, slice 22, ADR-0027).

The API is ``www.steamgriddb.com`` (allowlisted, only with a user key). The
images themselves are served from ``cdn2.steamgriddb.com``, which is **not** on
the allowlist: adding it is an escalation item, so downloads stay off until the
owner approves it (``IMAGE_HOST_APPROVED``). The key is sent only to the API
host, never to the image host, and never logged or returned to the frontend.

Images are checked by their first bytes (PNG or JPEG only, which is all
``SetCustomArtworkForApp`` accepts) and capped in size before they are staged.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from .. import net

API_HOST = "www.steamgriddb.com"
API = f"https://{API_HOST}/api/v2"
IMAGE_HOSTS = frozenset({"cdn2.steamgriddb.com"})
# Escalation (CLAUDE.md section 4): the image host is outside the allowlist until Peter approves it.
IMAGE_HOST_APPROVED = False
MAX_IMAGE_BYTES = 8 * 1024 * 1024
KEY = re.compile(r"^[A-Za-z0-9]{16,64}$")
# Steam's ELibraryAssetType (verified in @decky/ui 4.16.5 App.d.ts) and the SteamGridDB query for each.
ASSETS: tuple[tuple[int, str, str], ...] = (
    (0, "capsule", "grids/game/{id}?dimensions=600x900&mimes=image/png,image/jpeg"),
    (3, "header", "grids/game/{id}?dimensions=460x215,920x430&mimes=image/png,image/jpeg"),
    (1, "hero", "heroes/game/{id}?mimes=image/png,image/jpeg"),
    (2, "logo", "logos/game/{id}?mimes=image/png"),
)


class ArtworkError(ValueError):
    pass


def available() -> bool:
    return IMAGE_HOST_APPROVED


def image_type(head: bytes) -> str:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    raise ArtworkError("SteamGridDB sent something that is not a PNG or JPEG image")


class SteamGridDB:
    def __init__(
        self,
        key: Callable[[], str],
        fetch: net.Fetcher = net.fetch,
        fetch_to_file: Callable[..., net.HttpResponse] = net.fetch_to_file,
    ) -> None:
        self._key = key
        self._fetch = fetch
        self._fetch_to_file = fetch_to_file

    def _api(self, path: str) -> Any:
        key = self._key()
        if not KEY.match(key or ""):
            raise ArtworkError("add your SteamGridDB API key first")
        response = self._fetch(
            f"{API}/{path}", headers={"Authorization": f"Bearer {key}"}, allowed=frozenset({API_HOST})
        )
        if response.status == 401:
            raise ArtworkError("SteamGridDB did not accept the API key")
        if response.status != 200:
            raise ArtworkError(f"SteamGridDB answered {response.status}")
        try:
            body = json.loads(response.body)
        except ValueError as exc:
            raise ArtworkError("SteamGridDB sent an answer Keepsake cannot read") from exc
        if not isinstance(body, dict) or not body.get("success") or not isinstance(body.get("data"), list):
            raise ArtworkError("SteamGridDB sent an answer Keepsake cannot read")
        return body["data"]

    def search(self, title: str) -> list[dict[str, Any]]:
        out = []
        for item in self._api("search/autocomplete/" + quote(title.strip()[:80], safe=""))[:8]:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                out.append(
                    {"id": item["id"], "name": str(item.get("name", "")), "verified": bool(item.get("verified"))}
                )
        return out

    def choose(self, game_id: int) -> list[dict[str, Any]]:
        """The top-scored image of each kind SteamGridDB has for ``game_id``."""
        chosen = []
        for asset_type, label, query in ASSETS:
            for item in self._api(query.format(id=int(game_id))):
                url = item.get("url") if isinstance(item, dict) else None
                if isinstance(url, str):
                    net.check_url(url, IMAGE_HOSTS)
                    chosen.append({"assetType": asset_type, "label": label, "url": url})
                    break
        return chosen

    def download(self, url: str, dest: str) -> str:
        """Stage one image; returns ``png`` or ``jpg``. The API key is never sent here."""
        if not available():
            raise ArtworkError("artwork downloads wait for the owner's approval of the SteamGridDB image host")
        net.check_url(url, IMAGE_HOSTS)
        response = self._fetch_to_file(url, dest, max_bytes=MAX_IMAGE_BYTES, allowed=IMAGE_HOSTS)
        try:
            if response.status != 200:
                raise ArtworkError(f"SteamGridDB's image host answered {response.status}")
            with open(dest, "rb") as handle:
                return image_type(handle.read(8))
        except ArtworkError:
            if os.path.exists(dest):
                os.unlink(dest)
            raise
