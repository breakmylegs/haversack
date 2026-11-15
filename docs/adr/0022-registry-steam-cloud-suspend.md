# ADR-0022: Registry keys, Steam Cloud detection and suspend snapshots

- Status: accepted (slice 11, decided under Peter's delegation)
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: build prompt sections 8, 9, 10 and 16 (slice 11), threat model T15; `docs/build-prompt-v2.md` section 10 (slice 11 amendment)

## Context

Some games keep save data in the Wine registry rather than in files. Steam apps usually have Steam Cloud and should be left alone unless they do not. A device that sleeps mid-game holds unsaved progress that a later push would capture, but only if the device wakes up.

## Decision

1. **Registry: keys as a snapshot file.** For a game whose manifest entry lists `HKEY_CURRENT_USER` keys, and only when the game opts in ("Sync registry keys", off by default, shared between devices because both must agree on what a snapshot holds) and the global "Registry keys" setting is on, Keepsake exports those keys and their subkeys from `<pfx>/user.reg` into a canonical fragment in its runtime folder, stored in the snapshot as `registry/user.reg`. The fragment is the Wine format without timestamps or `#time` lines, so the same values always hash the same. `registry` becomes a snapshot root (not a root custom paths can use). Save-tagged keys are synced; config-tagged keys only when the game includes config files. `HKEY_LOCAL_MACHINE` keys are not synced.
2. **Registry: merging after a restore.** After any restore (before launch, conflict choice, History restore or undo), the restored fragment is merged into `user.reg`: managed keys are replaced by the fragment's, every other key stays byte for byte. A snapshot without a fragment changes nothing. The merge is refused while the game runs.
3. **Registry: a corrupt merge is impossible by construction.** The current file must parse; the result must re-parse, keep every unmanaged key unchanged and hold exactly the fragment's managed keys; a fragment with keys Keepsake does not manage is refused; a copy of the original goes to `runtime/registry-backups/<gameKey>/` (last five kept); the new file is written beside the original, flushed and atomically renamed, then read back and put back if it does not match; if Wine changed the file meanwhile, nothing is written. A merge whose keys already match writes nothing. If the merge fails after the files were restored, the files stay restored, the registry stays as it was, and the user is told; the pre-restore snapshot holds the previous fragment for undo.
4. **Core service (v2 amendment).** `registry.set_values(path, key, values)` sets raw values in one key of any Wine `.reg` file through the same guarded write, for the Installer's drive type in v2. Not used by the UI yet.
5. **Steam Cloud detection.** Read-only: `userdata/<id3>/<appid>/remotecache.vdf`, or a non-empty `remote/` folder, means the app uses Steam Cloud; a played app with neither has no Steam Cloud saves; an unplayed app is unknown. Steam apps are labelled, and "Sync them all" enables matched, played Steam apps without Steam Cloud. Behind "Detect Steam Cloud" (on by default).
6. **Suspend snapshots.** When the Steam client announces a suspend (`SteamClient.System.RegisterForOnSuspendRequest`) and "Snapshot when the device sleeps" is on (off by default), Keepsake takes a `provisional` snapshot (flag `suspend`) of each synced game with an open session, on top of the device's base, through the normal safety gates. Provisional snapshots are never heads and never a base, and their parents do not hide the head they were taken on. Another device's launch check reports the newest provisional snapshot taken on top of the current head and shows a message; it never restores it. The user can restore it from History. The sleeping device's exit save later supersedes it.

## Consequences

- Each feature has its own setting (acceptance item).
- A suspend snapshot needs the cloud to be reachable at the moment of sleep; offline it is skipped.
- Mixed versions: a device older than slice 11 would treat provisional snapshots as heads. Update both devices before turning sleep snapshots on.
- Retention does not protect provisional snapshots (they are not among the kept automatic, manual, merge or import kinds), so a retention run may prune one unless it is pinned. They are meant to bridge a sleep, not to be history.
