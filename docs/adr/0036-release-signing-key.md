# ADR-0036: Release signing key: storage, transition and proof

- Status: accepted (Peter's owner decision of 17 November 2026, "start signing releases now"; the storage choice is mine under ADR-0037)
- Date: 17 November 2026
- Deciders: Peter (owner)
- Builds on: ADR-0023 (verification in pure Python, switched on by pinning), threat model T10

## Context

Peter asked for releases to be signed from now on, without him typing a password at each release, and for the secret key to be protected as well as the platform allows. He also asked for proof that the in-plugin verifier accepts a real minisign signature (A123 said it had only been checked against signatures built by Keepsake's own tests), and for a safe transition for every installed version.

This laptop is a managed Windows machine. A security hook here blocks any command that I (Claude) run against a key file ("Secrets files are blocked by policy"). That includes creating a throwaway test key. I do not work around that guardrail. So **Peter creates the key himself**, with one command, and the secret never passes through me.

## Options for storing the key

| Option | Unattended signing | A copy of the files (backup, imaging, theft of the disk) | A process running as Peter |
|---|---|---|---|
| Key without a passphrase (`minisign -W`), folder limited to Peter by its access list | yes | exposes the key | can sign |
| Passphrase in an environment variable or a plain file | yes | exposes the key | can sign |
| **Key encrypted by minisign (scrypt), passphrase sealed with DPAPI for Peter's account, folder limited to Peter** | **yes** | **useless: the passphrase only unseals under Peter's Windows account** | can sign |
| Windows Credential Manager | yes | same as DPAPI (it uses DPAPI) | can sign |
| Hardware token or TPM | yes | safe | can sign while it is plugged in |

Notes on the options:
- **The last row** is not available: minisign has no PKCS#11 or TPM support.
- **No software option** can stop malware already running as Peter. That malware would also have his `gh` session, so it is the same compromise.

## Decision

1. **Storage.**
   - **The key:** a minisign key encrypted with a 64-character random passphrase (`secrets.token_urlsafe(48)`).
   - **The passphrase:** sealed with DPAPI (`CryptProtectData`, current user, with Keepsake-specific entropy).
   - **The folder:** `%LOCALAPPDATA%\Keepsake\signing`, which is not roamed and is outside OneDrive. Its inherited permissions are removed and only Peter's account is granted access (`icacls /inheritance:r /grant:r`).
   - **The tool:** `scripts/signing.py` handles setup, status, backup, show-passphrase and restore. It never prints or logs the key, and the passphrase appears only in `show-passphrase`, after Peter types `SHOW`.
2. **Unattended signing.** `release.py publish` asks `signing.py` to sign `SHA256SUMS`. That unseals the passphrase and pipes it to `minisign -S`. minisign reads its password with `fgets(stdin)` on Windows as well (`src/get_line.c`, A165), so a pipe works.
3. **Every signature is checked before publishing.**
   - **The pinned key:** after minisign signs, `release.py` verifies the signature with the plugin's own verifier against the pinned `release_key.PUBLIC_KEY`. A release that installed devices would refuse is never tagged.
   - **Pinned key, no signing key:** if the key is pinned but no signing key is set up, publishing stops.
   - **Ongoing proof:** each release re-proves the verifier against the real minisign tool.
4. **One-off proof against the real tool (A123, now verified).** `tests/test_minisign_real.py` checks the plugin's verifier against minisign's own signed release `minisign-0.12.tar.gz` and its `.minisig`, with minisign's published public key. The files were first checked with `minisign -V`. The verifier:
   - accepts it;
   - refuses one changed byte, a changed signature, a changed trusted comment, an empty or broken signature, and another key.
5. **Transition.**
   - **Every version up to v0.24.0** has an empty pinned key, so it installs any release with a matching `SHA256SUMS`, signed or not (`tests/test_signatures.py`). The first signed release therefore installs on v0.2.0, v0.22.x, v0.23.0 and v0.24.0.
   - **That release carries the pinned key,** so from then on unsigned or wrongly signed releases are refused (`unsigned-release`, `bad-signature`).
   - **Order:**
     1. merge this change (key still empty);
     2. Peter runs `setup`;
     3. pin the public key by pull request;
     4. publish the next release signed.
   - **First installs:** the first-install URL (`releases/latest/download/Keepsake.zip`) still works. Decky installs it without Keepsake's own checks, as before, and `Keepsake.zip` is listed in the signed `SHA256SUMS`.
6. **Losing or rotating the key.**
   - **If the key is lost:** pinned devices cannot update in place. The recovery is a reinstall from the first-install URL, which keeps settings and saves, because Decky's uninstall step leaves them (`main.py` `_uninstall`).
   - **For a planned rotation:** publish a release signed with the old key that pins the new one.
   - **The backup** (steps in `docs/releasing.md`) is what keeps a lost laptop from needing either of these.

## Consequences

- From the pinning release on, a compromised GitHub account alone can no longer push an update to devices (T10). It also needs this laptop's key and Peter's Windows account.
- Releases can be made without Peter at the keyboard.
- The laptop's corporate policy means key creation and restore are always Peter's steps.
