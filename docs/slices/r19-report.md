# R19 report: games both ways between devices, with progress on both (v0.31.0)

Peter's requests of 21 November 2026, one feature release: items 4 to 8 (two-way trust, a space check, no acceptance, progress and Stop on either side, toasts) and the new direction's item 1 (pull, and progress bars as a must-have). Decisions are in ADR-0072.

## What changed

- **Two-way pairing.**
  - When a pairing this device started finishes, its listener is switched on, if it was off, and the toast says games can now go both ways.
  - The device that accepted was listening already.
  - "Let other devices reach this one" still switches it off.
- **Space check before sending.**
  - Send now works out the game's size without hashing (`sendgame.sizes`) and asks the other device (`space-check`).
  - That device runs the same check as the copy's preflight: file systems add up, each with the margin, and a built-in or present tool needs no space.
  - The sending device stops before reading any file, with "Legion Go 2 doesn't have enough space: needs 41.2 GiB, has 12.0 GiB free".
  - An older Keepsake that lacks the check still gets the game, and its own preflight still guards it.
- **No acceptance.**
  - A new game from a paired device starts copying as soon as its offer arrives (`_auto_accept`), with the same checks as Accept.
  - A missing compatibility tool is copied.
  - A refusal fails the offer with the reason on both devices.
  - Updates keep their per-game rule.
- **Get this game (pull).**
  - Each paired device has **Games on <device>**. It lists the other device's non-Steam games, by title and random token only.
  - **Get this game** checks this device's space against the other device's sizes (`pull-check`), then asks it to send (`pull`).
  - The other device allows it, shows a toast, and sends through the normal offer, which carries the token.
  - A failure there comes back as `pull-state`.
  - A pull stopped meanwhile declines its late offer.
- **Progress bars.**
  - **The shape.** `replication/activity.py` gives one shape for every game moving, either way: the stage, bytes done of the total, percent, speed, time left, a reason, and whether it can be stopped or cleared.
  - **What the sender sees.** The receiving device sends its numbers to the sender about once a second, in `offer-state`, through `replication/news.py`. That uses one reused connection, keeps only the newest message per game, tries final messages again, and closes when idle.
  - **Where the bars show:**
    - the Devices page, with a bar per game, Stop and remove, and Clear (`GameTransfersSection`);
    - the quick access menu, as one compact line per game (`GameTransfersCompact`);
    - the desktop app's Devices page, as a table with a progress bar per game.
  - **Persistence.** The bars live in the backend, so a closed and reopened page carries on. Pages follow them every second while anything moves.
- **Stop and remove from either side.**
  - On the sending device, `offer-stop` asks the receiving device to remove the copy, then withdraws the offer.
  - On the receiving device, the "removed" news withdraws the offer on the sending side, with a toast.
  - Before an offer exists, Stop cancels the preparation.
- **Toasts on both sides,** as listed in ADR-0072 section 7. Progress never toasts.
- **The Devices page and the desktop app.** The Accept and Decline buttons and the separate "offered" list are gone. Only updates waiting for a choice keep their own section.
- **The Device checks' export** adds each bar: direction, stage, percent and a path-free reason, with no titles. It also lists the types of the last news messages sent.

## Protocol

These are additive under version 1, with ADR-0059's rule made explicit in ADR-0072 section 8:

- new request types: `space-check`, `offer-stop`, `games-list`, `pull-check`, `pull` and `pull-state`;
- optional fields: `pull` on `offer`, and the bar's numbers on `offer-state`.

`docs/protocol.md` lists them. The golden test (`tests/test_replication_protocol.py`) passes unchanged.

## Not done, and why

- **Sorting and filtering in the desktop transfer table.** These come with the layout review (Peter's item 2, R20), which reworks the desktop app as a whole.
- **Frontend tests.** The repository has no frontend test runner. The bars, the compact line and the desktop table are covered by the type check, lint, the build and the device run.
- **Retrying a failed copy in place.** A failed game is cleared (which removes what it made) and sent again. Picking up a failed copy is a later improvement, if the device run shows it is needed.

## Tests

New file: `tests/test_replication_pull_progress.py`, 25 tests:

- **Bars:** receiving stages and numbers, sending bars from the other device's news, and checks on the other device's numbers.
- **Space:**
  - the space check (one disk counted once with its margin; built-in and missing tools);
  - no library folder;
  - the exact wording;
  - request validation;
  - sizes without logs or Temp.
- **Stop and progress:** `offer-stop` only from the sending device; progress news updating the sender's bar.
- **The news sender:** only the newest progress, over one connection; a final state tried again, with the rest of the round kept.
- **Two apps:**
  - a new game starts copying by itself, and both sides see it;
  - a game that cannot start fails with the reason;
  - sending stops before hashing when the other device lacks space;
  - an older device without the check still gets the game;
  - Get this game from another app in process: no app ID or key over the link, a toast there, and a token used once;
  - Get this game checks space here first;
  - a pull needs a token listed to that device;
  - Stop from the sending device reaches the receiver and withdraws;
  - "removed" withdraws on the sender, with a toast;
  - the sender's toasts as the copy goes;
  - pairing makes this device reachable, once;
  - the export carries the bars without titles;
  - `Transfers.start` off the loop leaves nothing behind.

Changed: `tests/test_replication_offer_state.py`.

- The app test now waits for the copy to start by itself, with no Accept.
- It records news through the shared sender.
- `record_state` now also returns `stateChanged`.

Regression tests run, named:

- `tests/test_replication_offer_state.py`
- `tests/test_replication_sendgame.py`
- `tests/test_replication_ongoing.py`
- `tests/test_replication_transfers.py`
- `tests/test_replication_link.py`
- `tests/test_replication_protocol.py`
- `tests/test_replication_devices.py`

Together with the new file: 189 passed and 2 skipped on Windows (symbolic links, a Unix socket).

Mutation tests: 29 mutations across `activity.py`, `offers.py`, `news.py`, `app.py` and `sendgame.py`. One survived: forcing 100 percent on "done". It led to a new test: an older device that sends only "done" must still show 100 percent. All 29 are now caught.

The gate (`python scripts/check.py`) result is in the pull request.

## Threat model and assumptions

- **Threat model:**
  - T135: no acceptance;
  - T136: pull and the games list;
  - T137: forged stop or progress;
  - T138: the listener switched on by a pairing.
- **Assumptions:**
  - A217: the size walk is close enough to the manifest, unverified;
  - A218: `Focusable.onActivate`, verified.

## On-device checklist

In `docs/device-run.md`, part 4:

- **Step 13:** pairing both ways.
- **Step 14:** no Accept, with bars on both devices, the quick access menu, and a reopened page.
- **Step 15:** the space check message.
- **Step 16:** Get this game.
- **Step 17:** Stop and remove from each side.
- **Step 18:** the desktop table.

## Patch 0.31.1

Send's confirmation, in Gaming Mode and the desktop app, still said nothing is copied until the game is accepted on the other device. It now says the game starts by itself, after a space check, and that either device can stop and remove it. The device-run list's step 10 label is back to 0.30.2: the release script's version update had changed it, and the script now touches only the install lines. These are wording changes only, with no backend change, so they are covered by the type check, lint and the build. Threat model: no change, because nothing behaves differently.
