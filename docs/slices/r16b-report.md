# R16 step 2 report: take the newest save (v0.38.0)

Step 2 of Peter's several-save-locations request. The decisions are in ADR-0080, an opt-in exception to principle 4.

## What changed

- **The decision:** `keepsake/newest.py`. It is pure and guarded: exactly two versions, both times known, neither more than 5 minutes in the future, and at least 2 minutes apart. Anything else asks, with the reason.
- **The "When saves differ" setting** (`conflictPolicy`): "ask", the default, or "newest". It is in Settings, Sync and safety, and in the desktop app's Settings.
- **The app:**
  - Every place that announced a conflict now goes through `_conflict_raised`: launch, exit, the idle pass, and manual pull and push. With "newest", it settles the conflict in a background task (`take_newest`), using the same `resolve` as the user's choice.
  - A toast names the version kept and the margin.
  - The choice is recorded for **Undo** (`undo_newest`, an ordinary restore).
- **History:**
  - a "Keepsake took the newer save" card with Undo;
  - "In: …" on each snapshot when there are several save locations (`snapshot_locations`).
- **Principle 4 in `CLAUDE.md`** now notes the exception.

## Not done, and why

- **Several versions at once:** these still ask. Ordering three or more versions by device clocks is not safe enough.
- **The desktop app's History** does not show locations yet. It is planned with the desktop History table.

## Tests

- **New:** `tests/test_newest_save.py`, 17 tests.
  - **The rules:**
    - the newer side wins;
    - five guard cases ask instead: too close, the other clock fast, this device's files dated ahead, an unknown time, three versions;
    - the edges just inside the guard;
    - zones in times.
  - **Two simulated handhelds sharing one store:**
    - the newer save from the other device is taken, and Undo brings mine back, once;
    - a device with a fast clock never wins by it;
    - this device's newer save is kept;
    - saves too close in time are left to you;
    - "Ask me" is the default and never takes anything;
    - with "newest" set, a manual pull settles it by itself;
    - with "Ask me", a conflict is announced and left;
    - History shows which locations hold each snapshot;
    - the setting is checked.
- **Regression:** these pass, with 1 skipped (POSIX file modes):
  - `tests/test_app_ux.py`
  - `tests/test_save_safety.py`
  - `tests/test_sync.py`
  - `tests/test_sync_invariant.py`
  - `tests/test_sync_plan.py`
  - `tests/test_settings.py`
- **Mutation tests:** 11 mutations. 2 survived, the "Ask me" branch and clearing the Undo record, and led to new tests. Now all are caught.

## Threat model

T145.

## On-device checklist

`docs/device-run.md` part 4, step 28.
