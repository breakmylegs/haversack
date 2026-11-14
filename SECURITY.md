# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's "Report a vulnerability" button on the Security tab of this repository. Do not open a public issue.

Include what you found, how to reproduce it and the Keepsake version. You should get a reply within a week.

## Scope

Of particular interest:

- anything that could leak cloud tokens or credentials
- writes outside the plugin's allowlisted folders, including zip slip during restore
- a game left frozen, or the wrong process frozen
- a way to make Keepsake overwrite or lose a save without the user choosing it
- tampering with releases or the update path

The threat model is in [docs/threat-model.md](docs/threat-model.md).

## Design notes

- The backend runs as the desktop user, never as root.
- Tokens are stored one file per backend with mode 0600, never logged and never included in diagnostics exports.
- Releases carry a `SHA256SUMS` file signed with minisign. The release zip is built deterministically, so anyone can rebuild a tag and compare hashes. The in-plugin updater checks the hash before handing the install to Decky Loader.
