"""Settings store: one JSON file in the plugin settings folder.

Writes are atomic and the file is mode 0600. Unknown keys cannot be set from
the frontend, but unknown keys already in the file are preserved, so rolling
back to an older version never deletes settings a newer version wrote.

If the file's ``schemaVersion`` is newer than this build understands (after a
rollback), the store opens in read-only safe mode and never writes
(build prompt section 12).
"""

from __future__ import annotations

import os
import re
import threading
import uuid
from typing import Any

from .fsutil import atomic_write_json, read_json
from .safepath import ensure_within

SETTINGS_FILE = "settings.json"
SCHEMA_VERSION = 1
DEVICE_NAME_MAX = 40
UPDATE_CHANNELS = ("stable", "prerelease")

DEFAULTS: dict[str, Any] = {
    "schemaVersion": SCHEMA_VERSION,
    "deviceId": "",
    "deviceName": "",
    "updateChannel": "stable",
    "gateMaxRemovedPercent": 50,
    "gateMaxSizeDropPercent": 70,
    "onedriveClientId": "",
    "snapshotStore": "local",
    "launchPullTimeout": 20,
    "toastOnSync": True,
    "idleSyncMinutes": 30,
    "showSteamApps": False,
    "setupComplete": False,
    # Slice 11 features, each behind its own setting.
    "registrySync": True,  # available; each game still opts in (off by default per game)
    "steamCloudDetection": True,
    "suspendSnapshots": False,
    # v2 module flags (slice 13); missing names use modules.DEFAULT_FLAGS.
    "moduleFlags": {},
}
MODULE_NAMES = ("saves", "advisor", "replication", "installer", "desktop")

# Keys the frontend may change. deviceId and schemaVersion are managed here.
USER_KEYS = frozenset(
    {
        "deviceName",
        "updateChannel",
        "gateMaxRemovedPercent",
        "gateMaxSizeDropPercent",
        "onedriveClientId",
        "snapshotStore",
        "launchPullTimeout",
        "toastOnSync",
        "idleSyncMinutes",
        "showSteamApps",
        "setupComplete",
        "registrySync",
        "steamCloudDetection",
        "suspendSnapshots",
        "moduleFlags",
    }
)
IDLE_MINUTES_RANGE = (10, 240)
SNAPSHOT_STORES = ("local", "onedrive", "webdav", "s3", "gdrive")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Safety gates may only be tightened (build prompt section 9): [floor, default].
GATE_LIMITS = {"gateMaxRemovedPercent": (5, 50), "gateMaxSizeDropPercent": (5, 70)}


class SettingsError(ValueError):
    pass


class SettingsStore:
    def __init__(self, settings_dir: str) -> None:
        self._dir = settings_dir
        self._path = ensure_within(settings_dir, os.path.join(settings_dir, SETTINGS_FILE))
        self._lock = threading.Lock()
        self.read_only = False
        self._extra: dict[str, Any] = {}
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        stored = read_json(self._path, default={})
        if not isinstance(stored, dict):
            raise SettingsError("settings file is not a JSON object")
        stored_schema = stored.get("schemaVersion", SCHEMA_VERSION)
        if isinstance(stored_schema, int) and stored_schema > SCHEMA_VERSION:
            self.read_only = True
        self._extra = {k: v for k, v in stored.items() if k not in DEFAULTS}
        data = dict(DEFAULTS)
        data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        if self.read_only:
            return data
        data["schemaVersion"] = SCHEMA_VERSION
        if not data["deviceId"]:
            data["deviceId"] = str(uuid.uuid4())
        if {**self._extra, **data} != stored:
            self._write(data)
        return data

    def _write(self, data: dict[str, Any]) -> None:
        if self.read_only:
            raise SettingsError("settings are read-only because a newer Keepsake wrote them; please update")
        atomic_write_json(self._path, {**self._extra, **data})

    def all(self) -> dict[str, Any]:
        with self._lock:
            return {**self._data, "readOnly": self.read_only}

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data[key]

    def set(self, key: str, value: Any) -> dict[str, Any]:
        if key not in USER_KEYS:
            raise SettingsError(f"unknown or read-only setting: {key}")
        value = _validate(key, value)
        with self._lock:
            updated = {**self._data, key: value}
            self._write(updated)
            self._data = updated
            return {**self._data, "readOnly": self.read_only}


def _validate(key: str, value: Any) -> Any:
    if key == "deviceName":
        if not isinstance(value, str):
            raise SettingsError("device name must be text")
        value = " ".join(value.split())
        if len(value) > DEVICE_NAME_MAX:
            raise SettingsError(f"device name must be {DEVICE_NAME_MAX} characters or fewer")
        return value
    if key == "updateChannel":
        if value not in UPDATE_CHANNELS:
            raise SettingsError("update channel must be stable or prerelease")
        return value
    if key == "onedriveClientId":
        if not isinstance(value, str) or (value.strip() and not _GUID.match(value.strip())):
            raise SettingsError("the client ID looks like 00001111-aaaa-2222-bbbb-3333cccc4444")
        return value.strip().lower()
    if key == "launchPullTimeout":
        if not isinstance(value, int) or isinstance(value, bool) or not 5 <= value <= 60:
            raise SettingsError("the launch check timeout is 5 to 60 seconds")
        return value
    if key == "moduleFlags":
        if not isinstance(value, dict) or set(value) - set(MODULE_NAMES):
            raise SettingsError("unknown module")
        if not all(isinstance(v, bool) for v in value.values()):
            raise SettingsError("module flags are true or false")
        return dict(value)
    if key == "idleSyncMinutes":
        low, high = IDLE_MINUTES_RANGE
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise SettingsError(f"the idle sync interval is {low} to {high} minutes")
        return value
    if key in (
        "toastOnSync",
        "showSteamApps",
        "setupComplete",
        "registrySync",
        "steamCloudDetection",
        "suspendSnapshots",
    ):
        if not isinstance(value, bool):
            raise SettingsError("must be true or false")
        return value
    if key == "snapshotStore":
        if value not in SNAPSHOT_STORES:
            raise SettingsError("store must be local, onedrive, webdav, s3 or gdrive")
        return value
    if key in GATE_LIMITS:
        low, high = GATE_LIMITS[key]
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise SettingsError(f"must be a whole number from {low} to {high} (gates can only be tightened)")
        return value
    raise SettingsError(f"no validator for {key}")
