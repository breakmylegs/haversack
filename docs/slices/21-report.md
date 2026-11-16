# Slice 21 report: Installer I

Branch `slice/21-installer-1`, stacked on `slice/13-module-framework` (#17). v2 spec slice 21. It is taken ahead of slices 14 to 20, which are blocked: 14 and 15 wait for the licence audit sign-off, and 17 to 20 wait for the slice 16 device results. The Installer depends only on Core. Implementation decisions: ADR-0026.

## What changed

- `installer/udisks.py`: mounts an ISO read-only with `udisksctl` (loop-setup, then mount). Unmounts and deletes the loop device afterwards, and straight away when mounting fails.
- `installer/files.py`: lists files, lists new files, finds installer programs (setup first, then autorun), and ranks a game's executables with uninstallers, redistributables and helpers excluded.
- `installer/service.py`: install jobs in the `installer_jobs` table. The flow is choose installer, create the `Install: <Title>` shortcut, run the installer, choose the game's program, retarget the same shortcut, then done. Every Steam change is an executor operation created by a user action.
- `steamops.py` and `src/steamops.ts`: a new `add-shortcut` operation. It creates the shortcut, sets every field again after Steam settles, picks the newest GE-Proton (numeric order) or Proton Experimental, and reads the result back.
- `app.py`:
  - the Installer is now a real module, with health (`udisksctl`) and the installer callables;
  - Core publishes `game_exited` with no `gameKey` for apps Saves does not manage, so the Installer notices when the installer closes;
  - executor results are routed to the module that queued them.
- `settings.py`: `libraryRoot`.
- Frontend:
  - an Install tab, shown only while the module runs (the same now applies to every module's tabs);
  - the Install page has file and folder pickers, the Windows path to type, installer choice, "I have finished installing", program choice with confirmation, Cancel and "Change folder".
- Docs:
  - ADR-0026;
  - threat model: T51 in place, with the accepted risk awaiting sign-off; T46 updated; new T73 and T74;
  - assumptions A129 to A134;
  - README "Installing games", with the not-a-sandbox warning;
  - CHANGELOG 0.21.0 (the version number follows the slice number and can be renumbered at release).

## Acceptance (v2 spec slice 21)

| Requirement | How it is shown |
|---|---|
| An ISO installs into its own prefix, and the shortcut keeps that prefix after retargeting | The ISO flow test: a read-only mount, `STEAM_COMPAT_MOUNTS` on the installer shortcut, and the disc released on failure. The folder flow test: every retarget operation targets the installer shortcut's app ID and clears the launch options. Proving that the prefix is kept needs a device (check 2). |
| The game's executable is found | Ranking test: uninstallers, redistributables and crash reporters are excluded, and the title match comes first. In the flow test, Wine's own files in the prefix are never offered. |
| No Steam change without a user action, and every change is read back | Operations are only queued by `create_shortcut` and `retarget`. The job is `done` only after every retarget operation reports back (checked part way through). |

## Tests

- New: `tests/test_installer.py` (9).
- Re-run because they cover touched code: `test_modules`, `test_settings`, `test_app_ux`, `test_lifecycle`, `test_app`. One expectation in `test_modules` changed: Installer is no longer listed as unavailable. 75 passed and 1 skipped (`posix`) before that update; `test_modules` passed 12 of 12 after it.
- Mutation checks: 15 guards were broken one at a time, all caught. They cover:
  - udisks clean-up when mounting fails;
  - installer ordering and depth;
  - the Wine folder exclusion;
  - clearing launch options on retarget;
  - the ISO mount option;
  - waiting for every retarget operation (missed at first; a test was added);
  - detaching when a job finishes;
  - retargeting only to a listed candidate;
  - matching the exit to the job's app ID;
  - refusing to cancel a finished job;
  - the `Z:` path conversion;
  - `add-shortcut` payload validation;
  - the absolute `libraryRoot`;
  - app routing of executor results.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan).

## Known gaps

- A failed or cancelled install leaves the `Install: <Title>` shortcut in Steam, and the user removes it. Automatic removal comes in slice 22 as a button.
- Zip, rar and 7z sources, multi-disc ISOs and disc swaps are not supported.
- The compatibility tool falls back to the newest GE-Proton until Advisor (slice 14) can recommend one.
- Everything touching Steam, udisks and Proton is unverified until the checks below: A70 to A76, A85 and A131 to A134.
- T51 (malicious installer) is an accepted risk that needs Peter's sign-off.

## On-device checklist

1. Settings, Modules: Installer shows Running, and its health reports `udisksctl` found. Keepsake shows the Install tab.
2. **Folder install:** use a folder holding a small trusted installer (for example a GOG offline installer).
   - Enter a title and choose "From a folder", then "Use setup...".
   - An `Install: <Title>` shortcut appears with GE-Proton.
   - Start it, install to the `Z:\...` path shown, and quit.
   - The Install page lists the game's program within a few seconds. If it does not, press "I have finished installing".
   - Choose the program. The shortcut is renamed to the title, and starting it runs the game with the same `compatdata/<appid>`.
3. **ISO install:** the same steps from an `.iso`. The installer sees the disc, and after Done or Cancel `udisksctl status` shows no Keepsake loop device.
4. Change folder to a folder on the SD card. The next install suggests that path.
5. Switch the Installer off in Modules. The Install tab disappears.
6. Run `pnpm run test:device`.
