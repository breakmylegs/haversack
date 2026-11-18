# R7 report: save sync directly between devices

Recorded in ADR-0061 (Peter's option C, 18 November 2026).

## What changed

- **`keepsake/directsync.py`, Saves' side, which does not import Replication:**
  - handlers for `store-list`, `store-get` (4 MiB parts) and `store-changed`;
  - `exchange`, which copies the save objects the other device has and this one lacks, snapshots last. It honours pruned markers: none is copied back, and a blob is removed here once a marker arrives. An object arriving at the wrong size is not kept.
- **App:**
  - **The store:** `snapshotStore` `direct` is a local store in Keepsake's own folder.
  - **The handlers** are on the Replication listener.
  - **When exchanges run:**
    - before a launch's pull, bounded by half the pull timeout;
    - on the idle pass;
    - when told by the other device;
    - after a push, telling the other device;
    - on **Sync now** (`direct_sync_now`).
  - **The Cloud status** says when no device is paired, and shows the last exchange.
- **Settings:** `snapshotStore` accepts `direct`.
- **Pages:** the Cloud page's **Directly between my devices** choice, with Sync now, in Gaming Mode and on the desktop.
- **Docs:** ADR-0061, T119, A197, the user guide (Cloud), the changelog and the plan.

## Test results

- **The feature:** `tests/test_directsync.py` (16 new). They cover:
  - copying without changing anything here, and nothing fetched twice;
  - every snapshot after its blob;
  - retention deciding for both devices;
  - parts, and a short arrival not kept;
  - refusals (not direct, bad keys, oversized parts, a missing object, a bad list) and the `store-changed` notice;
  - the app's store, status, idle pass and Sync now;
  - an unreachable device never blocking play.
- **Regression for what changed:** `test_settings.py`, `test_app_backends.py`, `test_app_cloud.py`, `test_builtin_clients.py` (the Cloud status), `test_app_sync.py`, `test_lifecycle.py` (the launch, exit, push and idle paths) and `test_host.py`: 83 passed with the feature tests.
- **Mutation checks:** 12 mutations, all killed after one test was added and one was extended.
- **Frontend:** `tsc`, the desktop build and eslint are clean.
- `python scripts/check.py`: all checks passed.

## Known gaps

- Direct sync needs Replication on and the devices paired.
- With no cloud there is no off-site copy (stated on the Cloud page and in the guide).

## On-device checklist

1. Pair the two handhelds (slice 17). On both, choose **Directly between my devices** on the Cloud page.
2. Play a game with Saves on the Legion Go 2 and quit. Within a minute, the Legion Go should have the snapshot: check History, or press Sync now.
3. Start the game on the Legion Go. It should start with the Legion Go 2's save.
4. Turn the Legion Go 2 off. Start and quit the game on the Legion Go. It plays on and notes the device as not reachable.
5. Play on both while they cannot reach each other, then bring them together. Check that a conflict appears, and that resolving it works as with a cloud store.
