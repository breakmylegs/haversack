"""Settings and secrets for the WebDAV, S3 and Google Drive backends (build prompt section 11).

One file per backend in the settings folder, mode 0600. Secrets (passwords,
secret keys, the Google client secret) are never returned to the frontend,
logged or put in diagnostics: :meth:`CredentialStore.public` reports only
whether each is set. Saving with an empty secret keeps the stored one, so the
user never has to see or retype it.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any
from urllib.parse import urlsplit

from .fsutil import atomic_write_json, read_json

FILES = {"webdav": "webdav.json", "s3": "s3.json", "gdrive": "google-client.json", "steamgriddb": "steamgriddb.json"}
FIELDS: dict[str, dict[str, str]] = {
    "webdav": {"url": "text", "username": "text", "password": "secret"},
    "s3": {
        "endpoint": "text",
        "region": "text",
        "bucket": "text",
        "prefix": "text",
        "accessKey": "text",
        "secretKey": "secret",
        "pathStyle": "bool",
    },
    "gdrive": {"clientId": "text", "clientSecret": "secret"},
    "steamgriddb": {"apiKey": "secret"},
}
REQUIRED = {
    "webdav": ("url", "username", "password"),
    "s3": ("endpoint", "bucket", "accessKey", "secretKey"),
    "gdrive": ("clientId", "clientSecret"),
    "steamgriddb": ("apiKey",),
}
DEFAULTS: dict[str, dict[str, Any]] = {
    "webdav": {"url": "", "username": "", "password": ""},
    "s3": {
        "endpoint": "",
        "region": "us-east-1",
        "bucket": "",
        "prefix": "keepsake",
        "accessKey": "",
        "secretKey": "",
        "pathStyle": True,
    },
    "gdrive": {"clientId": "", "clientSecret": ""},
    "steamgriddb": {"apiKey": ""},
}
MAX_TEXT = 300
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_REGION = re.compile(r"^[a-z0-9-]{1,32}$")
_PREFIX = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]{0,63})(/[A-Za-z0-9][A-Za-z0-9._-]{0,63}){0,4}$")


class BackendConfigError(ValueError):
    pass


def _https(value: str, label: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname:
        raise BackendConfigError(f"the {label} must start with https://")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise BackendConfigError(f"enter the {label} without a user name, password or query")
    return value


def _validate(kind: str, values: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULTS[kind])
    for name, field in FIELDS[kind].items():
        value = values.get(name, out[name])
        if field == "bool":
            if not isinstance(value, bool):
                raise BackendConfigError(f"{name} must be true or false")
        else:
            if not isinstance(value, str) or len(value) > MAX_TEXT or "\x00" in value:
                raise BackendConfigError(f"{name} is not valid text")
            value = value if field == "secret" else value.strip()
        out[name] = value
    if kind == "webdav" and out["url"]:
        _https(out["url"], "WebDAV address")
    if kind == "s3":
        if out["endpoint"]:
            _https(out["endpoint"], "S3 endpoint")
        if out["bucket"] and not _BUCKET.match(out["bucket"]):
            raise BackendConfigError("the bucket name is 3 to 63 lower-case letters, digits, dots and hyphens")
        if not _REGION.match(out["region"] or "us-east-1"):
            raise BackendConfigError("the region looks like eu-west-2")
        if out["prefix"] and not _PREFIX.match(out["prefix"].strip("/")):
            raise BackendConfigError("the key prefix is folder names separated by /")
        out["prefix"] = out["prefix"].strip("/")
    if kind == "steamgriddb" and out["apiKey"] and not re.match(r"^[A-Za-z0-9]{16,64}$", out["apiKey"]):
        raise BackendConfigError("a SteamGridDB API key is 16 to 64 letters and digits")
    return out


class CredentialStore:
    def __init__(self, settings_dir: str) -> None:
        self._dir = settings_dir
        self._lock = threading.Lock()

    def _path(self, kind: str) -> str:
        if kind not in FILES:
            raise BackendConfigError(f"unknown backend {kind}")
        return os.path.join(self._dir, FILES[kind])

    def load(self, kind: str) -> dict[str, Any]:
        with self._lock:
            try:
                data = read_json(self._path(kind), default={})
            except (OSError, ValueError):
                data = {}
        try:
            return _validate(kind, data if isinstance(data, dict) else {})
        except BackendConfigError:
            return dict(DEFAULTS[kind])

    def public(self, kind: str) -> dict[str, Any]:
        """Settings for the frontend: secrets replaced by ``<name>Set`` flags."""
        data = self.load(kind)
        out: dict[str, Any] = {}
        for name, field in FIELDS[kind].items():
            if field == "secret":
                out[name] = ""
                out[f"{name}Set"] = bool(data[name])
            else:
                out[name] = data[name]
        out["configured"] = self.configured(kind)
        return out

    def save(self, kind: str, values: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict) or set(values) - set(FIELDS.get(kind, {})):
            raise BackendConfigError("unknown backend settings")
        current = self.load(kind)
        merged = {**current, **values}
        for name, field in FIELDS[kind].items():
            if field == "secret" and values.get(name, "") == "":
                merged[name] = current[name]  # blank means keep the stored secret
        clean = _validate(kind, merged)
        with self._lock:
            atomic_write_json(self._path(kind), clean, mode=0o600)
        return self.public(kind)

    def clear(self, kind: str) -> None:
        with self._lock:
            try:
                os.unlink(self._path(kind))
            except FileNotFoundError:
                pass

    def configured(self, kind: str) -> bool:
        data = self.load(kind)
        return all(data.get(name) for name in REQUIRED[kind])
