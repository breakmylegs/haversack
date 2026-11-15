"""S3 and S3-compatible store (build prompt section 11, slice 10).

* The user enters an HTTPS endpoint, region, bucket, an optional key prefix and
  an access key pair. Only the endpoint's host (or ``<bucket>.<host>`` with
  virtual-hosted addressing) is contacted.
* Requests are signed with SigV4 (``sigv4.py``); the signed payload hash makes
  the service reject a corrupted upload, so a successful upload is verified.
* Writes are create-only with ``If-None-Match: *`` (412 when the key exists,
  409 while a competing conditional write is in progress). Not every
  S3-compatible service supports conditional writes, so :meth:`S3Store.check`
  proves it before use and refuses the store otherwise (fail closed).
"""

from __future__ import annotations

import builtins
import hashlib
import time
import urllib.parse
from collections.abc import Callable
from typing import Any

from .. import net
from . import sigv4
from .base import AlreadyExistsError, NotFoundError, ObjectInfo, Store, StoreError, validate_key, validate_prefix
from .httpcall import call, file_sha256, parse_xml, read_upload

CONFLICT_RETRIES = 3
DOWNLOAD_MAX = 16 * 1024 * 1024 * 1024


class S3Store(Store):
    def __init__(
        self,
        endpoint: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        prefix: str = "keepsake/",
        path_style: bool = True,
        transport: net.Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not bucket or "/" in bucket:
            raise StoreError("enter a bucket name")
        if prefix:
            validate_prefix(prefix if prefix.endswith("/") else prefix + "/")
        self.prefix = (prefix.rstrip("/") + "/") if prefix else ""
        self.bucket = bucket
        self.region = region or "us-east-1"
        self.access_key = access_key
        self.secret_key = secret_key
        self.origin = self.origin_for(endpoint, bucket, path_style)
        self.base_path = f"/{urllib.parse.quote(bucket)}/" if path_style else "/"
        self.transport = transport or net.endpoint_transport(self.origin)
        self.sleep = sleep
        self.clock = clock

    @staticmethod
    def origin_for(endpoint: str, bucket: str, path_style: bool) -> str:
        parts = urllib.parse.urlsplit(endpoint.rstrip("/"))
        return f"{parts.scheme}://{parts.netloc}" if path_style else f"{parts.scheme}://{bucket}.{parts.netloc}"

    def _url(self, key: str) -> str:
        return self.origin + self.base_path + urllib.parse.quote(self.prefix + key, safe="/~")

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        payload_sha256: str = sigv4.EMPTY_SHA256,
        headers: dict[str, str] | None = None,
        **kw: Any,
    ) -> net.HttpResponse:
        signed = sigv4.sign(
            method, url, headers or {}, payload_sha256, self.access_key, self.secret_key, self.region, now=self.clock()
        )
        response = call(self.transport, method, url, signed, body, sleep=self.sleep, **kw)
        if response.status in (401, 403):
            raise StoreError(f"the S3 service refused the access key (HTTP {response.status})")
        return response

    # Writing

    def put_new(self, key: str, data: bytes) -> ObjectInfo:
        validate_key(key)
        digest = hashlib.sha256(data).hexdigest()
        for _ in range(CONFLICT_RETRIES):
            response = self._request(
                "PUT", self._url(key), data, digest, {"If-None-Match": "*", "Content-Length": str(len(data))}
            )
            if response.status == 412:
                raise AlreadyExistsError(key)
            if response.status == 409:
                continue  # a competing conditional write: try again, which ends in 412 or success
            if response.status != 200:
                raise StoreError(f"upload failed: HTTP {response.status}")
            return ObjectInfo(key=key, size=len(data), sha256=digest)  # the signed hash was checked by the service
        raise StoreError("upload kept conflicting with another writer")

    def put_new_file(self, key: str, path: str) -> ObjectInfo:
        return self.put_new(key, read_upload(path))

    # Reading

    def get(self, key: str) -> bytes:
        validate_key(key)
        response = self._request("GET", self._url(key), max_bytes=DOWNLOAD_MAX)
        if response.status == 404:
            raise NotFoundError(key)
        if response.status != 200:
            raise StoreError(f"download failed: HTTP {response.status}")
        return response.body

    def get_to_file(self, key: str, dest: str) -> ObjectInfo:
        validate_key(key)
        response = self._request("GET", self._url(key), dest=dest, max_bytes=DOWNLOAD_MAX)
        if response.status == 404:
            raise NotFoundError(key)
        if response.status != 200:
            raise StoreError(f"download failed: HTTP {response.status}")
        size, digest = file_sha256(dest)
        return ObjectInfo(key=key, size=size, sha256=digest)

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        validate_prefix(prefix)
        out: list[ObjectInfo] = []
        token: str | None = None
        while True:
            fields = {"list-type": "2", "prefix": self.prefix + prefix}
            if token:
                fields["continuation-token"] = token
            query = urllib.parse.urlencode(sorted(fields.items()), quote_via=urllib.parse.quote)
            response = self._request("GET", f"{self.origin}{self.base_path}?{query}")  # the bucket, not a key
            if response.status != 200:
                raise StoreError(f"list failed: HTTP {response.status}")
            keys, token = self._parse_list(response.body)
            out.extend(keys)
            if not token:
                return sorted(out, key=lambda o: o.key)

    def _parse_list(self, body: bytes) -> tuple[builtins.list[ObjectInfo], str | None]:
        root = parse_xml(body, "S3 service")
        ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
        out = []
        for item in root.iter(ns + "Contents"):
            full = item.findtext(ns + "Key") or ""
            if not full.startswith(self.prefix):
                continue
            key = full[len(self.prefix) :]
            try:
                validate_key(key)
            except StoreError:
                continue  # not Keepsake's: ignore
            try:
                size = int(item.findtext(ns + "Size") or 0)
            except ValueError:
                size = 0
            out.append(ObjectInfo(key=key, size=size))
        truncated = (root.findtext(ns + "IsTruncated") or "").lower() == "true"
        token = root.findtext(ns + "NextContinuationToken") if truncated else None
        return out, token or None

    def delete(self, key: str) -> None:
        validate_key(key)
        head = self._request("HEAD", self._url(key))
        if head.status == 404:
            raise NotFoundError(key)  # S3 answers 204 for missing keys, so check first
        response = self._request("DELETE", self._url(key))
        if response.status not in (200, 204):
            raise StoreError(f"delete failed: HTTP {response.status}")

    def check(self, device_id: str) -> dict[str, Any]:
        """Prove conditional writes work before the store is used (fail closed)."""
        key = f"registry/probe/{device_id}.json"
        try:
            self.put_new(key, b'{"probe":true}')
        except AlreadyExistsError:
            pass
        try:
            self.put_new(key, b'{"probe":true}')
        except AlreadyExistsError:
            return {"ok": True}
        raise StoreError("this S3 service ignores conditional writes (If-None-Match), so Keepsake cannot use it")
