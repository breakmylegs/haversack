# R16 report: several save locations (step 1 of 2)

Recorded in ADR-0071 (Peter's request of 21 November 2026). Step 2, taking the newest save when locations differ, follows as ADR-0072.

## What changed

- **`keepsake/store/multi.py`:**
  - `MultiStore`: writes to every location, reads from the first that has the object, lists the union, deletes everywhere;
  - per-game routing;
  - a local copy of write-once history (snapshots, pruned markers, bases);
  - `catch_up` (bounded; never copies pruned or orphan blobs; removes lingering pruned blobs);
  - `LocationState` (last success, problem, objects still to copy, space used).
- **Settings and game config:** `snapshotStores` (empty means `snapshotStore` alone), and a game's `locations`.
- **App:**
  - one location keeps the single store; several get a `MultiStore`;
  - `locations_status`, `add_location`, `remove_location` and `set_game_locations`;
  - catch-up in the idle pass and on adding a location;
  - direct sync whenever "direct" is a location.
- **Interface:**
  - the Cloud page lists save locations with status and Remove, and "Add ... as a save location";
  - a game's page has **Save locations for this game** when there are several.
- **Docs:** ADR-0071, T130, the cloud guide, CHANGELOG, device run part 4 step 8.

## Found on the way

The simulator test with two locations dropping out in turn caught a real problem. A push while the location holding the base was down published a snapshot with no parent, which later showed as a false fork. The fix keeps a local copy of write-once history (ADR-0071 point 4), and the test now passes.

## Tests

- `tests/test_multistore.py`, 11 tests:
  - writes everywhere, with one view for reads and lists;
  - one location down never blocks; none answering is "unavailable";
  - catch-up never brings back pruned or orphan blobs; per-game routing;
  - bounded catch-up, with large objects copied through a file; error reporting;
  - history seen stays visible while its location is down;
  - **two devices in step while each location drops out in turn**, and play with every location down;
  - the app's single and union stores, adding, removing, the older single choice, and game location validation.
- **Regression:** `test_settings.py`, `test_gameconfig.py`, `test_app_sync.py`, `test_app_cloud.py`, `test_app_backends.py`, `test_directsync.py`, `test_save_safety.py`, `test_sync.py`, `test_host.py`, `test_storage.py`.
- **Mutation:** 25 mutants of the union store, catch-up, the history cache, routing, the app's location rules and validation. All are killed after two sharper tests were added.

## Known gaps

- Taking the newest save on a real fork, the clock guard, and History showing locations are step 2 (ADR-0072).

## On-device checklist

- `docs/device-run.md` part 4 step 8.
