# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's "Report a vulnerability" button on the Security tab of this repository (private vulnerability reporting is on). Do not open a public issue.

Include what you found, how to reproduce it and the Haversack version. You should get a reply within a week.

## Scope

Of particular interest:

- anything that could leak a SteamGridDB key, a network-location password or a pairing key
- writes outside the plugin's allowlisted folders, including path escapes in a game sent from another device
- a way for an unpaired device to connect, or for a paired one to write outside the game it sends
- a game update that replaces a save or settings file
- tampering with releases or the update path

The threat model is in [docs/threat-model.md](docs/threat-model.md).

## Design notes

- The backend runs as the desktop user, never as root.
- Keys and passwords are stored with mode 0600, never logged and never included in diagnostics exports.
- Releases carry a `SHA256SUMS` file signed with minisign, using the project's release key (ADR-0036). The key's public half is built into the plugin, which refuses any update without a valid signature.
- The release zip is built deterministically, so anyone can rebuild a tag and compare hashes: see "Rebuilding a release to check it" in [docs/releasing.md](docs/releasing.md).
- Each release also carries a software bill of materials, `Haversack-v<version>.sbom.cdx.json` (CycloneDX), listed in the signed `SHA256SUMS`. It names every third-party component the release ships, with versions and licences (ADR-0050).
- If the release key were ever lost or exposed, "Signing key: rotation and compromise" in [docs/releasing.md](docs/releasing.md) says what happens.
