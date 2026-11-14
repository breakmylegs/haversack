import json
import os
import stat

import pytest

from keepsake.settings import SETTINGS_FILE, SettingsError, SettingsStore


def test_creates_device_id_once(tmp_path):
    first = SettingsStore(str(tmp_path)).get("deviceId")
    second = SettingsStore(str(tmp_path)).get("deviceId")
    assert first and first == second


def test_set_device_name_persists_and_normalises(tmp_path):
    store = SettingsStore(str(tmp_path))
    store.set("deviceName", "  Handheld   One ")
    assert SettingsStore(str(tmp_path)).get("deviceName") == "Handheld One"


def test_rejects_unknown_and_read_only_keys(tmp_path):
    store = SettingsStore(str(tmp_path))
    with pytest.raises(SettingsError):
        store.set("deviceId", "x")
    with pytest.raises(SettingsError):
        store.set("nonsense", 1)


def test_rejects_long_or_non_text_name(tmp_path):
    store = SettingsStore(str(tmp_path))
    with pytest.raises(SettingsError):
        store.set("deviceName", "x" * 41)
    with pytest.raises(SettingsError):
        store.set("deviceName", 5)


def test_unknown_stored_keys_hidden_but_preserved(tmp_path):
    # A newer version may have written keys this build does not know (rollback).
    (tmp_path / SETTINGS_FILE).write_text(json.dumps({"deviceName": "A", "futureKey": 1}))
    store = SettingsStore(str(tmp_path))
    assert "futureKey" not in store.all()
    assert store.all()["deviceName"] == "A"
    store.set("deviceName", "B")
    on_disk = json.loads((tmp_path / SETTINGS_FILE).read_text())
    assert on_disk["futureKey"] == 1 and on_disk["deviceName"] == "B"


def test_newer_schema_opens_read_only_and_never_writes(tmp_path):
    original = json.dumps({"schemaVersion": 99, "deviceId": "abc", "deviceName": "A", "newThing": [1]})
    (tmp_path / SETTINGS_FILE).write_text(original)
    store = SettingsStore(str(tmp_path))
    assert store.read_only is True
    assert store.all()["readOnly"] is True
    with pytest.raises(SettingsError):
        store.set("deviceName", "B")
    assert (tmp_path / SETTINGS_FILE).read_text() == original


def test_gate_thresholds_can_only_be_tightened(tmp_path):
    store = SettingsStore(str(tmp_path))
    assert store.get("gateMaxRemovedPercent") == 50 and store.get("gateMaxSizeDropPercent") == 70
    store.set("gateMaxRemovedPercent", 20)
    assert SettingsStore(str(tmp_path)).get("gateMaxRemovedPercent") == 20
    for key, bad in (
        ("gateMaxRemovedPercent", 51),
        ("gateMaxRemovedPercent", 4),
        ("gateMaxSizeDropPercent", 71),
        ("gateMaxSizeDropPercent", True),
        ("gateMaxSizeDropPercent", "10"),
    ):
        with pytest.raises(SettingsError):
            store.set(key, bad)


def test_update_channel(tmp_path):
    store = SettingsStore(str(tmp_path))
    assert store.get("updateChannel") == "stable"
    store.set("updateChannel", "prerelease")
    assert SettingsStore(str(tmp_path)).get("updateChannel") == "prerelease"
    with pytest.raises(SettingsError):
        store.set("updateChannel", "nightly")


@pytest.mark.posix
@pytest.mark.skipif(os.name != "posix", reason="file modes need POSIX")
def test_file_mode_is_private(tmp_path):
    SettingsStore(str(tmp_path))
    mode = stat.S_IMODE(os.stat(tmp_path / SETTINGS_FILE).st_mode)
    assert mode == 0o600
