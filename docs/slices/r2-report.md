# R2 report: everyday polish

Slice R2 of the post-v2 roadmap (ADR-0047), recorded in ADR-0049.

## What changed

- **Newer save from another device.**
  - **Detection:** the idle pass's prefetch records a single newer head made by another device.
  - **Where it shows:** `match_games` and `qam_summary` carry it.
  - **"Get it now" (`bring_newer`):** applies the launch decision table without opening a session.
  - **Interfaces:** the Gaming Mode Games row and the QAM, plus the desktop Games page and Overview.
- **Combined playtime.**
  - **Recording:** a write-once `games/<gameKey>/sessions/<deviceId>/<seq>-<seconds>.json` per session of 1 minute to 24 hours, recorded at exit.
  - **Offline:** sessions are queued and sent by the idle pass.
  - **Reading:** `game_playtime` gives totals by device from one listing, shown on the Gaming Mode game page.
- **Mains-powered devices.** `keepsake.power` (Linux `power_supply`, Windows `GetSystemPowerStatus`). The device facts carry `battery`. Advisor drops battery estimates on mains, and drops the TDP too without a profile.
- **Accessibility.** Desktop fonts are in `rem`, so the browser text size applies. Status words sit next to icons throughout.
- **What's new and tips.** Both packages ship `CHANGELOG.md`, and the startup notice carries the version's section, shown once as plain text. A dismissible first-run tip appears in the QAM (`tipsDismissed`).
- **Docs:** ADR-0049, T106, A180, A181, the user guide, the changelog, the plan and refreshed screenshots.

## Test results

- `tests/test_everyday_polish.py` (15 new): passed.
- Covering tests passed: `test_app_ux`, `test_sync`, `test_sync_plan`, `test_lifecycle`, `test_advisor`, `test_advisor_2`, `test_settings`, `test_scripts`, `test_host` and `test_save_safety`, 160 in all, with 1 POSIX skip.
- Mutation checks: 17 mutations, all killed after the tests were tightened for 4 first-round survivors.
- `tsc` and eslint clean. The desktop pages were rendered by the screenshot harness.

## Known gaps

- Playtime is not shown on the desktop interface yet.
- Playtime counts only from this version, and only for games with a session start Keepsake saw.
- No Steam Machine or battery-less desktop has been tested (A180, A181).

## On-device checklist (handhelds)

1. **Newer save.** Play a synced game on the Legion Go and quit. On the Legion Go 2, press **Sync now** or wait for the idle sync. Check that the Games row and the QAM say "Newer save from Legion Go". Press **Get it now** and check that the save arrives.
2. **No overwrite.** Repeat, but change the save on the Legion Go 2 first. **Get it now** must report a conflict and change nothing.
3. **Playtime.** After two sessions over a minute long on different devices, the game's page shows the total and each device.
4. **What's new.** After installing the next release through Updates, the What's new window appears once.
5. **Tip.** On a set-up device, the QAM tip appears, and **Got it** removes it for good.
