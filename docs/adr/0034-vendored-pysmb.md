# ADR-0034: Windows share installs through vendored pysmb

- Status: accepted (the recommended option in ADR-0033, chosen under Peter's standing instruction to take the recommended option)
- Date: 17 November 2026
- Deciders: Peter (owner)
- Builds on: ADR-0033 (network install), ADR-0018 (System Binary Register), ADR-0030 (frozen stdlib)

## Context

ADR-0033 compared four routes to SMB shares that aren't mounted:
- **gvfs** (`gio`), which needs a register entry;
- **kio-fuse**, which needs a session bus and a KDE session;
- **smbprotocol**, which needs the compiled `cryptography` package and so breaks P9;
- **pysmb**, which is pure Python.

pysmb was recommended because it needs no binary, no root, no mount and no session bus. Peter's brief asked for SMB "via the route the probe confirms". The probe matters only for the gvfs and kio-fuse routes. pysmb works the same on any device with a network connection, so it does not wait on the probe.

This is Keepsake's first vendored library. P9 allows vendored pure-Python libraries, pinned with hashes.

## Decision

1. **What is vendored:**
   - **pysmb 1.2.15** (zlib/libpng). Only the `smb` and `nmb` packages are kept. The Twisted front ends (`smb/SMBProtocol.py`, `nmb/NetBIOSProtocol.py`) and the urllib handler (`smb/SMBHandler.py`) are left out.
   - **pyasn1 0.6.5** (BSD-2-Clause).
   - Both come from their PyPI wheels, checked against the wheels' SHA-256, and live in `py_modules/keepsake/_vendor/`.
2. **One patch.** pysmb 1.2.12 and later import `tqdm` (MPL-2.0) at module level, but use it only when a caller asks for a progress bar, and Keepsake never does. The two `from tqdm import tqdm` lines are replaced by a stub that raises if called. This keeps the newest pysmb fixes without shipping tqdm. pysmb 1.2.11 has no tqdm import, but would give up four releases of fixes.
3. **Reproducible:**
   - `scripts/vendor.py` downloads the pinned wheels, checks their hashes, extracts the listed packages, applies the patch and writes the licences and `_vendor/MANIFEST.json`, which lists every file's SHA-256.
   - `tests/test_vendored.py` fails on any added, missing or changed file, a missing licence, a lost patch, a compiled file, or an import of tqdm, Twisted or `cryptography`.
   - `.gitattributes` keeps the tree byte for byte (`-text`).
   - Ruff and mypy skip it.
4. **Loaded only on use.** `keepsake/installer/smbshare.py` adds `_vendor` to `sys.path` the first time a share is used. If a stdlib module that pysmb needs is missing from Decky's frozen Python, SMB reports that plainly. Nothing else is affected.
5. **Rules, the same terms as HTTP (ADR-0033):**
   - Only servers whose every address is local (`remote.LOCAL_NETWORKS`). The name is resolved once, and Keepsake connects to the checked address, so there is no second DNS lookup.
   - **SMB 2 only.** A server that offers only SMB 1 is refused. Signing is used when the server supports it. pysmb has no SMB 3 encryption, so a share that requires encryption is reported as unreachable.
   - NTLMv2 authentication. The password goes only to that server, and remembered passwords go in the CredentialStore.
   - Downloads work like HTTP:
     - a `.part` file in staging;
     - 4 MiB reads with progress;
     - cancel between reads;
     - reconnect and resume from the byte reached, up to 5 times;
     - the size is taken from the server's attributes;
     - an optional SHA-256;
     - the free-space check and the 128 GiB cap;
     - a partial file is deleted on any failure.
6. **No new endpoint class.** A user-entered `smb://` location falls under the user-entered locations Peter approved in ADR-0033, limited to the local network.

## Consequences

- `scripts/secret_scan.py` skips only its email-address rule under `py_modules/keepsake/_vendor/`, because the upstream copyright lines carry the authors' public addresses and the licences forbid removing those notices. Token, key, profile-path and denylist rules still apply there, and `tests/test_scripts.py` proves it.
- About 0.8 MB more Python in the plugin zip. It is not imported unless SMB is used.
- `THIRD_PARTY_NOTICES.md` carries the pysmb and pyasn1 licences. The licence files also ship in `_vendor/LICENSES`.
- Updating a vendored library means editing the pin in `scripts/vendor.py`, running it and reviewing the diff. The tests catch drift either way.
- Not verified on a device yet: whether every stdlib module pysmb imports exists in Decky's frozen Python (`random`, `hmac`, `binascii`, `select`, `string` and others), and real NAS behaviour (A161, A162).
