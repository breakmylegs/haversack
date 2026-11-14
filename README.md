# Keepsake

Keepsake is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that syncs PC game saves between SteamOS and Bazzite handhelds through cloud storage, operated entirely from Gaming Mode.

It is built for non-Steam shortcuts installed into their own Proton prefixes, whose compatdata IDs differ on every device. Saves are stored under canonical logical roots, so the same game finds its saves on each device whatever its local prefix is called.

## Status

Early development. The current build collects on-device diagnostics and can update itself from GitHub Releases. It does not sync saves yet. See [CHANGELOG.md](CHANGELOG.md).

## Principles

- Never silently overwrite a save. When both sides changed, you choose.
- Cloud snapshots are written once and never modified.
- Every restore is reversible.
- Content hashes decide; timestamps only inform.
- No Desktop Mode, no terminal, no root, no bundled binaries.

## Install

Once releases exist (slice 2 onwards):

1. In Decky Loader, open Settings, General, and enable Developer mode.
2. Open Developer, Install plugin from URL, and paste the latest release zip URL from the [Releases](https://github.com/breakmylegs/keepsake/releases) page.
3. Every update after that happens inside Keepsake.

## Development

See [docs/dev-setup.md](docs/dev-setup.md). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: [SECURITY.md](SECURITY.md).

## Licence

BSD-3-Clause. Based on [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template), whose notice is kept in [LICENSE](LICENSE). Save location data will come from the [Ludusavi manifest](https://github.com/mtkennerly/ludusavi-manifest) (MIT), attributed wherever it is used.
