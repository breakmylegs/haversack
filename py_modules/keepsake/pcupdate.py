"""PC self-update (ADR-0043, second part of P5).

There is no Decky installer on a PC, so the host updates itself, with the same
checks as the plugin:

1. the release's ``SHA256SUMS`` must carry a valid signature from the pinned key
   (``Updater.prepare_desktop``, ADR-0036);
2. the downloaded ``Keepsake-desktop-v<version>.zip`` must match its line;
3. the zip is unpacked member by member into a staging folder: every name must sit
   under ``Keepsake-desktop/``, with no ``..``, absolute path or drive, and within
   size and count limits;
4. its ``VERSION`` must be the version the signed release names;
5. ``pcinstall.install`` puts it in a new version folder and switches ``current.json``,
   keeping the previous version for a rollback. Start-up entries are left as the user set them.

The running host keeps running the old version until it restarts.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from typing import Any

from . import net, pcinstall
from .fsutil import atomic_write_json

MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_UNPACKED = 256 * 1024 * 1024
MAX_MEMBERS = 5000
ROOT_FOLDER = "Keepsake-desktop/"

Downloader = Callable[[str, str], None]


class UpdateError(Exception):
    pass


def download(url: str, dest: str) -> None:
    """GitHub release asset download (allowlisted, redirects checked), capped."""
    try:
        response = net.fetch_to_file(url, dest, timeout=120.0, max_bytes=MAX_DOWNLOAD)
    except net.NetError as exc:
        raise UpdateError(f"the update could not be downloaded: {exc}") from exc
    if response.status != 200:
        raise UpdateError(f"the update download answered HTTP {response.status}")


def safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Every member, checked: under the package folder, no escapes, within the limits."""
    members = archive.infolist()
    if len(members) > MAX_MEMBERS:
        raise UpdateError("the update has too many files")
    total = 0
    for info in members:
        name = info.filename
        parts = name.split("/")
        if (
            not name.startswith(ROOT_FOLDER)
            or "\\" in name
            or ":" in name
            or name.startswith("/")
            or any(p in ("..", ".") for p in parts)
            or "\x00" in name
        ):
            raise UpdateError("the update holds a file outside its folder; refused")
        total += info.file_size
        if total > MAX_UNPACKED:
            raise UpdateError("the update is larger than expected; refused")
    return members


def unpack(zip_path: str, dest: str) -> str:
    """Unpack into ``dest``; return the package folder inside it."""
    with zipfile.ZipFile(zip_path) as archive:
        for info in safe_members(archive):
            target = os.path.join(dest, *info.filename.split("/"))
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as out:
                shutil.copyfileobj(source, out)
    return os.path.join(dest, ROOT_FOLDER.rstrip("/"))


def apply(
    prepared: dict[str, Any], host: str, fetch: Downloader = download, env: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Download, verify and install the PC package that ``Updater.prepare_desktop`` approved."""
    if not prepared.get("ok"):
        raise UpdateError(f"the update was not verified ({prepared.get('reason')})")
    with tempfile.TemporaryDirectory(prefix="keepsake-update-") as scratch:
        zip_path = os.path.join(scratch, "package.zip")
        fetch(str(prepared["url"]), zip_path)
        digest = hashlib.sha256()
        with open(zip_path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != prepared["sha256"]:
            raise UpdateError("the downloaded update does not match the signed checksum; refused")
        try:
            package_dir = unpack(zip_path, os.path.join(scratch, "unpacked"))
        except (OSError, zipfile.BadZipFile) as exc:
            raise UpdateError(f"the update could not be unpacked: {exc}") from exc
        try:
            version = pcinstall.package_version(package_dir)
        except pcinstall.InstallError as exc:
            raise UpdateError(str(exc)) from exc
        if version != prepared["version"]:
            raise UpdateError("the update's version does not match the signed release; refused")
        try:
            result = pcinstall.install(package_dir, host, env=env, entries=False)
        except (pcinstall.InstallError, OSError) as exc:
            raise UpdateError(f"the update could not be installed: {exc}") from exc
    return {"ok": True, "version": result["version"], "restart": True}


def rollback(host: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Switch back to the previous installed version (kept by every install)."""
    root = pcinstall.app_root(host, env)
    current = pcinstall.installed(host, env)
    previous = current.get("previous")
    if not previous or not os.path.isfile(os.path.join(root, str(previous), "VERSION")):
        raise UpdateError("there is no previous version to go back to")
    atomic_write_json(os.path.join(root, pcinstall.CURRENT), {"version": previous, "previous": current.get("version")})
    return {"ok": True, "version": previous, "restart": True}
