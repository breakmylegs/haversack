"""Google Drive store in the hidden app data folder (build prompt section 11, slice 10).

* Scope ``drive.appdata``: Keepsake sees only its own ``appDataFolder``, never
  the user's files. Objects are stored flat, named by their full store key.
* Drive allows several files with one name and has no create-only upload, so
  create-only is built on top (ADR-0021): check that the name is free, upload,
  then list every file with that name. The oldest by Drive's own
  ``createdTime`` (then file ID) is the object; a writer that finds an older
  copy deletes the copy it has just made and raises
  :class:`AlreadyExistsError`. Readers apply the same rule, so racing devices
  agree on one object (threat model T13). The only file ever deleted outside
  retention is a writer's own losing duplicate, seconds after creating it.
* Uploads are verified with the ``sha256Checksum`` Drive reports.
* The bearer token goes only to ``www.googleapis.com``; downloads that redirect
  elsewhere are refused (fail closed).
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from .. import net
from ..auth import AuthError
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
from .httpcall import call, file_sha256, read_upload

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FIELDS = "id,name,size,createdTime,sha256Checksum"
PAGE_SIZE = 1000
DOWNLOAD_MAX = 16 * 1024 * 1024 * 1024


class TokenSource(Protocol):
    def access_token(self, force_refresh: bool = False) -> str: ...


def _winner(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    return min(files, key=lambda f: (str(f.get("createdTime", "")), str(f.get("id", "")))) if files else None


class GoogleDriveStore(Store):
    def __init__(
        self,
        tokens: TokenSource,
        transport: net.Transport = net.google_request,
        api: str = API,
        upload: str = UPLOAD,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.tokens = tokens
        self.transport = transport
        self.api = api.rstrip("/")
        self.upload = upload.rstrip("/")
        self.sleep = sleep

    def _call(self, method: str, url: str, headers: dict[str, str] | None = None, **kw: Any) -> net.HttpResponse:
        refreshed = False
        while True:
            try:
                token = self.tokens.access_token(force_refresh=refreshed)
            except AuthError as exc:
                raise StoreUnavailable(f"sign-in: {exc.reason}") from exc
            response = call(
                self.transport,
                method,
                url,
                {**(headers or {}), "Authorization": f"Bearer {token}"},
                sleep=self.sleep,
                **kw,
            )
            if response.status == 401 and not refreshed:
                refreshed = True
                continue
            return response

    @staticmethod
    def _json(response: net.HttpResponse) -> dict[str, Any]:
        try:
            data = json.loads(response.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _query(self, q: str) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            fields = {
                "spaces": "appDataFolder",
                "q": q,
                "fields": f"nextPageToken,files({FIELDS})",
                "pageSize": str(PAGE_SIZE),
            }
            if token:
                fields["pageToken"] = token
            response = self._call("GET", f"{self.api}/files?{urllib.parse.urlencode(fields)}")
            if response.status != 200:
                raise StoreError(f"list failed: HTTP {response.status}")
            data = self._json(response)
            files.extend(f for f in data.get("files", []) if isinstance(f, dict) and isinstance(f.get("name"), str))
            token = data.get("nextPageToken") if isinstance(data.get("nextPageToken"), str) else None
            if not token:
                return files

    def _named(self, key: str) -> list[dict[str, Any]]:
        # Keys are limited to [A-Za-z0-9._/-], so no quoting is needed inside the query.
        return [f for f in self._query(f"name = '{key}' and trashed = false") if f["name"] == key]

    # Writing

    def put_new(self, key: str, data: bytes) -> ObjectInfo:
        validate_key(key)
        if self._named(key):
            raise AlreadyExistsError(key)
        boundary = "keepsake-" + uuid.uuid4().hex
        metadata = json.dumps({"name": key, "parents": ["appDataFolder"]}).encode()
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata
            + f"\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        response = self._call(
            "POST",
            f"{self.upload}/files?uploadType=multipart&fields={FIELDS}",
            {"Content-Type": f"multipart/related; boundary={boundary}"},
            body=body,
        )
        if response.status != 200:
            raise StoreError(f"upload failed: HTTP {response.status}")
        created = self._json(response)
        winner = _winner(self._named(key))
        if winner is not None and winner.get("id") != created.get("id"):
            self._delete_id(str(created.get("id", "")))  # our own losing duplicate, made seconds ago
            raise AlreadyExistsError(key)
        local = hashlib.sha256(data).hexdigest()
        reported = str(created.get("sha256Checksum", "")).lower()
        return ObjectInfo(key=key, size=len(data), sha256=local if reported == local else None)

    def put_new_file(self, key: str, path: str) -> ObjectInfo:
        return self.put_new(key, read_upload(path))

    def _delete_id(self, file_id: str) -> None:
        if not file_id:
            return
        response = self._call("DELETE", f"{self.api}/files/{urllib.parse.quote(file_id)}")
        if response.status not in (200, 204, 404):
            raise StoreError(f"delete failed: HTTP {response.status}")

    # Reading

    def _download(self, key: str, dest: str | None) -> net.HttpResponse:
        validate_key(key)
        winner = _winner(self._named(key))
        if winner is None:
            raise NotFoundError(key)
        url = f"{self.api}/files/{urllib.parse.quote(str(winner['id']))}?alt=media"
        response = self._call("GET", url, dest=dest, max_bytes=DOWNLOAD_MAX)
        if response.status == 404:
            raise NotFoundError(key)
        if response.status != 200:
            raise StoreError(f"download failed: HTTP {response.status}")
        return response

    def get(self, key: str) -> bytes:
        return self._download(key, None).body

    def get_to_file(self, key: str, dest: str) -> ObjectInfo:
        self._download(key, dest)
        size, digest = file_sha256(dest)
        return ObjectInfo(key=key, size=size, sha256=digest)

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        validate_prefix(prefix)
        seen: dict[str, dict[str, Any]] = {}
        for item in self._query("trashed = false"):
            name = item["name"]
            if not name.startswith(prefix):
                continue
            try:
                validate_key(name)
            except StoreError:
                continue
            current = seen.get(name)
            seen[name] = _winner([item, current]) if current else item  # type: ignore[assignment]
        return sorted(
            (ObjectInfo(key=name, size=int(item.get("size", 0) or 0)) for name, item in seen.items()),
            key=lambda o: o.key,
        )

    def delete(self, key: str) -> None:
        validate_key(key)
        files = self._named(key)
        if not files:
            raise NotFoundError(key)
        for item in files:  # retention removes every copy of the key
            self._delete_id(str(item.get("id", "")))

    def check(self) -> dict[str, Any]:
        response = self._call("GET", f"{self.api}/files?spaces=appDataFolder&pageSize=1&fields=files(id)")
        if response.status != 200:
            raise StoreError(f"Google Drive app folder: HTTP {response.status}")
        return {"ok": True}
