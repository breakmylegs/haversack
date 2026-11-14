import json
import os

from keepsake import diagnostics
from keepsake.discovery import Shortcut


def test_environment_reports_modules():
    env = diagnostics.environment()
    assert env["modules"]["sqlite3"]["available"] in (True, False)
    assert env["modules"]["ssl"]["available"] is True
    assert "DECKY_PLUGIN_SETTINGS_DIR" in env["env"]


def test_env_value_hides_non_stock_usernames(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setenv("DECKY_USER", "deck")
    assert diagnostics._env_value("USER") == "[other user]"
    assert diagnostics._env_value("DECKY_USER") == "deck"


def test_shortcut_facts_library_index_and_exe_inside(tmp_path):
    base, card = tmp_path / "base", tmp_path / "card"
    compat = card / "steamapps" / "compatdata" / "77"
    exe = compat / "pfx" / "drive_c" / "Game" / "game.exe"
    exe.parent.mkdir(parents=True)
    (base / "steamapps").mkdir(parents=True)
    sc = Shortcut(appid_signed=77, appid_unsigned=77, name="G", exe=f'"{exe}"', start_dir="", last_play_time=0)
    libraries = [os.path.realpath(base), os.path.realpath(card)]
    facts = diagnostics._shortcut_facts(sc, libraries)
    assert facts["compatdataFound"] is True
    assert facts["compatdataLibraryIndex"] == 1
    assert facts["exeInsidePrefix"] is True
    missing = diagnostics._shortcut_facts(Shortcut(5, 5, "M", "/x.exe", "", 0), libraries)
    assert missing["compatdataFound"] is False and missing["compatdataLibraryIndex"] is None


def test_probe_events_capped(tmp_path):
    for i in range(diagnostics.PROBE_LIMIT + 5):
        diagnostics.record_probe_event(str(tmp_path), "lifetime", {"unAppID": i})
    events = diagnostics.probe_events(str(tmp_path))
    assert len(events) == diagnostics.PROBE_LIMIT
    assert events[-1]["payload"]["unAppID"] == diagnostics.PROBE_LIMIT + 4


def test_large_probe_payload_truncated(tmp_path):
    diagnostics.record_probe_event(str(tmp_path), "big", {"x": "y" * 20000})
    payload = diagnostics.probe_events(str(tmp_path))[0]["payload"]
    assert len(payload["truncated"]) == 8000


def test_export_is_redacted(tmp_path, monkeypatch):
    settings, runtime, logs = (tmp_path / n for n in ("s", "r", "l"))
    for folder in (settings, runtime, logs):
        folder.mkdir()
    monkeypatch.setattr(diagnostics, "steam", lambda: {"roots": [{"path": "/home/alice/.local/share/Steam"}]})
    diagnostics.record_probe_event(str(runtime), "x", {"access_token": "SECRET"})
    path = diagnostics.export(str(settings), str(runtime), str(logs), {"note": "me@example.com"})
    text = open(path, encoding="utf-8").read()
    assert "SECRET" not in text and "alice" not in text and "me@example.com" not in text
    data = json.loads(text)
    assert data["steam"]["roots"][0]["path"] == "~/.local/share/Steam"
