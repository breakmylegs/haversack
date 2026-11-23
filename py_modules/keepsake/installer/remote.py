"""Install from a network location that is not mounted: HTTP and HTTPS (ADR-0033).

Only the host the user typed is contacted, and only after a user action. HTTPS
may go to any host. Plain HTTP only to a private, loopback or link-local
address, and never with a password. Redirects are followed here, not by
``urllib``: same host and scheme only, never from HTTPS to HTTP, and another
host only once the user confirms it. Credentials never go to another host.

Downloads stream into the Installer's staging folder as ``<name>.part``. They
resume with ``Range`` after a dropped connection, are checked against
``Content-Length`` and an optional SHA-256, and are renamed when complete.
Runs in worker threads.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import os
import re
import shutil
import socket
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from .. import net
from ..fsutil import atomic_write_json, read_json

MAX_FILE = 128 * 1024**3
SPACE_MARGIN = 2 * 1024**3
LISTING_MAX = 2 * 1024 * 1024
LISTING_ENTRIES = 5000
MAX_REDIRECTS = 5
MAX_RESUMES = 5
CONNECT_TIMEOUT = 20.0
READ_TIMEOUT = 60.0
CHUNK = 1024 * 1024
URL_MAX = 2000
# Where plain HTTP is allowed: RFC 1918, shared address space (Tailscale and similar), loopback,
# link-local and IPv6 unique local addresses. Python's is_private also counts documentation ranges.
LOCAL_NETWORKS = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "::1/128",
    "fe80::/10",
    "fc00::/7",
)
_HREF = re.compile(r"""<a\s[^>]*?href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
_NAME = re.compile(r'^[^/\\\x00-\x1f"<>|:*?]{1,200}$')
_CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+|\*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RemoteError(Exception):
    """A download or listing failed; the message is shown to the user."""


class RedirectElsewhere(RemoteError):
    """The server sent the request to another host. The user may allow that host once."""

    def __init__(self, host: str) -> None:
        super().__init__(f"the server sent you to {host}; allow that host to carry on")
        self.host = host


class Cancelled(RemoteError):
    pass


def check_location(url: str) -> str:
    """A folder or file address the user typed: http or https, a host, nothing hidden in it."""
    url = str(url).strip()
    if not url or len(url) > URL_MAX or any(ord(c) < 32 or c == "\x7f" for c in url):
        raise RemoteError("enter an address such as https://nas.local/games/")
    try:
        parts = urlsplit(url)
    except ValueError as exc:  # for example a malformed [IPv6] address
        raise RemoteError("that address is not valid") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RemoteError("the address starts with http:// or https:// and names a server")
    if parts.username or parts.password:
        raise RemoteError("enter the user name and password in their own fields, not in the address")
    if parts.query or parts.fragment:
        raise RemoteError("enter the address without ? or #")
    try:
        parts.port  # noqa: B018 (raises on a bad port)
    except ValueError as exc:
        raise RemoteError("the port in the address is not a number from 1 to 65535") from exc
    return url


def check_sha256(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    if not value:
        return None
    if not _SHA256.match(value):
        raise RemoteError("a SHA-256 checksum is 64 letters a to f and digits")
    return value


Resolver = Callable[[str], Iterable[str]]


def _resolve(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


def host_is_private(host: str, resolve: Resolver = _resolve) -> bool:
    """True when every address of ``host`` is private, loopback or link-local (plain HTTP is allowed there)."""
    try:
        import ipaddress  # lazy: not proven in Decky's frozen Python (ADR-0030); missing means "not private"
    except ImportError:
        return False
    host = host.strip("[]")
    try:
        addresses = [host] if _is_ip(ipaddress, host) else list(resolve(host))
    except (OSError, UnicodeError, ValueError):
        return False
    if not addresses:
        return False
    for text in addresses:
        try:
            address = ipaddress.ip_address(text.split("%")[0])
        except ValueError:
            return False
        networks = [ipaddress.ip_network(n) for n in LOCAL_NETWORKS]
        if not any(address.version == n.version and address in n for n in networks):
            return False
    return True


def _is_ip(ipaddress: Any, host: str) -> bool:
    try:
        ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    return True


Connector = Callable[[str, str, int], http.client.HTTPConnection]


def _connect(scheme: str, host: str, port: int) -> http.client.HTTPConnection:
    conn: http.client.HTTPConnection
    if scheme == "https":
        conn = http.client.HTTPSConnection(host, port, timeout=CONNECT_TIMEOUT, context=net.ssl_context())
    else:
        conn = http.client.HTTPConnection(host, port, timeout=CONNECT_TIMEOUT)
    conn.connect()
    if conn.sock is not None:
        conn.sock.settimeout(READ_TIMEOUT)
    return conn


@dataclass
class Session:
    """One user action against one location: its host, credentials and any host the user allowed."""

    url: str
    username: str = ""
    password: str = ""
    allowed: set[str] = field(default_factory=set)
    connect: Connector = _connect
    resolve: Resolver = _resolve

    def __post_init__(self) -> None:
        self.url = check_location(self.url)
        self.home = (urlsplit(self.url).hostname or "").lower()
        self.allowed = {h.lower() for h in self.allowed} | {self.home}
        if self.password and urlsplit(self.url).scheme != "https":
            raise RemoteError("a password is only sent over https://; change the address to https")

    def _check_hop(self, url: str) -> None:
        try:
            parts = urlsplit(url)
            parts.port  # noqa: B018 (raises on a bad port)
        except ValueError as exc:
            raise RemoteError("the server sent an address Haversack cannot use") from exc
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            raise RemoteError("the server sent an address Haversack cannot use")
        if host not in self.allowed:
            raise RedirectElsewhere(host)
        if parts.scheme == "http" and not host_is_private(host, self.resolve):
            raise RemoteError(f"{host} is not on your local network, so Haversack only connects to it with https://")

    def open(
        self, url: str, headers: dict[str, str] | None = None, method: str = "GET", body: bytes | None = None
    ) -> tuple[http.client.HTTPResponse, str]:
        """GET ``url`` (or a WebDAV ``PROPFIND``), following permitted redirects.

        Returns the response and the final address.
        """
        if method not in ("GET", "PROPFIND"):
            raise RemoteError("Haversack only reads from network locations")
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            self._check_hop(current)
            parts = urlsplit(current)
            host = (parts.hostname or "").lower()
            port = parts.port or (443 if parts.scheme == "https" else 80)
            send = {"User-Agent": net.USER_AGENT, "Accept-Encoding": "identity", **(headers or {})}
            if self.username and parts.scheme == "https" and host == self.home:
                token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
                send["Authorization"] = f"Basic {token}"
            target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
            try:
                conn = self.connect(parts.scheme, parts.hostname or host, port)
                conn.request(method, target, body=body, headers=send)
                response = conn.getresponse()
            except (OSError, http.client.HTTPException) as exc:
                raise RemoteError(f"could not reach {host}: {type(exc).__name__}") from exc
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location") or ""
                response.close()
                conn.close()
                if not location:
                    raise RemoteError("the server sent a redirect without an address")
                try:
                    following = urljoin(current, location)
                    scheme = urlsplit(following).scheme
                except ValueError as exc:
                    raise RemoteError("the server sent a redirect Haversack cannot use") from exc
                if scheme not in ("http", "https"):
                    raise RemoteError("the server sent a redirect Haversack cannot use")
                if parts.scheme == "https" and scheme != "https":
                    raise RemoteError("the server tried to move you from https:// to plain http://; Haversack refused")
                current = following
                continue
            return response, current
        raise RemoteError("the server redirected too many times")


def _status_error(status: int) -> RemoteError:
    if status in (401, 403):
        return RemoteError("the server refused the user name or password (or needs one)")
    if status == 404:
        return RemoteError("nothing was found at that address")
    if status == 416:
        return RemoteError("the server could not resume the download")
    return RemoteError(f"the server answered {status}")


def list_folder(session: Session, url: str) -> list[dict[str, Any]]:
    """Folders and ISO files one level below ``url``, read from the server's listing page."""
    if not url.endswith("/"):
        url += "/"
    response, final = session.open(url)
    try:
        if response.status != 200:
            raise _status_error(response.status)
        body = response.read(LISTING_MAX + 1)
    except (OSError, http.client.HTTPException) as exc:
        raise RemoteError(f"the listing could not be read: {type(exc).__name__}") from exc
    finally:
        response.close()
    if len(body) > LISTING_MAX:
        raise RemoteError("the listing page is too large")
    return parse_listing(body.decode("utf-8", errors="replace"), final)


def parse_listing(page: str, base: str) -> list[dict[str, Any]]:
    base_parts = urlsplit(base)
    base_path = base_parts.path if base_parts.path.endswith("/") else base_parts.path.rsplit("/", 1)[0] + "/"
    seen: dict[str, dict[str, Any]] = {}
    for match in _HREF.finditer(page):
        if len(seen) >= LISTING_ENTRIES:
            break
        href = (match.group(1) or match.group(2) or match.group(3) or "").strip()
        href = href.replace("&amp;", "&")
        if not href or href.startswith(("#", "?", "javascript:", "mailto:")):
            continue
        try:
            target = urlsplit(urljoin(base, href))
        except ValueError:
            continue
        if (target.scheme, target.netloc) != (base_parts.scheme, base_parts.netloc) or target.query:
            continue
        if not target.path.startswith(base_path):
            continue
        rest = target.path[len(base_path) :]
        folder = rest.endswith("/")
        name = unquote(rest[:-1] if folder else rest)
        if not _NAME.match(name) or name in (".", ".."):  # _NAME has no "/": one level down only
            continue
        if not folder and not name.lower().endswith(".iso"):
            continue
        url = f"{base_parts.scheme}://{base_parts.netloc}{target.path}"
        seen.setdefault(url, {"name": name, "url": url, "kind": "folder" if folder else "iso"})
    return sorted(seen.values(), key=lambda e: (e["kind"] != "folder", e["name"].casefold()))


def file_name(url: str) -> str:
    name = unquote(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])
    if not _NAME.match(name) or name.startswith(".") or not name.lower().endswith(".iso"):
        raise RemoteError("choose an .iso file")
    return name


Progress = Callable[[int, int | None], None]


def download(
    session: Session,
    url: str,
    dest_dir: str,
    *,
    sha256: str | None = None,
    progress: Progress = lambda done, total: None,
    cancelled: Callable[[], bool] = lambda: False,
    free_space: Callable[[str], int] = lambda path: shutil.disk_usage(path).free,
    max_file: int = MAX_FILE,
) -> str:
    """Download one ISO into ``dest_dir``; returns its path. A partial file is deleted on failure or cancel."""
    name = file_name(url)
    expected = check_sha256(sha256)
    os.makedirs(dest_dir, exist_ok=True)
    final = os.path.join(dest_dir, name)
    part = final + ".part"
    try:
        _fetch(session, url, part, expected, progress, cancelled, free_space, max_file)
    except BaseException:
        _remove(part)
        raise
    os.replace(part, final)
    return final


def _fetch(
    session: Session,
    url: str,
    part: str,
    expected: str | None,
    progress: Progress,
    cancelled: Callable[[], bool],
    free_space: Callable[[str], int],
    max_file: int,
) -> None:
    folder = os.path.dirname(part)
    digest = hashlib.sha256()
    done = 0
    total: int | None = None
    resumes = 0
    with open(part, "wb") as out:
        while True:
            headers = {"Range": f"bytes={done}-"} if done else {}
            response, _ = session.open(url, headers)
            try:
                if response.status == 200 and done:
                    out.seek(0)  # the server ignored Range: start again
                    out.truncate()
                    digest, done = hashlib.sha256(), 0
                elif response.status == 206 and done:
                    match = _CONTENT_RANGE.match(response.getheader("Content-Range") or "")
                    if not match or int(match.group(1)) != done:
                        raise RemoteError("the server resumed from the wrong place")
                elif response.status != 200:
                    raise _status_error(response.status)
                length = response.getheader("Content-Length")
                if length and length.isdigit():
                    total = done + int(length)
                if total is not None:
                    if total > max_file:
                        raise RemoteError(f"the file is larger than {max_file // 1024**3} GiB")
                    if free_space(folder) < total - done + SPACE_MARGIN:
                        raise RemoteError(_space_message(total - done, free_space(folder)))
                chunks = 0
                while True:
                    if cancelled():
                        raise Cancelled("the download was cancelled")
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > max_file or (total is not None and done > total):
                        raise RemoteError("the server sent more than it said it would")
                    out.write(chunk)
                    digest.update(chunk)
                    chunks += 1
                    if total is None and chunks % 64 == 0 and free_space(folder) < SPACE_MARGIN:
                        raise RemoteError(_space_message(0, free_space(folder)))
                    progress(done, total)
            except (OSError, http.client.HTTPException) as exc:
                response.close()
                resumes += 1
                if resumes > MAX_RESUMES:
                    raise RemoteError(f"the connection kept dropping ({type(exc).__name__})") from exc
                out.flush()
                continue
            finally:
                response.close()
            if total is not None and done != total:
                resumes += 1
                if resumes > MAX_RESUMES:
                    raise RemoteError("the download ended early")
                continue
            break
    if expected and digest.hexdigest() != expected:
        raise RemoteError("the downloaded file does not match the SHA-256 you entered")


LOCATIONS_FILE = "netlocations.json"
LOCATIONS_MAX = 20
SECRETS = "netinstall"  # CredentialStore keyed-secret file for the passwords


class LocationStore:
    """Remembered locations: address and user name here (mode 0600), passwords in the CredentialStore."""

    def __init__(self, settings_dir: str, credentials: Any) -> None:
        self._path = os.path.join(settings_dir, LOCATIONS_FILE)
        self.credentials = credentials

    def _load(self) -> list[dict[str, Any]]:
        try:
            data = read_json(self._path, default={})
        except (OSError, ValueError):
            return []
        items = data.get("locations") if isinstance(data, dict) else None
        out = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("url"), str):
                out.append({"id": item["id"], "url": item["url"], "username": str(item.get("username") or "")})
        return out

    def public(self) -> list[dict[str, Any]]:
        return [{**loc, "passwordSet": bool(self.credentials.keyed_get(SECRETS, loc["id"]))} for loc in self._load()]

    def get(self, location_id: str) -> tuple[dict[str, Any], str]:
        loc = next((loc for loc in self._load() if loc["id"] == location_id), None)
        if loc is None:
            raise RemoteError("that location is no longer remembered")
        return loc, self.credentials.keyed_get(SECRETS, location_id)

    def save(self, url: str, username: str, password: str, location_id: str | None = None) -> list[dict[str, Any]]:
        """Remember a location. An empty password keeps the stored one."""
        from . import smbshare, webdav  # both import this module; pysmb itself loads only on use

        smb = smbshare.is_smb(url)
        dav = webdav.is_dav(url)
        if smb:
            url = smbshare.parse(url).url()
        elif dav:
            url = webdav.to_dav(check_location(webdav.to_http(url)))
        else:
            url = check_location(url)
        username = str(username or "").strip()
        if len(username) > 200 or any(ord(c) < 32 for c in username):
            raise RemoteError("the user name is not valid text")
        items = self._load()
        existing = next((loc for loc in items if loc["id"] == location_id), None) if location_id else None
        kept = self.credentials.keyed_get(SECRETS, existing["id"]) if existing else ""
        if not smb:
            # Refuses a password over plain http or dav://, including one kept from before.
            Session(webdav.to_http(url) if dav else url, username, password or kept)
        if existing is None:
            if len(items) >= LOCATIONS_MAX:
                raise RemoteError(f"Haversack remembers up to {LOCATIONS_MAX} locations; forget one first")
            existing = {"id": uuid.uuid4().hex[:12]}
            items.append(existing)
        existing.update(url=url, username=username)
        atomic_write_json(self._path, {"locations": items}, mode=0o600)
        if password:
            self.credentials.keyed_set(SECRETS, existing["id"], password)
        return self.public()

    def forget(self, location_id: str) -> list[dict[str, Any]]:
        items = [loc for loc in self._load() if loc["id"] != location_id]
        atomic_write_json(self._path, {"locations": items}, mode=0o600)
        self.credentials.keyed_set(SECRETS, location_id, None)
        return self.public()


def _space_message(needed: int, free: int) -> str:
    gib = 1024**3
    return (
        f"not enough free space: the download needs {needed / gib:.1f} GiB plus {SPACE_MARGIN // gib} GiB to spare, "
        f"and {free / gib:.1f} GiB is free"
    )


def _remove(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
