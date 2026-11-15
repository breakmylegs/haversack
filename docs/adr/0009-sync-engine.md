# ADR-0009: Sync engine decisions

- Status: accepted (decided in slice 7 under the owner's delegation, 15 November 2026)
- Date: 15 November 2026
- Deciders: Peter (owner)

## Context

Slice 7 implements the decision table in build prompt section 9: adoption, pull before launch, push after exit, forks, merges, conflicts, the offline queue, prefetch staging and the idle pass. Some details are left open by the build prompt.

## Decisions

1. **Heads** are snapshots no other snapshot names as a parent. Every decision compares content hashes and parent links only; timestamps never choose (principle 4). Skewed device clocks are part of the simulator.
2. **Adoption** (no base on this device): no cloud snapshots, launch; one head and no local files, restore it; one head with the same content hash, adopt silently; otherwise an adoption conflict. Several heads are always a fork conflict (adopting a matching head as the base first, if there is one).
3. **Converged edits.** If both sides changed but now have identical content, the head is adopted silently; there is nothing to choose between.
4. **Use cloud save** keeps this device's files as a pinned snapshot (flag `conflict-loser`), restores the chosen head (with a verified pre-restore snapshot), then publishes a **merge** snapshot with the chosen content whose parents are every current head, so history converges to one head. Every losing head is pinned. (The build prompt describes the first two steps; without the merge, the kept copy and the losing head would stay as heads and raise the same conflict again.)
5. **Use this device's save** publishes a merge snapshot with this device's files and every head as parents, and pins the losing heads.
6. **Losers are pinned for 90 days** (the build prompt asks for at least 30). Metadata stays forever, so ancestry checks keep working after a blob is pruned.
7. **Explicit choices skip the safety gates.** A merge the user chose is published even if it removes many files compared with the cloud, because the user confirmed it; the losing side stays pinned. Automatic pushes always pass the gates.
8. **Decide later** leaves the conflict open: launches use the local save, automatic restores stay off for that game, and exit pushes upload as a fork so nothing is lost.
9. **Push when the head moved during play** uploads with `parent = base`, creating a fork, then raises a conflict (data safe in the cloud rather than blocking).
10. **Never synced but the cloud has history**: an exit push uploads (a new root, so nothing is lost) and raises an adoption conflict rather than guessing a parent.
11. **Offline and errors.** A store that is unreachable at launch marks the game pending and lets it start; exit pushes that fail stay pending; the idle pass reconciles with the normal decision table. A game whose cloud metadata has a newer schema is never written.
12. **Cloud newer while the game already runs** (could not be frozen): no restore; the game is marked pending (section 10).
13. **Device bases** are published to `games/<gameKey>/bases/<deviceId>/<deviceSeq>.json` whenever the base changes, best-effort (retried by the idle pass); retention protects every device's newest base.
14. **Prefetch** downloads heads newer than the base into `staging/<gameKey>/<snapId>.zip`, verified; a launch restore uses the staged copy. Staging is a local cache and pruned to current heads.
15. **Idle pass** every 30 minutes (first pass a minute after start-up) for games with "Sync this game" on: crash recovery for sessions left open, base publishing, prefetch, offline reconciliation, and a push of changes made while the plugin was not running. Games are opt-in.
16. **Game config revisions** (`config/` in the cloud layout) are deferred to slice 9 with the per-game page.

## Consequences

- Resolving a conflict always creates at least one new snapshot (the merge) and pins; storage use grows slightly, bounded by retention after the pins expire.
- The two-device simulator and the randomised no-loss invariant are the main protection against regressions here.
