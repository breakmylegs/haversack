# ADR-0020: Gaming Mode UX, shared game settings and health checks

- Status: accepted (slice 9, decided under Peter's delegation)
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: build prompt sections 9, 14 and 15; `docs/build-prompt-v2.md` section 10 (slice 9 amendment)

## Context

Slice 9 completes the Gaming Mode interface: the Quick Access Menu panel, the full-screen tabs, the setup wizard, the conflict modal, toasts and the health checks. It also delivers the game config revisions deferred from slice 7 (ADR-0009, item 16) and the v2 amendment that the navigation is ready for module tabs.

## Decision

1. **Game config revisions.** Shared fields are `aliases`, `includeConfig`, `customPaths` and `exclusions`: the settings that describe where a game's saves are, in canonical form (`{root, rel}` paths and globs). The match override, game key, enable switch and launch gate stay per device, because shortcut names, app IDs and the user's choices differ per device. Each change to a shared field of an enabled game is published as `games/<gameKey>/config/<seq>-<deviceId>.json` (the frozen layout), where `seq` counts this device's revisions for that game. The body holds schema version, game key, device ID and name, sequence, creation time, `basedOn` (the revision applied when the change was made) and the shared fields. The newest revision by creation time applies everywhere (build prompt section 9 allows timestamps for config, principle 4 covers save data only). Two revisions from different devices with the same `basedOn` are concurrent edits: the newest applies and the game page names the other device. Invalid, foreign or newer-schema revisions are ignored. A change made offline stays pending and is published by the idle pass; while it is pending, remote revisions are not applied over it. Enabling a game first fetches the newest revision, so a second device picks up the first device's custom paths.
2. **Conflict modal.** A modal (`ModalRoot`) whose `onCancel` (B button, background) is "Decide later", with initial focus on "Decide later" (`preferredFocus`). "Use cloud save" and "Use this device's save" need two presses: the first press only arms the choice and changes its label. Each side shows device, time, file count, size and the number of files changed since the last sync (by path and hash). Closing the modal in any way leaves the conflict open.
3. **Setup wizard** at its own route, shown from the QAM until `setupComplete`. Steps follow section 14. The dry run uses `SyncEngine.plan`, a read-only copy of the decision table, so it changes nothing. Installs that already have enabled games are marked as set up on start.
4. **Steam apps** are hidden from the Games list and the wizard unless Settings, "Show Steam games" is on. They can still be enabled one by one. Non-Steam shortcuts are always listed.
5. **Health checks** are a pure function over facts the app gathers (`keepsake/health.py`). Opening Diagnostics runs them without network; "Run checks" also tests OneDrive. The QAM badge is the worst status. decky-ludusavi is detected read-only from Decky's plugin folders and `disabled_plugins`; its per-game settings format is unknown, so the check warns whenever it is active alongside synced games.
6. **Navigation.** Tabs are a list tagged by module (`saves` or `core`), so later modules add entries. Settings shows a Modules placeholder until slice 13.
7. **Toasts** added: conflict and quarantine from the idle pass, and "sign-in needs attention" once per outage.
8. **Idle interval** is a setting (10 to 240 minutes, default 30).

## Consequences

- One small cloud object per settings change per game. Revisions are never deleted (principle 2); retention does not cover them, which is acceptable at their size.
- The quarantine flag in sync state is now cleared when a quarantined snapshot is released or a later good save is pushed, so status icons and health checks do not stay stuck.
- Device names appear in config revisions, as they already do in snapshots and the device registry.
