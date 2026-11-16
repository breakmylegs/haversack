# Slice 12 report: hardening, documentation and cutover

Branch `slice/12-hardening`, based on `main` after v0.11.0. Build prompt slice 12. Design decisions: ADR-0023. **v1.0.0 is prepared but not published**: it needs Peter's release key, his sign-off of `docs/security-review.md` and the on-device checks (ADR-0023).

## What changed

**Code**
- `ed25519.py`, `minisign.py`, `release_key.py` (new) and `update.py`: release signature verification. Off until a public key is pinned; then mandatory for every update (threat model T10).
- `store/local_folder.py`: listing walks only below the prefix's folder. The 50-game check found the old walk made every idle pass quadratic: 142 s became 14 s for 50 games.
- `src/update.ts`: messages for unsigned, missing and invalid signatures.

**Docs**
- `README.md`: what Keepsake does, install, the first-run wizard, links to every setup guide, help and licences.
- `docs/troubleshooting.md` (new): each message, its meaning and what to do; getting diagnostics off the device.
- `docs/cutover.md` (new): build prompt section 19 as a step-by-step plan.
- `docs/security-review.md` (new): every v1 threat reviewed; nine accepted risks listed for Peter's sign-off with recommendations.
- `docs/releasing.md`: how to create and pin the release key.
- `docs/threat-model.md`: T10 and T34 updated. ADR-0023, assumptions A123 to A125, CHANGELOG 0.12.0.

## Tests

- New: `test_signatures.py` (8, including RFC 8032's test vectors 1 and 2, both minisign algorithms, tampering, wrong key, changed trusted comment, and the updater with and without a pinned key), `test_performance.py` (the 50-game check). Changed: `test_update.py` (the prepared update now reports `signed`).
- Added later (slice 25 hardening): `test_fuzz_signatures.py` (3). A mutated signature file never verifies unless only the unsigned comment changed. Mutated public keys and arbitrary Ed25519 keys and signatures, including off-curve and small-order points, never raise. Removing the trusted comment check makes it fail.
- Re-run because they cover touched code: `test_update.py`, `test_store_contract.py -k local`, `test_store_local.py`.
- 50-game timings on the development laptop are recorded in assumption A125. All are well inside their budgets.
- Mutation checks: 8 guards broken one at a time:
  - the curve check, `s < L`, and the point decompression sign;
  - the key ID, the trusted comment and the BLAKE2b prehash;
  - the updater's "unsigned release" refusal, and the check being switched on by a pinned key.

  The first run missed `s < L`, because the test used `s = L`, which fails the equation anyway. It now tests the malleable `s + L` signature, which RFC 8032 requires rejecting, and all 8 are caught.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan).

## Known gaps

- Releases stay unsigned until the key is pinned.
- On-device timings for 50 games are not yet measured.
- v2 threats (T42 to T55) are out of v1 scope and reviewed in slice 25.

## Before v1.0.0 (Peter)

1. Create the minisign key and pin the public key (`docs/releasing.md`).
2. Sign off the accepted risks in `docs/security-review.md`, or ask for changes.
3. On-device: install from `https://github.com/breakmylegs/keepsake/releases/latest/download/Keepsake.zip` on a SteamOS device and on a Bazzite device, complete the wizard, sync a game between them, and run `pnpm run test:device` plus `python scripts/test_on_device.py tests/test_performance.py`.
4. Then: `pnpm release prepare 1.0.0`, merge, and `pnpm release publish --device-tested` with `KEEPSAKE_MINISIGN_KEY` set.

Next: v2 slices from `docs/plan.md`, starting with slice 13 (module framework), once Peter has answered the C0 questions.
