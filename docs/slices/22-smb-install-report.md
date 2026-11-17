# Windows share installs (follow-on to slice 22): report

Builds the SMB route that ADR-0033 recommended. The decision record is [ADR-0034](../adr/0034-vendored-pysmb.md). This report follows [the network install report](22-network-install-report.md).

## What changed

- **Vendored code (Keepsake's first):** pysmb 1.2.15 (`smb`, `nmb`) and pyasn1 0.6.5, in `py_modules/keepsake/_vendor/`.
  - `scripts/vendor.py` builds the tree from the pinned PyPI wheels, checked by SHA-256.
  - It applies one marked patch, which replaces the `tqdm` import with a stub.
  - It leaves out the Twisted front ends and the urllib handler.
  - It writes `LICENSES/` and `MANIFEST.json`.
  - `.gitattributes` keeps the tree byte for byte, and ruff and mypy skip it.
- **`keepsake/installer/smbshare.py`:**
  - `smb://` address parsing;
  - a `Share` session that resolves the name once, allows only local servers, refuses SMB 1, signs when supported and uses NTLMv2;
  - listing of shares, folders and ISOs;
  - chunked download with progress, cancel, reconnect and resume, size from the server, optional SHA-256, the space check and clean-up.
  - pysmb loads only on first use.
- **Locations:** the location store accepts `smb://` locations.
- **App:** browse and download choose HTTP or SMB from the address. Its address checks and resolver are shared and injectable, so tests can use fakes.
- **Install page:** the Windows share option uses the same form, with its own hints. A typed address without a scheme gets the chosen protocol's scheme. Remembered locations are listed per protocol. Address handling no longer uses `URL()`, which gives `smb://` no origin in Chromium.
- **Docs:** ADR-0034, the pysmb and pyasn1 notices in `THIRD_PARTY_NOTICES.md`, T91, T92, A161, A162, the changelog, and the `vendor.py` command in CLAUDE.md.

## Tests

- `tests/test_installer_smb.py` (11) uses a fake pysmb connection. It covers:
  - addresses;
  - share and folder listing, where special shares, printers and non-ISO files are hidden;
  - connecting by the checked address;
  - chunked download with progress and checksum;
  - reconnecting and resuming from the byte reached;
  - failures leaving nothing behind (repeated drops, checksum, space, cancel, size cap, missing file);
  - refusing SMB 1, public and mixed addresses, a wrong password and another server;
  - resolving the name once, even when a second DNS answer differs;
  - the real vendored pysmb loading without tqdm or Twisted;
  - the real pysmb failing cleanly on a closed local port;
  - remembered `smb://` locations;
  - the app flow from share list to folder to prepared install.
- `tests/test_vendored.py` (3) checks:
  - the files against the manifest;
  - the pins, licences and patch;
  - no compiled files and no banned imports.
- Regression: `tests/test_installer_network.py` and `tests/test_installer_remote.py`.
- Mutation checks: see the pull request.

## Known gaps

- SMB 3 encryption is not supported by pysmb. Shares that require it fail with a plain message.
- Not run against a real NAS, and the frozen-Python stdlib coverage for pysmb is unproven (A161, A162).

## On-device checklist

1. In Gaming Mode, open Install and enter a title. Choose From a network location, then Windows share (SMB).
2. Enter `smb://<nas>/` with your user name and password, then Browse. Check your shares are listed, and IPC$ and admin shares are not.
3. Open a share and choose an ISO. Watch the progress, cancel once, then download again and finish the install.
4. If the NAS allows guest access, try it with no user name.
5. If anything fails, export diagnostics. The log shows only error class names.
