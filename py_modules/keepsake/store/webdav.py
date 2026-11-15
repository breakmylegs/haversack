"""WebDAV store (build prompt section 11, slice 10).

* The user enters an HTTPS folder URL, a user name and a password (for
  Nextcloud and ownCloud, an app password). Only that host is ever contacted.
* Writes are create-only with ``If-None-Match: *``: the server answers 412 when
  the name is taken, which becomes :class:`AlreadyExistsError` (threat model
  T13). Some servers ignore the header, so :meth:`WebDavStore.check` proves
  create-only behaviour before the store is used and refuses it otherwise
  (fail closed).
* WebDAV reports no content hash, so uploads return no verified ``sha256`` and
  the snapshot engine verifies blobs by downloading them again.
"""

from __future__ import annotations

import base64
import time
import urllib.parse
from collections.abc import Callable, Iterator
from typing import Any

from .. import net
from .base import AlreadyExistsError, NotFoundError, ObjectInfo, Store, StoreError, validate_key, validate_prefix
from .httpcall import call, file_sha256, parse_xml, read_upload

DAV = "{DAV:}"
PROPFIND_BODY = (
    b'<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:"><d:prop>'
    b"<d:resourcetype/><d:getcontentlength/></d:prop></d:propfind>"
)
MAX_DEPTH = 16
DOWNLOAD_MAX = 16 * 1024 * 1024 * 1024


class WebDavStore(Store):
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        transport: net.Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not base_url.endswith("/"):
            base_url += "/"
        self.base = base_url
        self.base_path = urllib.parse.urlsplit(base_url).path
        self.transport = transport or net.endpoint_transport(base_url)
        self.sleep = sleep
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        self._auth = {"Authorization": f"Basic {token}"}

    def _url(self, key: str) -> str:
        return self.base + urllib.parse.quote(key, safe="/")

    def _call(self, method: str, url: str, headers: dict[str, str] | None = None, **kw: Any) -> net.HttpResponse:
        response = call(self.transport, method, url, {**self._auth, **(headers or {})}, sleep=self.sleep, **kw)
        if response.status == 401:
            raise StoreError("the WebDAV server refused the user name or password")
        return response

    # Writing

    def put_new(self, key: str, data: bytes) -> ObjectInfo:
        validate_key(key)
        self._ensure_parents(key)
        response = self._call("PUT", self._url(key), {"If-None-Match": "*"}, body=data)
        if response.status == 412:
            raise AlreadyExistsError(key)
        if response.status not in (200, 201, 204):
            raise StoreError(f"upload failed: HTTP {response.status}")
        return ObjectInfo(key=key, size=len(data))  # no server hash: the engine verifies by download

    def put_new_file(self, key: str, path: str) -> ObjectInfo:
        return self.put_new(key, read_upload(path))

    def _ensure_parents(self, key: str) -> None:
        parts = key.split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            folder = "/".join(parts[:depth]) + "/"
            response = self._call("MKCOL", self._url(folder))
            if response.status not in (201, 405):  # 405: it already exists
                raise StoreError(f"could not create folder {folder}: HTTP {response.status}")

    # Reading

    def get(self, key: str) -> bytes:
        validate_key(key)
        response = self._call("GET", self._url(key), max_bytes=DOWNLOAD_MAX)
        if response.status == 404:
            raise NotFoundError(key)
        if response.status != 200:
            raise StoreError(f"download failed: HTTP {response.status}")
        return response.body

    def get_to_file(self, key: str, dest: str) -> ObjectInfo:
        validate_key(key)
        response = self._call("GET", self._url(key), dest=dest, max_bytes=DOWNLOAD_MAX)
        if response.status == 404:
            raise NotFoundError(key)
        if response.status != 200:
            raise StoreError(f"download failed: HTTP {response.status}")
        size, digest = file_sha256(dest)
        return ObjectInfo(key=key, size=size, sha256=digest)

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        validate_prefix(prefix)
        if not prefix or prefix.endswith("/"):
            folder = prefix
        else:
            folder = prefix.rsplit("/", 1)[0] + "/" if "/" in prefix else ""
        out = [o for o in self._walk(folder, 0) if o.key.startswith(prefix)]
        return sorted(out, key=lambda o: o.key)

    def _walk(self, folder: str, depth: int) -> Iterator[ObjectInfo]:
        if depth > MAX_DEPTH:
            return
        response = self._call(
            "PROPFIND",
            self._url(folder),
            {"Depth": "1", "Content-Type": "application/xml"},
            body=PROPFIND_BODY,
        )
        if response.status == 404:
            return
        if response.status != 207:
            raise StoreError(f"list failed: HTTP {response.status}")
        for name, is_folder, size in self._entries(response.body, folder):
            key = folder + name
            if is_folder:
                yield from self._walk(key + "/", depth + 1)
            else:
                yield ObjectInfo(key=key, size=size)

    def _entries(self, body: bytes, folder: str) -> Iterator[tuple[str, bool, int]]:
        root = parse_xml(body, "WebDAV server")
        own = self.base_path + urllib.parse.quote(folder, safe="/")
        for item in root.iter(DAV + "response"):
            href = urllib.parse.urlsplit((item.findtext(DAV + "href") or "").strip()).path
            if urllib.parse.unquote(href.rstrip("/")) == urllib.parse.unquote(own.rstrip("/")):
                continue  # the folder itself
            name = urllib.parse.unquote(href.rstrip("/").rsplit("/", 1)[-1])
            try:
                validate_key(name)
            except StoreError:
                continue  # never Keepsake's: ignore
            is_folder = item.find(f".//{DAV}resourcetype/{DAV}collection") is not None
            try:
                size = int(item.findtext(f".//{DAV}getcontentlength") or 0)
            except ValueError:
                size = 0
            yield name, is_folder, size

    def delete(self, key: str) -> None:
        validate_key(key)
        response = self._call("DELETE", self._url(key))
        if response.status == 404:
            raise NotFoundError(key)
        if response.status not in (200, 204):
            raise StoreError(f"delete failed: HTTP {response.status}")

    def check(self, device_id: str) -> dict[str, Any]:
        """Prove the server honours create-only writes before it is used (fail closed).

        Writes ``registry/probe/<deviceId>.json`` once (kept, a few bytes) and then
        tries to write it again: the second write must be refused.
        """
        key = f"registry/probe/{device_id}.json"
        try:
            self.put_new(key, b'{"probe":true}')
        except AlreadyExistsError:
            pass
        try:
            self.put_new(key, b'{"probe":true}')
        except AlreadyExistsError:
            return {"ok": True}
        raise StoreError("this WebDAV server ignores create-only writes (If-None-Match), so Keepsake cannot use it")
