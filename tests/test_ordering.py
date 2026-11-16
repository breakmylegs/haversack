"""The Games list order: needs approval, prefix mismatch, conflict, quarantined, then by name (16 November 2026)."""

import asyncio

from keepsake import ordering


def game(key, name, sync="synced", proposal=None):
    return {"key": key, "name": name, "sync": sync, "proposal": proposal}


def test_attention_order_then_natural_names():
    games = [
        game("a", "game 10"),
        game("b", "Zed", sync="quarantined"),
        game("c", "Alpha", sync="conflict"),
        game("d", "Game 2"),
        game("e", "Mismatched"),
        game("f", "beta", proposal={"candidate": {"gameKey": "x", "title": "X"}}),
        game("g", "Another needs approval", proposal={"candidate": {"gameKey": "y", "title": "Y"}}),
        game(
            "h",
            "Conflicted and needs approval",
            sync="conflict",
            proposal={"candidate": {"gameKey": "z", "title": None}},
        ),
        game("i", "game 2"),
    ]
    ordered = ordering.order(games, mismatched={"e"})
    assert [g["key"] for g in ordered] == ["g", "f", "h", "e", "c", "b", "d", "i", "a"]
    assert [g["attention"] for g in ordered[:6]] == [
        "confirm-match",
        "confirm-match",
        "confirm-match",
        "prefix-mismatch",
        "conflict",
        "quarantined",
    ]
    assert ordered[-1]["attention"] is None
    # "Game 2" and "game 2" tie on the name and fall back to the key; "game 10" comes after both.
    assert ordering.name_key("Game 2") == ordering.name_key("game 2") < ordering.name_key("game 10")


def test_order_is_the_same_for_any_subset():
    """Filters (All, Synced, Shortcuts, Steam) keep the same relative order."""
    games = [game(str(i), f"Game {i}", sync=["synced", "conflict", "off"][i % 3]) for i in range(30)]
    full = [g["key"] for g in ordering.order(games)]
    subset = [g for g in games if int(g["key"]) % 2 == 0]
    assert [g["key"] for g in ordering.order(subset)] == [k for k in full if int(k) % 2 == 0]


def test_match_games_returns_the_attention_order(tmp_path):
    from keepsake import discovery
    from keepsake.store import LocalFolderStore
    from test_app_ux import Device

    a = Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))
    discovery.record_cross_check(
        a.app.paths.runtime_dir,
        a.key,
        {"status": "mismatch", "reason": "synthetic", "observed": ["/synthetic/other"]},
        "/synthetic/prefix",
    )
    found = asyncio.run(a.app.match_games())
    assert found[0]["key"] == a.key and found[0]["attention"] == "prefix-mismatch"
