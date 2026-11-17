"""Install from a WebDAV folder that is not mounted (ADR-0033).

WebDAV is HTTP, so the session, the address rules and the download are the HTTP
ones in :mod:`remote`; only the listing differs (``PROPFIND`` with ``Depth: 1``
instead of a listing page). Addresses use the ``davs://`` and ``dav://`` forms
that file managers use, so a remembered location keeps its protocol; they map
to ``https://`` and ``http://``. Read-only: no other WebDAV method is sent.
"""

from __future__ import annotations

import http.client
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from .remote import LISTING_ENTRIES, LISTING_MAX, RemoteError, Session, _status_error

SCHEMES = {"davs": "https", "dav": "http"}
BACK = {v: k for k, v in SCHEMES.items()}
DAV = "{DAV:}"
PROPFIND_BODY = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:getcontentlength/></d:prop></d:propfind>'
)


class DavSession(Session):
    """An HTTP session (same rules) whose folder listings use ``PROPFIND``."""


def is_dav(url: str) -> bool:
    return str(url).strip().lower().split("://", 1)[0] in SCHEMES


def to_http(url: str) -> str:
    """``davs://host/path`` to ``https://host/path`` (and ``dav`` to ``http``)."""
    try:
        parts = urlsplit(str(url).strip())
    except ValueError as exc:
        raise RemoteError("that address is not valid") from exc
    scheme = SCHEMES.get(parts.scheme.lower())
    if scheme is None:
        raise RemoteError("a WebDAV address starts with davs:// (or dav:// on your local network)")
    return urlunsplit((scheme, parts.netloc, parts.path or "/", parts.query, parts.fragment))


def to_dav(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((BACK[parts.scheme], parts.netloc, parts.path, "", ""))


def list_folder(session: Session, url: str) -> list[dict[str, Any]]:
    """Folders and ISO files one level below the WebDAV folder ``url`` (an http or https address)."""
    if not url.endswith("/"):
        url += "/"
    headers = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}
    response, final = session.open(url, headers, method="PROPFIND", body=PROPFIND_BODY)
    try:
        if response.status in (200, 405, 501):  # a plain web server, not a WebDAV folder
            raise RemoteError("that address does not answer as a WebDAV folder; try Web server instead")
        if response.status != 207:
            raise _status_error(response.status)
        body = response.read(LISTING_MAX + 1)
    except (OSError, http.client.HTTPException) as exc:
        raise RemoteError(f"the listing could not be read: {type(exc).__name__}") from exc
    finally:
        response.close()
    if len(body) > LISTING_MAX:
        raise RemoteError("the listing is too large")
    return parse_multistatus(body, final)


def parse_multistatus(body: bytes, base: str) -> list[dict[str, Any]]:
    """Children of ``base`` from a ``207 Multi-Status`` answer, as ``davs://`` or ``dav://`` addresses."""
    try:
        import xml.etree.ElementTree as ElementTree  # lazy: Decky may not bundle xml (ADR-0030)
    except ImportError as exc:
        raise RemoteError("WebDAV needs Python's xml module, which this system lacks; use Web server") from exc
    if b"<!doctype" in body[:4096].lower() or b"<!entity" in body.lower():
        raise RemoteError("the server sent XML with a document type declaration; refused")
    try:
        root = ElementTree.fromstring(body)  # noqa: S314 - DTDs refused above, size capped by the caller
    except ElementTree.ParseError as exc:
        raise RemoteError("the server sent an unreadable listing") from exc
    base_parts = urlsplit(base if base.endswith("/") else base + "/")
    base_path = unquote(base_parts.path)
    seen: dict[str, dict[str, Any]] = {}
    for item in root.findall(f"{DAV}response"):
        if len(seen) >= LISTING_ENTRIES:
            break
        href = (item.findtext(f"{DAV}href") or "").strip()
        try:
            target = urlsplit(urljoin(base, href))
        except ValueError:
            continue
        if (target.scheme, target.netloc) != (base_parts.scheme, base_parts.netloc) or target.query:
            continue
        path = unquote(target.path)
        folder = item.find(f".//{DAV}collection") is not None
        if not path.startswith(base_path):
            continue
        name = path[len(base_path) :].strip("/")
        if not name or "/" in name or name in (".", "..") or any(c in name for c in '\\\x00"<>|:*?'):
            continue
        if not folder and not name.lower().endswith(".iso"):
            continue
        clean = target.path if not folder or target.path.endswith("/") else target.path + "/"
        url = to_dav(urlunsplit((base_parts.scheme, base_parts.netloc, clean, "", "")))
        entry: dict[str, Any] = {"name": name, "url": url, "kind": "folder" if folder else "iso"}
        length = (item.findtext(f".//{DAV}getcontentlength") or "").strip()
        if not folder and length.isdigit():
            entry["size"] = int(length)
        seen.setdefault(url, entry)
    return sorted(seen.values(), key=lambda e: (e["kind"] != "folder", e["name"].casefold()))
