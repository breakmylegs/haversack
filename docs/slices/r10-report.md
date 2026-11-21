# R10 report: Uninstall

Recorded in ADR-0065, which extends ADR-0015 (Peter's request of 21 November 2026).

## What changed

- **`keepsake/uninstall.py`:**
  - the guards (`prefix_problem`, `folder_problem`, `recheck`);
  - the plan, with sizes and free space after;
  - `delete_tree`: bottom up, never follows links, Stop between files, progress.
- **App:**
  - `uninstall_plan`, `uninstall_start`, `uninstall_steam`, `uninstall_status`, `uninstall_cancel`;
  - the background job, which holds the game's lock throughout: backup, then shortcut, then folders, then records;
  - Steam op results now wake a waiting job.
- **Steam Operations Executor:**
  - `remove-shortcut` takes `clearArtwork` and reads back through `appStore`;
  - new `open-uninstall` (`OpenUninstallWizard`).
- **`GameConfigStore.remove`, `Installer.forget_appid`.**
- **Interface:** `UninstallPanel` on each Steam and non-Steam game's page, with the confirmation screen (Cancel first) and progress with Stop.
- **Docs:** ADR-0065, T124, A203 to A205, FAQ, CHANGELOG, device run part 4 step 3.

## Decisions taken under ADR-0037

- A refused folder is kept and reported, and the rest of the uninstall goes ahead. The alternative, refusing the whole uninstall, would leave a half-useful game behind for no gain.
- A final backup that cannot reach the store stops the uninstall. The user may then choose to go on without one.
- No Uninstall in the desktop app: shortcut removal needs the Gaming Mode frontend.

## Tests

- `tests/test_uninstall.py`, 54 tests (plus 1 POSIX-only, symlinks):
  - **Prefix guard and install folder guards:** protected folders, each home folder by name, outside places, shared folders, links, mount points and odd paths.
  - **Plan:** sizes, free space after, a game inside its prefix, kept reasons, and the check again before deleting.
  - **Deletion:** progress, Stop, and links.
  - **App order:**
    - nothing is deleted before Steam removes the shortcut, or when Steam still lists it or never answers;
    - a failed backup stops everything, and a successful one says where to restore from;
    - skip and Stop, including Stop during the backup;
    - a folder gone by deletion time, and a folder shared with another shortcut;
    - refusals (running, streaming, kind), Steam games through Steam's wizard, and clearing records.
- `tests/test_installer.py::test_forget_appid_removes_only_finished_installs_of_that_game`.
- **Regression:** `test_installer.py`, `test_gameconfig.py`, `test_remote_copies.py`, `test_modules.py` (the Steam ops queue).
- **Mutation:** 44 mutants of every guard, the plan, deletion and the app's order of work. All are killed.
  - The test for home folders lists them itself, so dropping one from the module fails.
  - Two conditions turned out to be covered by other guards and were removed rather than kept as dead code: library roots in the protected list (covered by `steamapps`), and the explicit "not the root itself" check (roots are protected).

## Known gaps

- What Steam does after `RemoveShortcut` (A203), the focus on Cancel (A204) and Steam's wizard (A205) are unverified until the device run.

## On-device checklist

- `docs/device-run.md` part 4, step 3.
