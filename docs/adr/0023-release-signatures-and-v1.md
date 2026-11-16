# ADR-0023: Release signature verification and v1.0.0 readiness

- Status: accepted (slice 12, decided under Peter's delegation; the key itself is Peter's action)
- Date: 16 November 2026
- Deciders: Peter (owner)
- Sources: build prompt sections 12 and 16 (slice 12), threat model T10, ADR-0002, ADR-0004

## Context

Without CI (ADR-0004), the minisign signature over `SHA256SUMS`, made with a key only Peter holds, is the control that protects against a compromised GitHub account (T10). Releases have been unsigned so far because no key exists, and the updater could not verify signatures. Slice 12 also has to decide when v1.0.0 can ship.

## Decision

1. **Verification in pure Python.** `keepsake/ed25519.py` implements Ed25519 verification following RFC 8032's reference algorithm (stdlib `hashlib` and integer arithmetic only, principle 9), tested against the RFC's vectors. `keepsake/minisign.py` reads minisign public keys and signature files (both the prehashed `ED` default and legacy `Ed`) and checks the signature and the trusted comment's global signature.
2. **Pinned key, switched on by pinning.** The public key lives in `keepsake/release_key.py`. While it is empty, the updater installs with the SHA-256 check only (as before) and reports `signed: false`. Once Peter pins his key, every update needs a valid `SHA256SUMS.minisig` from that key; a missing, unreadable or wrong signature refuses the install with a plain message. Rollback to an older unsigned release is then refused too, which is intended.
3. **v1.0.0 waits for Peter.** v1.0.0's acceptance needs a clean install on SteamOS and Bazzite and his sign-off of the accepted risks in `docs/security-review.md`. Slice 12 prepares everything but does not publish v1.0.0. The recommended order: create and pin the release key, sign off the review, run the on-device checks, then `pnpm release prepare 1.0.0` and `pnpm release publish --device-tested` with `KEEPSAKE_MINISIGN_KEY` set.

## Consequences

- Pinning the key is a one-line pull request; the first signed release after it proves the chain end to end.
- `docs/releasing.md` describes creating the key and pinning it.
- The 50-game performance check found the local test store listing the whole store for every prefix; fixed in this slice (idle pass for 50 games from 142 s to 14 s on the development laptop).
