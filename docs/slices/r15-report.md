# R15 report: pairing by code

Recorded in ADR-0070 (Peter's request of 21 November 2026). It supersedes ADR-0054 points 4.5 to 4.7 and ADR-0056's comparison step.

## What changed

- **`replication/link.py`, pairing protocol 2** (`keepsake-pair/2`, a new public key):
  - requests are taken whenever the listener is on (at most 3 in 2 minutes; 5 failed attempts lock an address or device ID out for 10 minutes);
  - `pair-request`, then Accept or Decline (120 s), then `pair-accepted` or `pair-declined`;
  - a random 6-digit code is shown on the receiver;
  - `prove_code` runs twenty commit-then-reveal rounds, one per bit, bound to `tls-unique`, both IDs and the role, and compared in constant time;
  - then `pair-key` and `pair-done`;
  - `answer`, `enter_code` (once per attempt) and `cancel`.
- **`replication/service.py`:** no window; `enter_code`; status `acceptsRequests`; a second request is refused while one is under way.
- **App:**
  - `replication_enter_code`;
  - `replication_open_pairing` and `replication_close_pairing` are removed;
  - requests are announced with `keepsake_pair_request`.
- **Frontend:**
  - Gaming Mode: a modal with Accept and Decline, or only a notification while a game runs;
  - Devices: waiting, number pad, code, checking, declined and failed states;
  - the desktop interface: the same steps, with a text field for the code.
- **Device check:** `see-other`, "The other handheld can be seen".
- **Docs:**
  - ADR-0070; status notes in ADR-0054 and ADR-0056; `docs/protocol.md`;
  - T129, the Replication guide, CHANGELOG, device run part 3 step 1.

## Decision taken under ADR-0037, and why it differs from the request

The request asked for the code to be derived from the TLS session as today, with only the requester checking it. That protects the requester but not the receiver:
- a device in the middle can compute the receiver's code from its own session with the receiver;
- it can then hand the receiver its own link key while the real requester reports a wrong code.

The code is therefore random, shown only on the receiver, and proved bit by bit with commitments (Bluetooth's passkey entry method). Both devices are protected, there is about one chance in a million per attempt, and there is nothing to try offline. ADR-0070 explains this in full.

## Tests

- `tests/test_replication_link.py`, 41 tests (pairing rewritten):
  - pairing and then connecting; a wrong code (differing only from bit 10 up) ending both attempts;
  - decline and no answer; no code typed in time; cancelling, and a second request refused;
  - three requests in two minutes; lockouts by address and by device ID;
  - **a relaying device in the middle between two real TLS sessions: both sides fail and no key is sent**;
  - a broken reveal and an out-of-order round; reflection on both sides and an old protocol version; pairing with itself;
  - commitment inputs; code format; the new device check.
- `tests/test_replication_protocol.py`: pins the new identity, key, limits and a commitment value.
- `tests/test_replication_devices.py`: the app-level flow (request event, Accept, code shown only on the receiver, entry, paired).
- **Regression:** `test_host.py`, `test_devicechecks.py`, `test_directsync.py`, `test_replication_transfers.py`, `test_replication_sendgame.py`, `test_replication_ongoing.py`.
- **Mutation:** 27 mutants of the rounds, commitments, code checks, answers, limits, lockouts, decline handling and service guard. All are killed after five sharper tests were added. One display condition, already ensured by clearing the code, was removed.

## Known gaps

- Both handhelds need this version to pair. Pairing with an older version fails cleanly in the handshake.

## On-device checklist

- `docs/device-run.md` part 3 step 1.
