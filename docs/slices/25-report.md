# Slice 25 report: v2 hardening (in progress, part 1: parser fuzzing)

Branch `slice/25-v2-hardening`, based on `main`. Slice 25 covers four things:
- a full threat model review;
- a 50-game performance check;
- VDF and manifest parser fuzzing;
- documentation and the v2.0.0 release.

Only the fuzzing can be done before slices 14 to 24 land and the devices are checked, so it comes first. It covers v1 code that is already on `main`, so this branch can merge on its own.

## What changed

- `tests/test_fuzz_parsers.py`: deterministic mutation fuzzing of every parser that reads outside input. The contract is that each parser either returns or raises its own error. The parsers:
  - binary VDF (`shortcuts.vdf`);
  - text VDF (`libraryfolders.vdf`, app manifests);
  - the Ludusavi manifest YAML subset, and the index built from it;
  - Wine `.reg` files, with export, merge and verification on whatever parses;
  - the update listing and checksum parsers.

  It also includes round-trip properties for both VDF formats, and depth-limit checks. The default is 1,500 iterations per parser; set `KEEPSAKE_FUZZ_ITERATIONS` for longer runs.
- **Bug fixed** (`manifest.py`): a mapping or list inside a manifest entry's `tags` raised `TypeError` and aborted the whole index build. Every game then lost its save locations until the next manifest. Now only string tags count, and the entry is handled like any other entry without save paths.
- **Bug fixed** (`manifest.py`): Steam IDs of `true` or `false` were accepted as app IDs, because `bool` is an `int` in Python. They are now ignored, as are zero and negative IDs.
- Docs:
  - threat model: T27 updated, new T79;
  - CHANGELOG `[Unreleased]`;
  - `docs/plan.md` status refreshed for 16 November.

## Tests

- New: `tests/test_fuzz_parsers.py`, 12 passed. A long run at 30,000 iterations per parser also passes.
- Regression tests for the touched file: `tests/test_manifest.py`, 17 passed.
- Proof of the new tests:
  - before the `tags` fix, `test_manifest_fuzz` and `test_manifest_index_survives_odd_but_valid_yaml` failed with the `TypeError`;
  - putting back the plain `isinstance(value, int)` check makes `test_manifest_steam_ids_are_positive_integers_never_booleans` fail.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan).

## Still to do in slice 25

- Done on #16 (slice 12), where those parsers live: `tests/test_fuzz_signatures.py` fuzzes minisign keys and signatures and Ed25519 verification. A mutated signature never verifies unless only its unsigned comment changed.
- Done (part 2, from `main` after #20): the Installer's mount table, `udisksctl` output, the `STEAM_COMPAT_MOUNTS` builder (it never emits a quote, `%` or newline) and installer program ranking. A mount whose output cannot be parsed always releases its loop device. Four tests, no bugs found. A long run at 20,000 iterations passes. Breaking either the release on failure or the character check makes them fail.
- The Advisor's parsers (Deck Verified reports, the anti-cheat list, AI replies and launch options) are fuzzed on #26, where that code lives until it merges.
- Still to fuzz once their slices merge: Replication manifests and the peer protocol (slices 17 and 18).
- The full threat model review, the 50-game performance check on both devices, documentation, and the v2.0.0 release with clean installs on SteamOS and Bazzite.

## On-device checklist

None for this part. These tests are platform-independent and run on the device with the rest via `pnpm run test:device` at release.
