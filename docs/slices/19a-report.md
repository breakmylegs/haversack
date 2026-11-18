# Slice 19a report: sending a game

The first part of slice 19, recorded in ADR-0059. Slice 19b adds the pages and the user guide.

## What changed

- **`replication/sendgame.py`:** the send plan.
  - **What it copies:** the game's own folder (or nothing, when the game is inside its prefix), its prefix, its compatibility tool from `compatibilitytools.d`, and its artwork under neutral names.
  - **Folder safety:** never home itself, the library root, or Steam's own folders.
  - **Exclusions:** caches, dumps, logs and Temp folders.
  - **Launch options:** device folders become `{install}`, `{prefix}` and `{home}`; mounts and other local paths are dropped and listed.
- **`replication/offers.py`:**
  - **Offer validation:** field by field.
  - **`Outgoing`:** prepares the shares and their manifests in a worker thread, keeps them across a restart, and withdraws them.
  - **`Incoming`, on the receiving side:**
    - stores offers until the user answers;
    - checks space, folders and the tool before starting;
    - records every target before making it;
    - runs the transfers, then queues `add-shortcut`, then moves the prefix into `compatdata/<appid>`;
    - sets and reads back the program, start folder, launch options, tool and artwork;
    - "Stop and remove" undoes exactly what the offer made.
- **`replication/source.py`:** shares keep their ID across a restart.
- **`replication/jobs.py`:** an `on_finished` hook.
- **`replication/service.py`:** the listener serves the shares and the `offer` request.
- **`replication/transfer.py`:** promote retries Windows' brief sharing violations.
- **App:**
  - 7 calls: `replication_send`, `_offers`, `_offer_check`, `_accept`, `_decline`, `_withdraw` and `_remove_game`;
  - a Saves push before sending;
  - Steam results and artwork files routed to Replication;
  - re-keying and Saves adoption;
  - change notices are now thread-safe.
- **Frontend:** `add-shortcut` uses the compatibility tool the offer asks for, when Steam lists it. The call bindings are in `backend.ts`.
- **Docs:** ADR-0059, `docs/protocol.md` (additions), T117, A195, the module document, the plan and the changelog.

## Test results

- `tests/test_replication_sendgame.py` (38 new):
  - the plan, exclusions and launch options;
  - offer validation (15 refusals);
  - an offer arriving and waiting;
  - accept, copy, register, promote and finish, in process;
  - a tool Steam did not keep, and a shortcut Steam refused;
  - "Stop and remove" after registration and mid-copy;
  - preflight refusals;
  - offers kept across a restart;
  - the app routing a Steam result and adopting the saves.
- `tests/test_replication_transfer.py` gains the Windows rename retry test.
- `tests/test_replication_protocol.py` pins the addition.
- 238 covering tests pass in all, across the replication files, `test_host.py`, `test_hosts.py`, `test_modules.py` and `test_installer.py`.
- Mutation checks: 24 mutations across the plan, the offer checks, preflight, registration, promote, Stop and remove, artwork serving, adoption and the rename retry. All killed after seven tests were added.
- `python scripts/check.py`: all checks passed.

## Known gaps

- There are no buttons yet (19b).
- Whether Steam accepts the copied prefix, and a tool copied while it runs, is unverified (A195).
- Config paths are not yet excluded by default; Ludusavi's `config` tags are not wired in. Recorded for slice 20.

## On-device checklist (after 19b)

1. Install a game from ISO on the Legion Go 2 with the Installer, play it once, and quit.
2. On the Legion Go, switch on the listener. On the Legion Go 2, send the game to it.
3. On the Legion Go, accept the offer. If the tool is missing, choose to copy it. Wait for "is ready".
4. Start the game on the Legion Go. Check:
   - the same Proton version, artwork and launch options;
   - the saves are there;
   - Saves shows no conflict.
5. Repeat in the other direction.
6. Send again and choose **Stop and remove** part way. Check that the library, `compatdata` and the tool folder are as they were.
