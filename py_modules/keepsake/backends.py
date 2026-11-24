"""Keys and passwords the user enters: the SteamGridDB key and network-location passwords.

One file per kind in the settings folder, mode 0600. Secrets are never returned to the frontend,
logged or put in diagnostics: :meth:`CredentialStore.public` reports only whether each is set.
Saving with an empty secret keeps the stored one, so the user never has to see or retype it.

The strip (ADR-0098) removed the cloud stores, Advisor and their settings. Files they left in the
settings folder stay there untouched, so reinstalling v0.60.0 finds them.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any

from .fsutil import atomic_write_json, read_json

FILES = {"steamgriddb": "steamgriddb.json"}
KEYED_FILES = {"netinstall": "netinstall-secrets.json"}
FIELDS: dict[str, dict[str, str]] = {"steamgriddb": {"apiKey": "secret"}}
REQUIRED = {"steamgriddb": ("apiKey",)}
DEFAULTS: dict[str, dict[str, Any]] = {"steamgriddb": {"apiKey": ""}}
MAX_TEXT = 300


class BackendConfigError(ValueError):
    pass


def _validate(kind: str, values: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULTS[kind])
    for name, field in FIELDS[kind].items():
        value = values.get(name, out[name])
        if not isinstance(value, str) or len(value) > MAX_TEXT or "\x00" in value:
            raise BackendConfigError(f"{name} is not valid text")
        out[name] = value if field == "secret" else value.strip()
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

    # Keyed secrets: one secret per remembered item, such as a network location's password (ADR-0033).

    def _keyed_path(self, kind: str) -> str:
        if kind not in KEYED_FILES:
            raise BackendConfigError(f"unknown secret store {kind}")
        return os.path.join(self._dir, KEYED_FILES[kind])

    def _keyed(self, kind: str) -> dict[str, str]:
        try:
            data = read_json(self._keyed_path(kind), default={})
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            return {}
        return {str(k): v for k, v in data.items() if isinstance(v, str)}

    def keyed_get(self, kind: str, key: str) -> str:
        with self._lock:
            return self._keyed(kind).get(str(key), "")

    def keyed_set(self, kind: str, key: str, value: str | None) -> None:
        """Store ``value`` for ``key``; None or "" removes it."""
        if value is not None and (not isinstance(value, str) or len(value) > MAX_TEXT or "\x00" in value):
            raise BackendConfigError("the password is not valid text")
        with self._lock:
            data = self._keyed(kind)
            if value:
                data[str(key)] = value
            else:
                data.pop(str(key), None)
            atomic_write_json(self._keyed_path(kind), data, mode=0o600)
