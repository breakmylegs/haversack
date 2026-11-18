"""R1, save safety and control (ADR-0048): the conflict screen's details, checkpoints, partial restore
and the Activity list. Synthetic games and saves only."""

import asyncio
import os

import pytest

from keepsake import activity
from keepsake.app import checkpoint_label, restore_paths
from keepsake.snapshot import FileEntry
from keepsake.sync import file_changes
from test_app_snapshots import KEY, app_and_save  # noqa: F401 - the fixture
from test_app_ux import pair, run  # noqa: F401 - the fixture


def entry(rel, digest="a" * 64, root="winLocalAppData"):
    return FileEntry(root, rel, 1, digest)


# The conflict screen


def test_file_changes_lists_added_removed_and_changed_files_by_logical_path():
    before = [entry("Game/a.sav"), entry("Game/b.sav"), entry("Game/same.sav")]
    after = [entry("Game/a.sav", "b" * 64), entry("Game/c.sav"), entry("Game/same.sav")]
    assert file_changes(before, after) == [
        {"path": "winLocalAppData/Game/a.sav", "change": "changed"},
        {"path": "winLocalAppData/Game/b.sav", "change": "removed"},
        {"path": "winLocalAppData/Game/c.sav", "change": "added"},
    ]
    many = [entry(f"Game/{n:03d}.sav") for n in range(250)]
    assert len(file_changes([], many)) == 200  # capped, so a huge save cannot flood the screen


def test_conflict_details_name_this_device_and_show_when_its_save_changed(pair):  # noqa: F811
    a, b = pair

    async def go():
        await a.app.update_game_config(a.key, {"enabled": True})
        (a.saves / "slot.sav").write_bytes(b"from a")
        await a.app.sync_push(a.key)
        (b.saves / "slot.sav").write_bytes(b"from b")
        os.utime(b.saves / "slot.sav", (1_790_000_000, 1_790_000_000))
        await b.app.update_game_config(b.key, {"enabled": True})
        await b.app.sync_pull(b.key)
        return await b.app.conflict_details(b.key)

    details = run(go())
    local, cloud = details["sides"]
    assert local["device"] == "Handheld B" and cloud["device"] == "Handheld A"
    assert local["created"] == "2026-09-21T14:13:20Z"  # the file's own time, not "now"
    assert local["changes"] == [{"path": "winLocalAppData/ExampleQuest/slot.sav", "change": "added"}]
    assert cloud["changes"] == local["changes"]  # no shared base: every file is new on both sides


# Checkpoints


def test_a_checkpoint_is_a_new_pinned_labelled_snapshot_even_without_changes(app_and_save):  # noqa: F811
    app, _saves, _ = app_and_save

    async def go():
        plain = await app.snapshot_game(KEY)
        checkpoint = await app.snapshot_game(KEY, "  Before the   final boss ")
        again = await app.snapshot_game(KEY)  # nothing changed since: no new snapshot
        return plain, checkpoint, again, await app.list_snapshots(KEY)

    plain, checkpoint, again, listing = run(go())
    assert checkpoint["status"] == "published" and checkpoint["snapId"] != plain["snapId"]
    assert again["status"] == "no-change"
    by_id = {s["snapId"]: s for s in listing["snapshots"]}
    assert by_id[checkpoint["snapId"]]["label"] == "Before the final boss"
    assert by_id[checkpoint["snapId"]]["pinned"] is True
    assert by_id[plain["snapId"]]["label"] is None and by_id[plain["snapId"]]["pinned"] is False


@pytest.mark.parametrize("bad", ["", "   ", "x" * 61, "line\x07bell"])
def test_checkpoint_names_are_one_short_line(bad):
    with pytest.raises(ValueError, match="name"):
        checkpoint_label(bad)


# Partial restore


def test_partial_restore_previews_then_changes_only_the_chosen_files(app_and_save):  # noqa: F811
    app, saves, _ = app_and_save
    (saves / "slot2.sav").write_bytes(b"slot two, old")

    async def go():
        old = await app.snapshot_game(KEY)
        (saves / "slot1.sav").write_bytes(b"chapter 9")
        (saves / "slot2.sav").write_bytes(b"slot two, new")
        (saves / "slot3.sav").write_bytes(b"brand new")
        await app.snapshot_game(KEY)
        preview = await app.restore_preview(KEY, old["snapId"])
        before = sorted(os.listdir(saves))
        restored = await app.restore_snapshot(KEY, old["snapId"], ["winLocalAppData/ExampleQuest/Saves/slot1.sav"])
        listing = await app.list_snapshots(KEY)
        return old, preview, before, restored, listing

    old, preview, before, restored, listing = run(go())
    assert sorted((c["rel"], c["action"]) for c in preview["changes"]) == [
        ("ExampleQuest/Saves/slot1.sav", "replace"),
        ("ExampleQuest/Saves/slot2.sav", "replace"),
        ("ExampleQuest/Saves/slot3.sav", "delete"),
    ]
    assert before == sorted(os.listdir(saves))  # the preview changed nothing
    assert restored["status"] == "restored-partly" and restored["prerestore"]
    assert (saves / "slot1.sav").read_bytes() == b"chapter 1"
    assert (saves / "slot2.sav").read_bytes() == b"slot two, new"  # not chosen: untouched
    assert (saves / "slot3.sav").read_bytes() == b"brand new"  # not chosen: not deleted
    assert not any(s["base"] and s["snapId"] == old["snapId"] for s in listing["snapshots"])  # a mix: base kept


def test_partial_restore_can_be_undone(app_and_save):  # noqa: F811
    app, saves, _ = app_and_save

    async def go():
        old = await app.snapshot_game(KEY)
        (saves / "slot1.sav").write_bytes(b"chapter 9")
        restored = await app.restore_snapshot(KEY, old["snapId"], ["winLocalAppData/ExampleQuest/Saves/slot1.sav"])
        await app.undo_restore(KEY, restored["prerestore"])

    run(go())
    assert (saves / "slot1.sav").read_bytes() == b"chapter 9"


@pytest.mark.parametrize(
    "paths", [[], "winLocalAppData/x", ["nowhere/x.sav"], ["winLocalAppData/../escape.sav"], ["winLocalAppData/"]]
)
def test_partial_restore_paths_are_checked(paths):
    with pytest.raises(ValueError):
        restore_paths(paths)


# Activity


def test_activity_turns_log_records_into_plain_sentences_newest_first():
    records = [
        {"ts": "2026-11-18T10:00:00Z", "level": "info", "event": "app.start", "fields": {}},
        {
            "ts": "2026-11-18T10:01:00Z",
            "level": "info",
            "event": "sync.pull",
            "fields": {"gameKey": "example-quest", "action": "restored"},
        },
        {
            "ts": "2026-11-18T10:30:00Z",
            "level": "info",
            "event": "sync.push",
            "fields": {"gameKey": "example-quest", "status": "published"},
        },
        {
            "ts": "2026-11-18T11:00:00Z",
            "level": "info",
            "event": "sync.push",
            "fields": {"gameKey": "unknown-game", "status": "quarantined"},
        },
        {
            "ts": "2026-11-18T11:05:00Z",
            "level": "warning",
            "event": "sync.resolve",
            "fields": {"gameKey": "example-quest", "choice": "use-local"},
        },
        {
            "ts": "2026-11-18T11:06:00Z",
            "level": "info",
            "event": "sync.push",
            "fields": {"gameKey": "example-quest", "status": "no-change"},
        },
    ]
    names = {"example-quest": "Example Quest"}
    entries = activity.build(records, lambda key: names.get(key, key))
    assert [e["text"] for e in entries] == [
        "Kept this device's save of Example Quest. The other one is pinned in History.",
        "Held back a save of unknown-game that looked broken; it is waiting for you to check it.",
        "Saved Example Quest to the cloud.",
        "Brought in the newer save from another device for Example Quest.",
    ]
    assert entries[0]["level"] == "warn" and entries[2]["level"] == "info"
    assert entries[0]["time"] == "2026-11-18T11:05:00Z"
    assert len(activity.build(records * 50, lambda key: key, limit=3)) == 3


def test_the_app_lists_activity_from_its_own_log(app_and_save):  # noqa: F811
    app, _saves, _ = app_and_save

    async def go():
        await app.snapshot_game(KEY, "Checkpoint one")
        return await app.activity(10)

    entries = run(go())
    assert entries[0]["text"] == "Saved a checkpoint of Example Quest."


def test_run_helper_is_asyncio():
    assert run(asyncio.sleep(0, "ok")) == "ok"
