"""Shared HTTP plumbing for the WebDAV, S3 and Google Drive stores.

Transport errors and 429 or 5xx answers are retried with backoff and end as
:class:`StoreUnavailable` (nothing changed, try again later). A URL outside the
allowlist is refused at once and never retried.
"""

from __future__ import annotations

import hashlib
import time
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Mapping

from .. import net
from .base import StoreError, StoreUnavailable

MAX_RETRIES = 4
MAX_RETRY_AFTER = 30.0
MAX_SINGLE_UPLOAD = 1024 * 1024 * 1024  # one request per object; save blobs are far smaller


def call(
    transport: net.Transport,
    method: str,
    url: str,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    *,
    dest: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_bytes: int = net.DEFAULT_MAX_BYTES,
) -> net.HttpResponse:
    attempt = 0
    while True:
        try:
            response = transport(method, url, dict(headers or {}), body, dest=dest, max_bytes=max_bytes)
        except net.DisallowedHost as exc:
            raise StoreError(f"refused: {exc}") from exc
        except net.NetError as exc:
            attempt += 1
            if attempt > MAX_RETRIES:
                raise StoreUnavailable(str(exc)) from exc
            sleep(min(2.0**attempt, MAX_RETRY_AFTER))
            continue
        if response.status == 429 or response.status >= 500:
            attempt += 1
            if attempt > MAX_RETRIES:
                raise StoreUnavailable(f"service busy (HTTP {response.status})")
            try:
                delay = float(response.headers.get("retry-after", ""))
            except ValueError:
                delay = 2.0**attempt
            sleep(min(delay, MAX_RETRY_AFTER))
            continue
        return response


def parse_xml(body: bytes, what: str) -> ElementTree.Element:
    """Parse a WebDAV or S3 XML answer, refusing any DTD or entity declaration.

    Without a DTD there are no entities to expand, which rules out the entity
    expansion and external entity attacks ``defusedxml`` guards against; the
    body is also size-capped by the transport. Stdlib only (principle 9).
    """
    head = body[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in body.lower():
        raise StoreError(f"the {what} sent XML with a document type declaration; refused")
    try:
        return ElementTree.fromstring(body)  # noqa: S314 - DTDs refused above
    except ElementTree.ParseError as exc:
        raise StoreError(f"the {what} sent an unreadable listing") from exc


def read_upload(path: str) -> bytes:
    with open(path, "rb") as handle:
        data = handle.read(MAX_SINGLE_UPLOAD + 1)
    if len(data) > MAX_SINGLE_UPLOAD:
        raise StoreError("object too large")
    return data


def file_sha256(path: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()
