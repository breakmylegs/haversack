# ADR-0071: Several save locations at once

- Status: accepted (Peter's request of 21 November 2026, decided under ADR-0037). Step 1 of 2: this ADR covers using several locations; taking the newest save when they differ, with its clock guard, is ADR-0072.
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

`snapshotStore` is one choice: local, OneDrive, WebDAV, S3, Google Drive, or directly between devices. Peter wants:
- several locations at once (for example OneDrive, plus direct between his devices, plus a WebDAV NAS);
- each game able to use some of them, all by default;
- every push to go to every location the game uses, with an unreachable location caught up later and never blocking the others or a launch;
- one view of every location on pull;
- the Cloud page to list each location with its status, and add, remove and sign in to each, with removing never deleting what is stored there;
- nothing to change for anyone with one location.

## Decision

1. **Settings.** `snapshotStores` is a list; empty means `[snapshotStore]`.
   - The list counts only while its first entry equals `snapshotStore`. If something older (an earlier page, or the desktop app's single choice) sets `snapshotStore` to something else, that single choice wins.
   - Existing installs change nothing until a second location is added.
   - A game's `locations` setting is a list, or `null` for all.
2. **One location means today's code path:** the single store, unchanged.
3. **Several locations: `MultiStore`** (`keepsake/store/multi.py`), one store made of several. This is safe because every key is either content-addressed (blobs), unique per snapshot, or scoped to one device (bases, config revisions, playtime, identity, registry), so the same key in two locations always holds the same object (principle 2).
   - **Write:** to every location the key's game uses. It succeeds if at least one took the object or already had it; the others are caught up later. Only when no location answers does it fail as unavailable, and the existing offline queue keeps the save, so a launch is never blocked.
   - **Read:** from the first location that has the object. Not found in the locations that answered while one did not answer is "unavailable", never "not found" (P5).
   - **List:** the union of every location that answers, plus the local copy of history below.
   - **Delete** (retention only): wherever the object is.
4. **Known history stays known.** Snapshot metadata, pruned markers and base records are written once and never deleted; retention removes only blobs. So each one written or read is kept under `<runtime>/locations-history/`.
   - Without this, a push while one location is down could miss its base, publish a snapshot with no parent and start a false fork. The simulator test "two devices stay in step while each location drops out in turn" found exactly that.
   - History another device wrote only to the location that is down stays out of view until it is back, and then the normal rules apply.
5. **Catch-up**, in every idle pass and when a location is added:
   - copies to each location what another has and it lacks, at most 200 objects a pass, large blobs through a temporary file;
   - never copies a blob retention pruned (a `pruned` marker anywhere), nor an orphan blob without its snapshot;
   - deletes a pruned blob that a location kept while it was away;
   - respects each game's chosen locations.
6. **Per-location status** in `<runtime>/locations.json`: last success, last problem, objects still to copy, and space used. The Cloud page shows them with **Remove** for each, which never deletes anything stored there, and "Add *X* as a save location", checked first for clouds (the same create-only check as before). A game's page shows **Save locations for this game** when there are several.
7. **Direct device sync (ADR-0061)** runs whenever "direct" is one of the locations.
8. **What does not change in this step:** a real fork is still a conflict for the user, as today. ADR-0072 adds taking the newest.

## Consequences

- Extra locations mean extra copies of every snapshot. Retention runs on the union view, so each location keeps the same history.
- A location left switched off for a long time catches up 200 objects a pass, in the background.
- T130 in `docs/threat-model.md`.
