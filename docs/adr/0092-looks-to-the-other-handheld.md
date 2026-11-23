# ADR-0092: Looks to the other handheld: an offer kind Replication carries for another module

- Status: accepted (R29 stage 1b; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

The R29 research and ADR-0091 call for syncing themes, sound packs and boot and sleep videos between the user's handhelds. Haversack already moves games and emulator games between paired devices (ADR-0087). Each of those added its own code to Replication's offers.

Looks is a separate module, and P13 says modules depend on Core and never on each other's internals. Two rules are escalation items:
- a new peer request changes the peer protocol;
- a write into `<homebrew>/themes` or `<homebrew>/sounds` falls outside the write allowlist.

## Decision

1. **An offer kind another module owns.** Replication's `Incoming` takes `kinds`, a map from kind to a handler with three methods:
   - `validate(raw)`: the clean offer and its title;
   - `targets(offer, id)`: where each part is staged;
   - `finish(offer, staged)`: puts the parts in place and reports placed, skipped and reason.

   The sending side gets a generic `Outgoing.prepare_parts(kind, title, {part: (root, members)})`. Replication carries the offer and the copy, and the Looks module (`looks/lookplan.py`) owns what the offer means. The app wires them together (Core), so neither module imports the other's internals. Later R29 stages can reuse it.
2. **Protocol addendum: `looks-offer`.** The request carries `{kind: "looks", id, shares: {part: {share, root, bytes, members}}, from: {name}}`.
   - The parts are `themes`, `sounds` and `animations`.
   - Members are top-level names only, checked against a strict pattern: no slashes, no leading dot, at most 120 characters and at most 300 of them.
   - Videos must be one of Steam's three file names.
   - `root` is a content hash. No paths, user names or labels cross the wire (P10).

   A device without the kind answers with an error, which the sender shows as "needs Haversack 0.55 or later". Existing requests are unchanged.
3. **What is sent.**
   - **Themes:** folders with a `theme.json`.
   - **Sound packs:** folders with a `pack.json`.
   - **Videos:** only those Haversack set on the sender, never a video another tool put there.

   Links are not offered. Only the chosen members are shared, through `only()`, as emulator games do.
4. **Write allowlist addendum.** On the receiver, new folders are written in three places:
   - `<homebrew>/themes/<new name>`;
   - `<homebrew>/sounds/<new name>`;
   - Haversack's own `looks/animations/From <device>`.

   Each part is staged beside its destination (`.haversack-looks-<part>-<offer>`), then moved in name by name. The rules:
   - only names the offer listed are moved, and nothing that exists is replaced;
   - the staging folder is removed;
   - nothing is written unless the receiver has Looks switched on.

   The receiver's screen never changes by itself: received videos are only choices on its Looks page.
5. **The same flow as other offers.** Offers start copying by themselves (ADR-0072). A receiver with Looks off fails the offer with "switch on Looks", and nothing is copied.

Alongside this, the emulator sender now reads the error `reason` the link sends, so the other device's own message is shown instead of a generic "refused it".

## Consequences

- The Looks page gains **Send to your other handheld**, in Gaming Mode and the desktop app.
- **Threat model:** T164.
- **Device run:** step 53.
