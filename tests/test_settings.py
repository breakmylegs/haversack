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


def test_drops_unknown_stored_keys(tmp_path):
    (tmp_path / SETTINGS_FILE).write_text(json.dumps({"deviceName": "A", "junk": 1}))
    data = SettingsStore(str(tmp_path)).all()
    assert "junk" not in data
    assert data["deviceName"] == "A"


@pytest.mark.skipif(os.name != "posix", reason="file modes need POSIX")
def test_file_mode_is_private(tmp_path):
    SettingsStore(str(tmp_path))
    mode = stat.S_IMODE(os.stat(tmp_path / SETTINGS_FILE).st_mode)
    assert mode == 0o600
