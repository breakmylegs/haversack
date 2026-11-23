# ADR-0096: The SD card game index, read only

- Status: accepted (R29 stage 4; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

R29's research recommends, for utilities:
- **Adopt:** an SD card game index (as in MicroSDeck, which is GPL-2.0 and not used here), clearing orphaned compatdata, one-tap Bluetooth connect, and link speed.
- **Later:** a screenshot backup.

Haversack already reasons about SD card labels for saves (canonical roots).

## Decision

1. **Device, Storage lists every SD card and drive Steam knows, with its games.** Cards in the device come first, and a card that is out says when it was last seen.
   - **The source is Steam's own `libraryfolders.vdf`:** each library's `path`, `label`, `contentid` (the key, which stays with the card) and `apps`. The internal library is left out.
   - **While a card is in,** names come from its app manifests, and non-Steam games are included when their program's resolved path is on the card. Haversack keeps the names in its own `sdcards.json`, so a card that is out still shows them. Tools such as runtimes are left out.
2. **Read only.** Nothing on the card or in Steam's files is changed. It is in Core, because it is information about this device's storage.
3. **Privacy.** Card labels and game names stay on the device. They are shown here and never sent to the cloud or peers (P10).
4. **The rest of the utilities area:**
   - **Orphaned compatdata:** not added. A prefix with no installed app may still hold a non-Steam game's saves, which Saves owns (P14). The existing prefix tools in Storage are safer.
   - **One-tap Bluetooth:** already covered by Reconnect help's quick menu buttons.
   - **Link speed:** already a Device check (ADR-0062).
   - **The screenshot backup:** stays in the plan.

## Consequences

- **Threat model:** T167.
- **Assumptions:** A250.
- **Device run:** step 57.
