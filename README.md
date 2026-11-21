# Keepsake

Keepsake is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that syncs PC game saves between SteamOS and Bazzite handhelds through cloud storage, operated entirely from Gaming Mode.

It is built for non-Steam shortcuts installed into their own Proton prefixes, whose compatdata IDs differ on every device. Saves are stored under canonical logical roots, so the same game finds its saves on each device whatever its local prefix is called, and Keepsake recognises the same game on both devices even when the shortcuts are named differently.

**[User guide](docs/user/README.md):** getting started on a handheld, a Linux PC or Windows, a guide to each feature, privacy and questions and answers.

## What it does

- Checks the cloud before a game starts (pausing it for a moment) and saves after it quits.
- Asks you whenever both devices have new progress. It never silently overwrites a save, and whichever save you do not choose is kept.
- Keeps a history of snapshots with restore, pin and undo. Suspicious saves (many files gone) are kept on the device instead of being uploaded.
- Works with OneDrive, Google Drive, WebDAV (for example Nextcloud) and S3.
- Imports old Ludusavi backups, syncs registry keys for games that need them, and leaves Steam games with Steam Cloud alone.
- Updates itself from Settings, Updates.

## Principles

- Never silently overwrite a save. When both sides changed, you choose.
- Cloud snapshots are written once and never modified.
- Every restore is reversible.
- Content hashes decide; timestamps only inform.
- No Desktop Mode, no terminal, no root, no bundled binaries.

## Install

First install on a new device uses one URL that never changes:

```
https://github.com/breakmylegs/keepsake/releases/latest/download/Keepsake.zip
```

1. In Decky Loader, open Settings, General, and enable Developer mode (once per device).
2. Open Decky, Settings, Developer, Install Plugin from URL, and paste the URL above.
3. After that, updates come through Keepsake's Settings, Updates.

The URL always gives the newest stable release; pre-releases are only offered through the Updates page on the Pre-release channel. Each release also has a versioned copy, `Keepsake-v<version>.zip`, with the same bytes, and `SHA256SUMS` lists both names.

## First run

Open Keepsake from the Quick Access Menu and choose **Set up Keepsake**. The wizard walks through:

1. **Device name**, shown next to this device's saves on your other devices.
2. **Cloud.** Choose OneDrive, Google Drive, WebDAV or S3, and sign in ([Cloud storage and sign-in](docs/user/cloud.md)).
3. **Scan games** and **review matches**: approve any match Keepsake is not sure about.
4. **Choose games** to sync. Steam games are hidden by default because Steam Cloud covers them.
5. **Dry run**: see what the first sync will do for each game. Nothing changes until you confirm.

Then set it up on your other device the same way. Games whose saves already match adopt silently; any that differ ask you which save to keep.

Moving from Ludusavi? Follow [docs/cutover.md](docs/cutover.md).

## Installing games

Keepsake's **Install** page installs a Windows game from an ISO file or a folder into its own Steam shortcut and Proton prefix, all from Gaming Mode. It adds an `Install: <Title>` shortcut that runs the installer; you install into the folder Keepsake shows, quit, choose the game's program, and the same shortcut then starts the game.

If an installer asks for the disc, press **Installer wants a disc drive** and start the installer again. To install from a NAS, mount the share first (for example by opening it in Dolphin in Desktop Mode); it then appears on the Install page.

**An installer is a Windows program that runs with your user's rights. A Proton prefix is not a sandbox.** Only install software you trust.

## Help

- [docs/troubleshooting.md](docs/troubleshooting.md): what each message means and what to do.
- Keepsake, Diagnostics, Health, Run checks: health checks for sign-in, sync, conflicts, prefixes and the manifest.
- [CHANGELOG.md](CHANGELOG.md): what changed in each version.

## Development

See [docs/dev-setup.md](docs/dev-setup.md). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: [SECURITY.md](SECURITY.md). Design decisions are in [docs/adr/](docs/adr/), the threat model in [docs/threat-model.md](docs/threat-model.md).

## Licence

BSD-3-Clause. Based on [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template), whose notice is kept in [LICENSE](LICENSE). Save location data comes from the [Ludusavi manifest](https://github.com/mtkennerly/ludusavi-manifest) (MIT), credited in the app next to the data. Third-party notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
