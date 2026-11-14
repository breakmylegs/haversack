"""Settings store: one JSON file in the plugin settings folder.

Writes are atomic and the file is mode 0600. Unknown keys are rejected so a
typo in the frontend cannot silently create a setting nobody reads.
"""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any

from .fsutil import atomic_write_json, read_json
from .safepath import ensure_within

SETTINGS_FILE = "settings.json"
SCHEMA_VERSION = 1
DEVICE_NAME_MAX = 40

DEFAULTS: dict[str, Any] = {
    "schemaVersion": SCHEMA_VERSION,
    "deviceId": "",
    "deviceName": "",
}

# Keys the frontend may change. deviceId and schemaVersion are managed here.
USER_KEYS = frozenset({"deviceName"})


class SettingsError(ValueError):
    pass


class SettingsStore:
    def __init__(self, settings_dir: str) -> None:
        self._dir = settings_dir
        self._path = ensure_within(settings_dir, os.path.join(settings_dir, SETTINGS_FILE))
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        stored = read_json(self._path, default={})
        if not isinstance(stored, dict):
            raise SettingsError("settings file is not a JSON object")
        data = dict(DEFAULTS)
        data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        changed = False
        if not data["deviceId"]:
            data["deviceId"] = str(uuid.uuid4())
            changed = True
        if changed or stored != data:
            atomic_write_json(self._path, data)
        return data

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data[key]

    def set(self, key: str, value: Any) -> dict[str, Any]:
        if key not in USER_KEYS:
            raise SettingsError(f"unknown or read-only setting: {key}")
        value = _validate(key, value)
        with self._lock:
            self._data[key] = value
            atomic_write_json(self._path, self._data)
            return dict(self._data)


def _validate(key: str, value: Any) -> Any:
    if key == "deviceName":
        if not isinstance(value, str):
            raise SettingsError("device name must be text")
        value = " ".join(value.split())
        if len(value) > DEVICE_NAME_MAX:
            raise SettingsError(f"device name must be {DEVICE_NAME_MAX} characters or fewer")
        return value
    raise SettingsError(f"no validator for {key}")
