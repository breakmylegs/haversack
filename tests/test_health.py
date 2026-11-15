import json

from keepsake import health

NOW = 1_800_000_000.0


def by_id(checks):
    return {c["id"]: c for c in checks}


def facts(**overrides):
    base = {
        "now": NOW,
        "cloud": {"store": "onedrive", "signedIn": True, "problem": None},
        "games": [],
        "mismatches": [],
        "manifest": {"available": True, "fetched": NOW - 3600, "stale": False},
        "ludusavi": {"installed": False},
    }
    base.update(overrides)
    return base


def test_all_clear_is_ok():
    checks = health.run(facts())
    assert health.summary(checks) == "ok"
    assert {c["id"] for c in checks} == {
        "cloud",
        "last-sync",
        "sessions",
        "quarantine",
        "conflicts",
        "prefix",
        "played-without",
        "manifest",
        "ludusavi",
    }


def test_cloud_states():
    assert by_id(health.run(facts(cloud={"store": "local"})))["cloud"]["status"] == "warn"
    assert by_id(health.run(facts(cloud={"store": "onedrive", "signedIn": False})))["cloud"]["status"] == "fail"
    problem = {"store": "onedrive", "signedIn": True, "problem": "invalid_grant"}
    assert by_id(health.run(facts(cloud=problem)))["cloud"]["status"] == "fail"
    down = {"store": "onedrive", "signedIn": True, "reachable": False, "error": "offline"}
    assert by_id(health.run(facts(cloud=down)))["cloud"]["status"] == "warn"
    up = {"store": "onedrive", "signedIn": True, "reachable": True}
    assert by_id(health.run(facts(cloud=up)))["cloud"]["detail"] == "Signed in and OneDrive answered."


def test_game_problems_are_reported_by_name():
    games = [
        {"name": "Synced", "state": {"base": "s1", "lastPush": NOW - 120, "lastPull": NOW - 7200}},
        {"name": "Never", "state": {}},
        {"name": "Stuck", "state": {"base": "s2", "sessionOpen": {"started": NOW - 7 * 3600}}, "running": False},
        {"name": "Playing", "state": {"base": "s3", "sessionOpen": {"started": NOW - 7 * 3600}}, "running": True},
        {"name": "Odd", "state": {"base": "s4", "quarantined": "q1", "conflict": {"kind": "fork"}}},
        {"name": "Unseen", "state": {"base": "s5"}, "playedWithoutKeepsake": True},
    ]
    checks = by_id(health.run(facts(games=games, mismatches=["Broken"])))
    assert checks["last-sync"]["status"] == "warn" and "1 not synced yet" in checks["last-sync"]["detail"]
    assert "Synced: pushed 2 minutes ago, pulled 2 hours ago" in checks["last-sync"]["items"]
    assert checks["sessions"]["items"] == ["Stuck"]  # a running game's open session is normal
    assert checks["quarantine"]["items"] == ["Odd"] and checks["conflicts"]["items"] == ["Odd"]
    assert checks["prefix"]["status"] == "fail" and checks["prefix"]["items"] == ["Broken"]
    assert checks["played-without"]["items"] == ["Unseen"]
    assert health.summary(list(checks.values())) == "fail"


def test_manifest_age():
    assert by_id(health.run(facts(manifest={"available": False})))["manifest"]["status"] == "fail"
    stale = {"available": True, "fetched": NOW - 20 * 86400, "stale": True}
    check = by_id(health.run(facts(manifest=stale)))["manifest"]
    assert check["status"] == "warn" and "20 days ago" in check["detail"]


def test_ludusavi_warns_only_when_active_alongside_synced_games():
    game = [{"name": "G", "state": {"base": "s"}}]
    assert by_id(health.run(facts(ludusavi={"installed": True}, games=game)))["ludusavi"]["status"] == "warn"
    assert by_id(health.run(facts(ludusavi={"installed": True})))["ludusavi"]["status"] == "info"
    off = {"installed": True, "disabled": True}
    assert by_id(health.run(facts(ludusavi=off, games=game)))["ludusavi"]["status"] == "ok"


def test_detect_decky_plugin(tmp_path):
    assert health.detect_decky_plugin(None, "ludusavi")["installed"] is False
    assert health.detect_decky_plugin(str(tmp_path), "ludusavi")["installed"] is False
    (tmp_path / "plugins" / "other").mkdir(parents=True)
    (tmp_path / "plugins" / "other" / "plugin.json").write_text(json.dumps({"name": "Something"}))
    (tmp_path / "plugins" / "broken").mkdir()
    (tmp_path / "plugins" / "broken" / "plugin.json").write_text("not json")
    (tmp_path / "plugins" / "x").mkdir()
    (tmp_path / "plugins" / "x" / "plugin.json").write_text(json.dumps({"name": "Decky Ludusavi"}))
    found = health.detect_decky_plugin(str(tmp_path), "ludusavi")
    assert found == {"installed": True, "disabled": False, "name": "Decky Ludusavi"}
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "loader.json").write_text(json.dumps({"disabled_plugins": ["Decky Ludusavi"]}))
    assert health.detect_decky_plugin(str(tmp_path), "ludusavi")["disabled"] is True
