# ADR-0072: Games both ways between paired devices, with progress on both

- Status: accepted (Peter's requests of 21 November 2026, decided under ADR-0037). Supersedes ADR-0059 decision 6 ("Nothing is written until the user accepts") for new games, and the "only from a user action" rule on accepting an offer.
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

Peter's requests, for one feature release:

1. **Two-way trust.** Pairing is trust both ways.
2. **A space check before sending.** It should say, for example, "Legion Go 2 doesn't have enough space: needs X GiB, has Y GiB free".
3. **No acceptance on the receiver.**
4. **Progress on both devices**, with Stop and remove on either side.
5. **Toasts on both sides.**
6. **Pull as well as push.** From a "Games on Legion Go" list, press **Get this game**. The flow is the same as a send, but started from the receiving side. The other device allows it automatically and shows a toast.
7. **Progress bars, a must-have.** They show on both devices, in the full Gaming Mode page, in a compact line in the quick access menu, and in the desktop app. Each bar shows:
   - the percentage done, GiB done of the total, speed and time left;
   - the stage: checking space, copying, verifying, adding to Steam, done, or failed with the reason;
   - **Stop and remove**, on either side.

   With several transfers, each gets its own bar. The bar keeps moving while the page is closed and reopened.

### What the code did before

- **Both sides already stored the link key** after pairing (`link.py`). But a send needs connections both ways: the offer goes from the sender to the receiver, and the files come back from the sender to the receiver. Pairing never switched on the listener of the device that started it. Until the user found that toggle, the other device could not send to it, and it could not receive a game.
- **Every new game waited for Accept.**
- **The sending device knew nothing** after the offer. v0.30.2 added states, but no progress.

## Decision

### 1. Pairing makes both devices reachable

When a pairing this device started finishes, its listener is switched on, if it was off, and stays on across restarts (`replicationListener`). A toast says "Paired with Legion Go 2. Games can now go both ways between you."

- **Principle 17 holds.** The listener still serves only paired devices, plus discovery and the rate-limited pairing handshake. It is switched on by the user's own pairing action, never by default.
- **It can be switched off.** "Let other devices reach this one" on the Devices page still does that. Games then go one way only.
- **The other side.** The device that accepted the pairing was listening already.

### 2. The space check before sending

- **The request.** A new `space-check` request carries the bytes each share would carry and the compatibility tool's name. The sending device works the sizes out by walking the same files the manifest would take, with the same exclusions and no symbolic links. It does not hash them, so this takes seconds, not minutes.
- **The receiving device's check** (`Incoming.space_check`) is the one Accept's preflight runs:
  - scopes that share a file system add up;
  - each file system needs the size plus the margin (5 percent or 2 GiB, `policy.space_needed`);
  - a built-in or present compatibility tool needs no space.
- **The answer.** It sends back `ok`, the bytes needed and the bytes free, or a plain reason, for example that no library folder is chosen.
- **The wording.** The sending device stops before reading any file, with "Legion Go 2 doesn't have enough space: needs 41.2 GiB, has 12.0 GiB free".
- **An older Keepsake** answers "unknown request". The send then goes ahead, and its own preflight still refuses a game that does not fit when the copy starts.

### 3. No acceptance for new games

A new game offered by a paired device starts copying as soon as the offer arrives (`KeepsakeApp._auto_accept`). The same checks run as when Accept was pressed:

- nothing is replaced: the install folder must not exist;
- space with margin on each file system;
- every target is recorded before it is made;
- Stop and remove undoes exactly that.

A compatibility tool this device lacks is copied, as Peter asked. Before, that was a choice. A refusal fails the offer with the reason, and v0.30.2's news shows it on both devices.

**Why this is safe enough.** Pairing is the consent: only a device the user paired, by typing its code, can offer. Offers are capped at 16. Copies wait while a game runs or on low battery, as before. A toast says "Factorio is coming from Legion Go". The user can stop and remove it at once, on either device.

**Updates are unchanged.** An update to a game that is already linked changes that game's existing files, so it keeps its per-game rule (automatic or manual) and its "changed on both devices" choice (ADR-0060).

### 4. Getting a game from another device (pull)

All four requests are new types, additive under version 1 (ADR-0059's rule).

| Request | Answer | Notes |
|---|---|---|
| `games-list` | `games`: an `id` (a fresh random token, 16 hex) and a `title` for each non-Steam game that can be sent | Tokens are kept for 15 minutes, for the asking device only. No app ID, key or path goes over the link (P10). |
| `pull-check` with a token | `pull-size`: the title, bytes per share and the compatibility tool | |
| `pull` with a token | `pull-started` | The token is used once. |
| `pull-state` | `pull-state-received` | From the sending device, when it could not send the game, with a reason without paths. |

- **The space check is on the asking side.** The asking device checks its own space with `pull-check`'s sizes before it sends `pull`. It knows its own disks, so nothing is asked twice.
- **The sending side allows it automatically,** because pairing is trust. It runs the same steps as Send: plan, a source checkpoint of the saves, prepare, then offer. Its toast says "Factorio is being copied to Legion Go 2".
- **Tying the offer to the request.** The offer that comes back carries `pull` (the token). Its bar takes over from the "preparing" bar. An offer for a pull the user stopped meanwhile is declined.

### 5. Progress on both devices

- **One shape everywhere.** `replication/activity.py` describes every game moving, sending or receiving, in one shape:
  - the stage: `checking-space`, `preparing`, `copying`, `verifying`, `adding`, `done`, `failed`, `paused` or `waiting`;
  - bytes done of the total, percent, bytes a second, seconds left;
  - a plain reason;
  - whether it can be stopped or cleared.

  `replication_activity` lists them, read from memory and two small files.
- **The receiving device works its bars out** from its offers and live transfers. About once a second while a copy runs, it sends the bar's numbers to the sending device, in `offer-state` (`stage`, `done`, `total`, `bytesPerSecond`, `secondsLeft`), next to the state and reason from v0.30.2.
- **One connection for the news.** `replication/news.py` sends this news over one reused connection:
  - only the newest message for each game is kept, so a slow link never queues;
  - a final message (done, failed, removed) is tried again up to three times;
  - the connection closes after 20 idle seconds.
- **The sending device checks every number** (`activity.clean_progress`) and shows the same bar.
- **The surfaces.**
  - The full Devices page: a bar per game with Stop and remove or Clear.
  - The quick access menu: one compact line and a thin bar per game; selecting it opens Devices.
  - The desktop app: a transfer table (game, device, stage, progress, GiB, speed, time left, actions). Sorting and filtering come with the layout review (Peter's item 2).
- **The bars live in the backend.** A page that is closed and reopened picks them up where they are, and follows them every second while anything moves.
- **The stages are honest.** Reading the game's files on the sending device is shown as "Preparing", because a large game takes minutes there.

### 6. Stop and remove from either side

- **On the receiving device:** as before. It deletes everything the copy made, then tells the sender "removed". The sender then withdraws its offer automatically and shows a toast.
- **On the sending device:** a new `offer-stop` request asks the receiving device to stop and remove. The receiving device accepts it only from the device the game came from. The sender then withdraws its offer. If the receiving device cannot be reached, its copy fails once the files are no longer offered, and it can be removed there.
- **Before an offer exists:** while the sending device still prepares, Stop cancels that work. A stopped pull is forgotten, and a late offer for it is declined.

### 7. Toasts on both sides

| Device | When | Toast |
|---|---|---|
| Sending | the game is offered | "Factorio is on its way to Legion Go 2." |
| Sending | the copy starts | "Factorio is copying to Legion Go 2." |
| Sending | it arrives | "Factorio arrived on Legion Go 2." |
| Sending | it fails | "Factorio did not arrive on Legion Go 2: reason." |
| Sending | the other device removed it | "Legion Go 2 stopped and removed Factorio." |
| Sending | the other device asked for it | "Factorio is being copied to Legion Go 2." |
| Receiving | the copy starts | "Factorio is coming from Legion Go." |
| Receiving | it is ready | "Factorio is ready on this device." |
| Receiving | it fails | "Factorio did not arrive: reason." |
| Receiving | a pull fails on the other device | "Factorio could not be copied: reason." |

Progress updates never toast.

### 8. The protocol rule, made explicit

ADR-0059 allowed new request types under version 1 and required version 2 for "a change to an existing message". This release adds two optional fields that older devices ignore by design:

- `pull` on `offer`: `validate` keeps known fields only;
- the bar's numbers on `offer-state`: `record_state` reads only what it knows.

The rule is now: **new request types and optional fields that older devices ignore may be added under version 1. A change to the meaning or the form of an existing field needs version 2.** The golden test still pins `manifest` and `chunk`.

## Consequences

- **No new endpoint, scope or binary.** Writes stay inside the allowlist (spec 6.3), as with Accept.
- **Threat model:**
  - T135: no acceptance;
  - T136: pull and the games list;
  - T137: forged stop and progress;
  - T138: the listener switched on by a pairing.
- **Assumptions:** A217, A218.
- **Device run:** part 4, steps 13 to 18.
