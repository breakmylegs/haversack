"""OneDrive (personal) store through Microsoft Graph, inside the app folder (build prompt section 11).

* Everything lives under ``/me/drive/special/approot`` (scope
  ``Files.ReadWrite.AppFolder``).
* Every write is create-only: an upload session with
  ``@microsoft.graph.conflictBehavior: fail``; Graph answers 409
  ``nameAlreadyExists`` when the name is taken, which becomes
  :class:`AlreadyExistsError` (threat model T13). Upload sessions are used even
  for small objects because create-only behaviour is documented for them.
* The bearer token goes only to ``graph.microsoft.com``. Upload URLs and
  download redirects are followed by hand without it (ADR-0008).
* Uploads are verified with the hash OneDrive reports (SHA-256 if present,
  else QuickXorHash); when that is missing or disagrees, the object is
  downloaded and compared.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
import urllib.parse
from collections.abc import Callable, Iterator
from typing import Any, BinaryIO, Protocol

from .. import net
from ..auth import AuthError
from ..quickxor import QuickXorHash
from .base import (
    AlreadyExistsError,
    NotFoundError,
    ObjectInfo,
    Store,
    StoreError,
    StoreUnavailable,
    validate_key,
    validate_prefix,
)

__all__ = ["GraphStore", "StoreUnavailable"]

GRAPH_ROOT = "https://graph.microsoft.com/v1.0/me/drive/special/approot"
CHUNK_SIZE = 32 * 320 * 1024  # 10 MiB, a multiple of 320 KiB as Graph requires
MAX_OBJECT_BYTES = 16 * 1024 * 1024 * 1024
MAX_RETRIES = 4
MAX_RETRY_AFTER = 30.0
REDIRECTS = (301, 302, 303, 307, 308)


class TokenSource(Protocol):
    def access_token(self, force_refresh: bool = False) -> str: ...


def _quote(key: str) -> str:
    return urllib.parse.quote(key, safe="/")


class GraphStore(Store):
    def __init__(
        self,
        tokens: TokenSource,
        transport: net.Transport = net.request,
        base_url: str = GRAPH_ROOT,
        sleep: Callable[[float], None] = time.sleep,
        chunk_size: int = CHUNK_SIZE,
    ) -> None:
        if chunk_size % (320 * 1024):
            raise ValueError("chunk size must be a multiple of 320 KiB")
        self.tokens = tokens
        self.transport = transport
        self.base = base_url.rstrip("/")
        self.sleep = sleep
        self.chunk_size = chunk_size

    # HTTP

    def _item(self, key: str, suffix: str = "") -> str:
        return f"{self.base}:/{_quote(key)}" + (f":/{suffix}" if suffix else "")

    def _children(self, folder: str) -> str:
        query = "?$select=name,size,file,folder&$top=200"
        if not folder:
            return f"{self.base}/children{query}"
        return f"{self.base}:/{_quote(folder)}:/children{query}"

    def _call(
        self,
        method: str,
        url: str,
        *,
        auth: bool = True,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        dest: str | None = None,
    ) -> net.HttpResponse:
        refreshed = False
        attempt = 0
        while True:
            request_headers = dict(headers or {})
            if auth:
                try:
                    request_headers["Authorization"] = "Bearer " + self.tokens.access_token(force_refresh=refreshed)
                except AuthError as exc:
                    raise StoreUnavailable(f"sign-in: {exc.reason}") from exc
            try:
                response = self.transport(method, url, request_headers, body, dest=dest)
            except net.DisallowedHost as exc:
                raise StoreError(f"refused: {exc}") from exc
            except net.NetError as exc:
                attempt += 1
                if attempt > MAX_RETRIES:
                    raise StoreUnavailable(str(exc)) from exc
                self.sleep(min(2.0**attempt, MAX_RETRY_AFTER))
                continue
            if response.status == 401 and auth and not refreshed:
                refreshed = True
                continue
            if response.status == 429 or response.status >= 500:
                attempt += 1
                if attempt > MAX_RETRIES:
                    raise StoreUnavailable(f"service busy (HTTP {response.status})")
                self.sleep(self._retry_after(response, attempt))
                continue
            return response

    @staticmethod
    def _retry_after(response: net.HttpResponse, attempt: int) -> float:
        try:
            return min(float(response.headers.get("retry-after", "")), MAX_RETRY_AFTER)
        except ValueError:
            return min(2.0**attempt, MAX_RETRY_AFTER)

    @staticmethod
    def _json(response: net.HttpResponse) -> dict[str, Any]:
        try:
            data = json.loads(response.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _fail(self, response: net.HttpResponse, what: str) -> StoreError:
        code = self._json(response).get("error", {})
        code = code.get("code") if isinstance(code, dict) else None
        return StoreError(f"{what} failed: HTTP {response.status} {code or ''}".strip())

    # Writing

    def put_new(self, key: str, data: bytes) -> ObjectInfo:
        return self._upload(key, len(data), io.BytesIO(data))

    def put_new_file(self, key: str, path: str) -> ObjectInfo:
        with open(path, "rb") as handle:
            return self._upload(key, os.path.getsize(path), handle)

    def _upload(self, key: str, size: int, source: BinaryIO) -> ObjectInfo:
        validate_key(key)
        if size == 0:
            raise StoreError("empty objects are not supported by upload sessions")
        if size > MAX_OBJECT_BYTES:
            raise StoreError("object too large")
        upload_url = self._create_session(key)
        sha = hashlib.sha256()
        qx = QuickXorHash()
        offset = 0
        item: dict[str, Any] = {}
        while offset < size:
            chunk = source.read(min(self.chunk_size, size - offset))
            if not chunk:
                raise StoreError("source ended early")
            sha.update(chunk)
            qx.update(chunk)
            end = offset + len(chunk) - 1
            headers = {"Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{end}/{size}"}
            response = self._call("PUT", upload_url, auth=False, body=chunk, headers=headers)
            if response.status == 409:
                self._cancel(upload_url)
                raise AlreadyExistsError(key)
            if response.status == 202:
                offset = end + 1
                continue
            if response.status in (200, 201):
                item = self._json(response)
                offset = end + 1
                break
            self._cancel(upload_url)
            raise self._fail(response, "upload")
        local_sha = sha.hexdigest()
        verified = self._verify_reported(item, local_sha, qx.digest_b64())
        return ObjectInfo(key=key, size=size, sha256=local_sha if verified else None)

    def _create_session(self, key: str) -> str:
        body = json.dumps({"item": {"@microsoft.graph.conflictBehavior": "fail"}}).encode()
        for attempt in range(2):
            response = self._call(
                "POST", self._item(key, "createUploadSession"), body=body, headers={"Content-Type": "application/json"}
            )
            if response.status == 409:
                raise AlreadyExistsError(key)
            if response.status == 404 and attempt == 0:
                self._ensure_parents(key)
                continue
            if response.status == 200:
                upload_url = self._json(response).get("uploadUrl")
                if isinstance(upload_url, str):
                    return upload_url  # the transport enforces the allowlist on every request
            raise self._fail(response, "create upload session")
        raise StoreError("could not create parent folders")

    def _cancel(self, upload_url: str) -> None:
        try:
            self.transport("DELETE", upload_url, {}, None)
        except net.NetError:
            pass  # sessions expire on their own

    def _ensure_parents(self, key: str) -> None:
        parts = key.split("/")[:-1]
        for depth in range(len(parts)):
            parent = "/".join(parts[:depth])
            url = f"{self.base}/children" if not parent else f"{self.base}:/{_quote(parent)}:/children"
            body = json.dumps({"name": parts[depth], "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
            response = self._call("POST", url, body=body.encode(), headers={"Content-Type": "application/json"})
            if response.status not in (200, 201, 409):
                raise self._fail(response, "create folder")

    @staticmethod
    def _verify_reported(item: dict[str, Any], sha256_hex: str, quickxor_b64: str) -> bool:
        hashes = item.get("file", {}).get("hashes", {}) if isinstance(item.get("file"), dict) else {}
        if not isinstance(hashes, dict):
            return False
        reported_sha = hashes.get("sha256Hash")
        if isinstance(reported_sha, str) and reported_sha:
            return reported_sha.lower() == sha256_hex
        reported_qx = hashes.get("quickXorHash")
        return isinstance(reported_qx, str) and reported_qx == quickxor_b64

    # Reading

    def _download(self, key: str, dest: str | None) -> net.HttpResponse:
        validate_key(key)
        response = self._call("GET", self._item(key, "content"), dest=dest)
        if response.status in REDIRECTS:
            location = response.headers.get("location", "")
            if not location:
                raise StoreError("download redirect without a location")
            response = self._call("GET", location, auth=False, dest=dest)  # pre-authenticated: no token
        if response.status == 404:
            raise NotFoundError(key)
        if response.status != 200:
            raise self._fail(response, "download")
        return response

    def get(self, key: str) -> bytes:
        return self._download(key, None).body

    def get_to_file(self, key: str, dest: str) -> ObjectInfo:
        self._download(key, dest)
        digest = hashlib.sha256()
        size = 0
        with open(dest, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return ObjectInfo(key=key, size=size, sha256=digest.hexdigest())

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        validate_prefix(prefix)
        if not prefix or prefix.endswith("/"):
            folder = prefix.rstrip("/")
        else:
            folder = prefix.rsplit("/", 1)[0] if "/" in prefix else ""
        out = [o for o in self._walk(folder, 0) if o.key.startswith(prefix)]
        return sorted(out, key=lambda o: o.key)

    def _walk(self, folder: str, depth: int) -> Iterator[ObjectInfo]:
        if depth > 16:
            return
        url: str | None = self._children(folder)
        while url:
            response = self._call("GET", url)
            if response.status == 404:
                return
            if response.status != 200:
                raise self._fail(response, "list")
            data = self._json(response)
            for child in data.get("value", []):
                if not isinstance(child, dict) or not isinstance(child.get("name"), str):
                    continue
                key = f"{folder}/{child['name']}" if folder else child["name"]
                if "folder" in child:
                    yield from self._walk(key, depth + 1)
                elif "file" in child:
                    yield ObjectInfo(key=key, size=int(child.get("size", 0)))
            next_link = data.get("@odata.nextLink")
            url = next_link if isinstance(next_link, str) else None

    def delete(self, key: str) -> None:
        validate_key(key)
        response = self._call("DELETE", self._item(key))
        if response.status == 404:
            raise NotFoundError(key)
        if response.status not in (200, 204):
            raise self._fail(response, "delete")

    def check(self) -> dict[str, Any]:
        """Open (and on first use create) the app folder."""
        response = self._call("GET", self.base)
        if response.status != 200:
            raise self._fail(response, "app folder")
        data = self._json(response)
        return {"name": data.get("name"), "id": bool(data.get("id"))}
