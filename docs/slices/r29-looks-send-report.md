# R29 stage 1b: looks to the other handheld (v0.55.0)

## What changed

- **Send to your other handheld** on Device, Looks (Gaming Mode and the desktop app): themes, sound packs, and the videos Haversack set.
- **A generic offer kind in Replication** (ADR-0092): `Outgoing.prepare_parts`, plus `Incoming(kinds=...)` with `kind_handler`, preflight and finish. The Looks module owns the offer (`looks/lookplan.py`) and the app wires them together, so neither module reaches into the other (P13).
- **The `looks-offer` request:**
  - members only, checked on a strict pattern, with no paths;
  - staged beside each destination and moved in name by name, never over what exists;
  - nothing written while the receiver's Looks is off.
- **Fix:** the emulator sender showed "refused it" instead of the other device's reason, because it read `message` where the link sends `reason`.

## Tests

- **New:** `tests/test_looks_send.py`, 9 tests plus one POSIX-only test.
  - The plan and the validator.
  - End to end over a fake connection: what lands where, what is kept, no staging left.
  - Looks off on the receiver, a device without the kind, leftover staging, and the app's guards.
- **Mutation testing:** 23 mutants of `lookplan.py` and the new `offers.py` code. All are killed except one, which the POSIX test kills on the device (links offered). Two survivors led to tests: leftover staging, and only the members being shared.
- **Regression tests for the touched files:**
  - `test_emu_transfer`, `test_replication_offer_state`, `test_replication_ongoing`, `test_replication_protocol`, `test_replication_pull_progress` and `test_replication_sendgame`;
  - `test_looks`, the host callables test and `test_desktop_calls`.

  All pass (125).
- **Checks:** `tsc` for both frontends and eslint on the changed files pass. The gate result is in the pull request.

## Threat model

T164.

## Known gaps

- CSS Loader's own settings, such as which themes are switched on, are not sent: only the themes themselves are.

## On-device checklist

- Device run step 53.
- `pnpm run test:device tests/test_looks_send.py`.
