"""In-plugin updates from GitHub Releases (build prompt section 12, ADR-0002).

The backend checks releases, verifies a release has a zip and a
``SHA256SUMS`` entry for it, and returns the arguments for Decky's own
installer. The frontend hands those to Decky, which shows its confirmation,
checks the SHA-256 and replaces the plugin. The backend never installs
anything itself.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from . import minisign, release_key
from .fsutil import atomic_write_json, read_json
from .net import Fetcher, NetError, check_url

REPO = "breakmylegs/keepsake"
PLUGIN_NAME = "Keepsake"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
STATE_FILE = "update-state.json"
CHECK_INTERVAL = 24 * 60 * 60
SUMS_NAME = "SHA256SUMS"
SUMS_MAX_BYTES = 64 * 1024
CHANNELS = ("stable", "prerelease")

# Decky's InstallType enum (frontend/src/plugin.ts).
INSTALL_TYPE = {"install": 0, "reinstall": 1, "update": 2, "downgrade": 3}

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

VersionKey = tuple[int, int, int, int, int]


def parse_version(text: str) -> VersionKey | None:
    """Return a sortable key. A release sorts above its betas."""
    match = _VERSION.match(text.strip())
    if not match:
        return None
    major, minor, patch, beta = match.groups()
    if beta is None:
        return (int(major), int(minor), int(patch), 1, 0)
    return (int(major), int(minor), int(patch), 0, int(beta))


@dataclass(frozen=True)
class Release:
    tag: str
    version: str
    prerelease: bool
    published: str
    notes: str
    zip_name: str
    zip_url: str | None
    sums_url: str | None
    signature_url: str | None
    desktop_url: str | None = None  # Keepsake-desktop-v<version>.zip, the PC package (ADR-0042)
    helper_url: str | None = None  # Keepsake-helper-v<version>.zip, the root helper (ADR-0083)

    @property
    def key(self) -> VersionKey:
        key = parse_version(self.version)
        assert key is not None
        return key

    @property
    def complete(self) -> bool:
        return bool(self.zip_url and self.sums_url)

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data["complete"] = self.complete
        return data


def parse_releases(payload: Any) -> list[Release]:
    """Turn the GitHub releases API response into releases, newest first."""
    releases: list[Release] = []
    if not isinstance(payload, list):
        return releases
    for item in payload:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        tag = str(item.get("tag_name", ""))
        key = parse_version(tag)
        if key is None or not tag.startswith("v"):
            continue
        version = tag[1:]
        zip_name = f"{PLUGIN_NAME}-v{version}.zip"
        assets = {
            str(a.get("name")): str(a.get("browser_download_url"))
            for a in item.get("assets", [])
            if isinstance(a, dict) and a.get("browser_download_url")
        }
        releases.append(
            Release(
                tag=tag,
                version=version,
                prerelease=bool(item.get("prerelease")) or key[3] == 0,
                published=str(item.get("published_at") or ""),
                notes=str(item.get("body") or "")[:20000],
                zip_name=zip_name,
                zip_url=assets.get(zip_name),
                sums_url=assets.get(SUMS_NAME),
                signature_url=assets.get(SUMS_NAME + ".minisig"),
                desktop_url=assets.get(desktop_zip_name(version)),
                helper_url=assets.get(helper_zip_name(version)),
            )
        )
    releases.sort(key=lambda r: r.key, reverse=True)
    return releases


def desktop_zip_name(version: str) -> str:
    return f"{PLUGIN_NAME}-desktop-v{version}.zip"


HELPER_NAME = "Keepsake Helper"


def helper_zip_name(version: str) -> str:
    return f"{PLUGIN_NAME}-helper-v{version}.zip"


def parse_sums(text: str) -> dict[str, str]:
    """Parse ``sha256sum`` output: ``<hex>  <name>`` or ``<hex> *<name>``."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts[0].lower(), parts[1].lstrip("*").strip()
        if _HEX64.match(digest) and name:
            out[name] = digest
    return out


def select_latest(releases: list[Release], channel: str) -> Release | None:
    for release in releases:
        if release.complete and (channel == "prerelease" or not release.prerelease):
            return release
    return None


class Updater:
    def __init__(
        self,
        runtime_dir: str,
        current_version: str,
        fetch: Fetcher,
        clock: Callable[[], float] = time.time,
        public_key: str = release_key.PUBLIC_KEY,
    ) -> None:
        self._path = os.path.join(runtime_dir, STATE_FILE)
        self.current_version = current_version
        self._fetch = fetch
        self._clock = clock
        self.public_key = public_key.strip()

    # State

    def _state(self) -> dict[str, Any]:
        try:
            state = read_json(self._path, default={})
        except (OSError, ValueError):
            state = {}
        return state if isinstance(state, dict) else {}

    def _save(self, state: dict[str, Any]) -> None:
        atomic_write_json(self._path, state)

    # Checking

    def check(self, channel: str, force: bool = False) -> dict[str, Any]:
        """Return update status. Hits GitHub at most once a day unless ``force``."""
        if channel not in CHANNELS:
            channel = "stable"
        state = self._state()
        now = self._clock()
        error: str | None = None
        last_check = float(state.get("lastCheck", 0) or 0)
        if force or now - last_check >= CHECK_INTERVAL or "releases" not in state:
            error = self._refresh(state, now)
        releases = parse_releases(state.get("releases", []))
        latest = select_latest(releases, channel)
        current_key = parse_version(self.current_version)
        available = bool(latest and current_key and latest.key > current_key)
        notify = False
        if available and latest and state.get("notifiedVersion") != latest.version:
            state["notifiedVersion"] = latest.version
            notify = True
        self._save(state)
        return {
            "current": self.current_version,
            "channel": channel,
            "latest": latest.public() if latest else None,
            "updateAvailable": available,
            "notify": notify,
            "releases": [r.public() for r in releases],
            "lastCheck": state.get("lastCheck"),
            "error": error,
        }

    def _refresh(self, state: dict[str, Any], now: float) -> str | None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if state.get("etag") and "releases" in state:
            headers["If-None-Match"] = str(state["etag"])
        try:
            response = self._fetch(RELEASES_URL, headers=headers)
        except NetError:
            return "offline"
        if response.status == 304:
            state["lastCheck"] = now
            return None
        if response.status in (403, 429):
            # Rate limited: keep the cache and try again tomorrow, quietly.
            state["lastCheck"] = now
            return "rate-limited"
        if response.status != 200:
            return f"http-{response.status}"
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except ValueError:
            return "bad-response"
        state["releases"] = _compact(payload)
        state["etag"] = response.headers.get("etag")
        state["lastCheck"] = now
        return None

    # Preparing the hand-off

    def prepare(self, tag: str, busy_reason: str | None) -> dict[str, Any]:
        """Verify ``tag`` and return the arguments for Decky's installer.

        Refuses while a sync job or game session is running, and whenever the
        release lacks a zip or a ``SHA256SUMS`` entry for it.
        """
        if busy_reason:
            return {"ok": False, "reason": "busy", "detail": busy_reason}
        releases = parse_releases(self._state().get("releases", []))
        release = next((r for r in releases if r.tag == tag), None)
        if release is None:
            return {"ok": False, "reason": "unknown-release"}
        if not release.complete or release.zip_url is None or release.sums_url is None:
            return {"ok": False, "reason": "incomplete-release"}
        try:
            check_url(release.zip_url)
            check_url(release.sums_url)
        except NetError:
            return {"ok": False, "reason": "disallowed-host"}
        try:
            response = self._fetch(release.sums_url, headers={"Accept": "application/octet-stream"})
        except NetError as exc:
            return {"ok": False, "reason": "offline", "detail": str(exc)}
        if response.status != 200 or len(response.body) > SUMS_MAX_BYTES:
            return {"ok": False, "reason": "sums-unavailable"}
        if self.public_key:
            refused = self._check_signature(release, response.body)
            if refused:
                return refused
        digest = parse_sums(response.body.decode("utf-8", errors="replace")).get(release.zip_name)
        if digest is None:
            return {"ok": False, "reason": "sums-missing-zip"}
        return {
            "signed": bool(self.public_key),
            "ok": True,
            "artifact": release.zip_url,
            "name": PLUGIN_NAME,
            # "dev" stops Decky reporting the install to its store server (ADR-0002).
            "version": "dev",
            "displayVersion": release.version,
            "sha256": digest,
            "installType": self.install_type(release.version),
        }

    def prepare_desktop(self, tag: str) -> dict[str, Any]:
        """Verify the PC package of ``tag`` (ADR-0042): its ``SHA256SUMS`` entry, under the release signature.

        Returns the address and SHA-256 to download and check; the PC self-update installs it.
        """
        releases = parse_releases(self._state().get("releases", []))
        release = next((r for r in releases if r.tag == tag), None)
        if release is None:
            return {"ok": False, "reason": "unknown-release"}
        if not release.desktop_url or not release.sums_url:
            return {"ok": False, "reason": "no-pc-package"}
        try:
            check_url(release.desktop_url)
            check_url(release.sums_url)
            response = self._fetch(release.sums_url, headers={"Accept": "application/octet-stream"})
        except NetError as exc:
            return {"ok": False, "reason": "offline", "detail": str(exc)}
        if response.status != 200 or len(response.body) > SUMS_MAX_BYTES:
            return {"ok": False, "reason": "sums-unavailable"}
        if self.public_key:
            refused = self._check_signature(release, response.body)
            if refused:
                return refused
        name = desktop_zip_name(release.version)
        digest = parse_sums(response.body.decode("utf-8", errors="replace")).get(name)
        if digest is None:
            return {"ok": False, "reason": "sums-missing-zip"}
        return {
            "ok": True,
            "signed": bool(self.public_key),
            "url": release.desktop_url,
            "name": name,
            "version": release.version,
            "sha256": digest,
        }

    def prepare_helper(self, tag: str, installed: bool) -> dict[str, Any]:
        """Verify the root helper of ``tag`` (ADR-0083) under the release signature, for Decky's installer.

        The helper is version-locked to Keepsake, so ``tag`` is always Keepsake's own release. A
        release without a signature, or without the helper in its ``SHA256SUMS``, is refused.
        """
        releases = parse_releases(self._state().get("releases", []))
        release = next((r for r in releases if r.tag == tag), None)
        if release is None:
            return {"ok": False, "reason": "unknown-release"}
        if not release.helper_url or not release.sums_url:
            return {"ok": False, "reason": "no-helper"}
        if not self.public_key:
            return {"ok": False, "reason": "unsigned-release"}  # root code is never installed unsigned
        try:
            check_url(release.helper_url)
            check_url(release.sums_url)
            response = self._fetch(release.sums_url, headers={"Accept": "application/octet-stream"})
        except NetError as exc:
            return {"ok": False, "reason": "offline", "detail": str(exc)}
        if response.status != 200 or len(response.body) > SUMS_MAX_BYTES:
            return {"ok": False, "reason": "sums-unavailable"}
        refused = self._check_signature(release, response.body)
        if refused:
            return refused
        digest = parse_sums(response.body.decode("utf-8", errors="replace")).get(helper_zip_name(release.version))
        if digest is None:
            return {"ok": False, "reason": "sums-missing-zip"}
        return {
            "ok": True,
            "signed": True,
            "artifact": release.helper_url,
            "name": HELPER_NAME,
            "version": "dev",
            "displayVersion": release.version,
            "sha256": digest,
            "installType": INSTALL_TYPE["update"] if installed else INSTALL_TYPE["install"],
        }

    def _check_signature(self, release: Release, sums: bytes) -> dict[str, Any] | None:
        """With a pinned key, ``SHA256SUMS`` must carry a valid minisign signature (T10). None means valid."""
        if not release.signature_url:
            return {"ok": False, "reason": "unsigned-release"}
        try:
            check_url(release.signature_url)
            response = self._fetch(release.signature_url, headers={"Accept": "application/octet-stream"})
        except NetError as exc:
            return {"ok": False, "reason": "offline", "detail": str(exc)}
        if response.status != 200 or len(response.body) > minisign.MAX_SIGNATURE_BYTES:
            return {"ok": False, "reason": "signature-unavailable"}
        try:
            minisign.verify(self.public_key, response.body.decode("utf-8", errors="replace"), sums)
        except minisign.MinisignError as exc:
            return {"ok": False, "reason": "bad-signature", "detail": str(exc)}
        return None

    def install_type(self, version: str) -> int:
        current, target = parse_version(self.current_version), parse_version(version)
        if current is None or target is None:
            return INSTALL_TYPE["install"]
        if target > current:
            return INSTALL_TYPE["update"]
        if target < current:
            return INSTALL_TYPE["downgrade"]
        return INSTALL_TYPE["reinstall"]


def _compact(payload: Any) -> list[dict[str, Any]]:
    """Keep only the fields we use, so the cache stays small."""
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload[:30]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "tag_name": item.get("tag_name"),
                "draft": item.get("draft"),
                "prerelease": item.get("prerelease"),
                "published_at": item.get("published_at"),
                "body": str(item.get("body") or "")[:20000],
                "assets": [
                    {"name": a.get("name"), "browser_download_url": a.get("browser_download_url")}
                    for a in item.get("assets", [])
                    if isinstance(a, dict)
                ],
            }
        )
    return out


def startup_notice(runtime_dir: str, current_version: str) -> dict[str, Any] | None:
    """Record the running version; return ``{from, to}`` once after it changes."""
    path = os.path.join(runtime_dir, "last-version.json")
    try:
        previous = read_json(path, default={})
    except (OSError, ValueError):
        previous = {}
    previous_version = previous.get("version") if isinstance(previous, dict) else None
    atomic_write_json(path, {"version": current_version})
    if previous_version and previous_version != current_version:
        return {"from": previous_version, "to": current_version}
    return None
