# ADR-0011: Cross-device game matching

- Status: accepted (requested by Peter on 15 November 2026; design chosen under his delegation)
- Date: 15 November 2026
- Deciders: Peter (owner)

## Context

A game's identity across devices is its game key. Compatdata numbers never enter into it, so a differently numbered prefix is not a problem in itself. The weak point was how the key was found: only the Ludusavi manifest title (Steam ID, normalised name, aliases or a manual pick). A shortcut named differently on each device ("Example Quest" and "ExQuest (ISO)"), or a game the manifest does not know, could not be linked to the other device's copy without manual work.

Existing tools: Ludusavi matches by store ID, title and the manifest's `installDir` folders; folder-scanning backup tools look for known save folders. None compares what another device has synced.

## Decision

1. **Signals.** Four independent signals, scored separately (`keepsake/identity.py`):
   - *exe*: the shortcut's executable name equals a manifest `launch` executable (now kept in the index, schema 2) or the exe another device recorded. Common names (`game.exe`, `launcher.exe`, `UnityCrashHandler64.exe` and similar) score 0.5 instead of 3.
   - *folder*: a non-generic folder on the way to the game (inside `drive_c`, or the last two folders outside a prefix) equals a manifest `installDir` or a folder another device recorded (3).
   - *name*: equal normalised names (3) or mostly shared words (1).
   - *saves*: at least half of the save folders another device syncs for that game exist inside this game's own logical roots (4; some of them, 2). This is the strongest signal and works without the manifest.
2. **Identity records.** After its first successful push of a game, each device writes a write-once record to `games/<gameKey>/identity/<deviceId>.json`: schema version, game key, device ID, manifest title if any, exe file name, normalised install folder names, normalised shortcut name and save folders as `root/folder/folder`. No absolute paths, usernames or compatdata IDs (principle 10).
3. **Automatic matching** happens only when the best candidate scores at least 6, has at least two strong signals, leads the runner-up by at least 3, and its key is not already used by another game on this device. It is recorded as `gameKeySource: auto` and shown on the game page with the evidence, so the user can change it. Steam apps keep matching by Steam ID.
3a. **Uncertain matches ask for approval** (Peter, 15 November 2026). When the automatic rule declines but a candidate scores at least 3 (including ties and fuzzy title matches), Keepsake proposes it: a one-off toast, a "Confirm match" note in the Games list with a count of matches awaiting approval, and an approval card on the game page with **Approve**, **Choose another** (the alternatives, or a manifest search) and **Not this game**. "Not this game" is remembered per game, so that candidate is not proposed again; the next best one may be. Proposals are stored locally in `match-proposals.json` and cleared when the game is matched any other way.
4. **Game keys without a manifest entry.** A game can be given its own key ("Give it its own game key", from its name) and sync through custom folders. Snapshots need a game key and at least one known save location (manifest or custom); otherwise they still fail closed.
5. **Safety.** A wrong automatic match cannot silently overwrite saves: the sync decision table raises an adoption conflict when local files differ, and a restore into an empty prefix only adds files (which the pre-restore snapshot and pins keep reversible).

## Consequences

- One small extra cloud object per device and game; the cloud layout gains `identity/` (backwards compatible, readers ignore unknown objects).
- Identity records are read with one listing of `games/`; results are cached for ten minutes and matching falls back to the manifest alone when offline.
- Records are written once, so a record can become stale if a game is reinstalled elsewhere; the other signals and manual choice still apply.
