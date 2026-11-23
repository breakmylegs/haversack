<p align="center"><img src="assets/logo.svg" width="128" height="128" alt="Haversack logo: a satchel on teal"></p>

# Haversack

Haversack carries your games, saves and settings between your handhelds and PCs. It is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for SteamOS and Bazzite, used entirely from Gaming Mode with the controller, and it also runs on Linux and Windows PCs.

Haversack was called Keepsake until version 0.51.0. Updating from Keepsake moves everything across, and nothing is lost ([how](docs/user/updates.md#keepsake-is-now-haversack)).

**[User guide](docs/user/README.md)**: getting started on a handheld, a Linux PC or Windows, a guide to each feature, privacy, and questions and answers. The same guide is inside Haversack, under Settings, Help.

## What it does

Haversack has parts you switch on or off in Settings, Modules:

- **Saves.** Your PC game saves follow you between devices, through your own OneDrive, Google Drive, WebDAV or S3 storage, or directly between your devices.
  - Built for non-Steam games installed into their own Proton prefixes, whose folders differ on every device. The same game is recognised on each device, even when its shortcut is named differently.
  - Haversack checks for a newer save before a game starts (pausing it for a moment) and saves after you quit.
  - When two devices both have new progress, it asks you. The save you do not choose stays in History.
  - Every restore can be undone, and a save that suddenly loses most of its files is kept on the device, not uploaded.
  - Steam games without Steam Cloud sync automatically. It can also import Ludusavi backups.
- **Replication.** Send a whole game from one device to another over your home network or your own VPN, with its Proton version, artwork and launch options. Games then stay in step, and emulator games can be sent too.
- **Advisor.** Recommended settings for your device from Deck Verified, ProtonDB and PCGamingWiki, and optionally an AI provider you choose. It only advises and never changes anything.
- **Install.** Install a Windows game from an ISO, a folder or a network share into its own Steam shortcut and Proton prefix.
- **Device.** On the Legion Go and Legion Go 2:
  - performance for each game, power limits, fan curves, the battery charge limit and controller lights;
  - help for controllers that will not reconnect.
- **Desktop.** The same features in Desktop Mode and on PCs, in a small app in your browser.

## Principles

- **Never silently overwrite a save.** When both sides changed, you choose.
- **Snapshots are immutable.** Cloud snapshots are written once and never modified.
- **Every restore is reversible.**
- **Hashes decide, timestamps inform.** Content hashes decide; timestamps only inform.
- **Gaming Mode first.** No Desktop Mode, no terminal and no root are needed. Nothing is bundled or downloaded as a program.
- **Nothing is sent anywhere you did not choose.** Haversack has no server and collects nothing ([privacy](docs/user/privacy.md)).

## Install

**On a handheld**, install from one address that never changes:

```
https://github.com/breakmylegs/haversack/releases/latest/download/Haversack.zip
```

1. In Decky Loader, open Settings, General, and switch on Developer mode (once per device).
2. Open Decky, Settings, Developer, **Install Plugin from URL**, and paste the address above.
3. Open Haversack in the Quick Access Menu and choose **Set up Haversack**: name the device, sign in to your cloud, and choose your games. Nothing changes until you confirm the dry run.
4. After that, Haversack updates itself from Settings, Updates. Every release is signed, and Haversack checks the signature before installing.

**On a PC,** follow [Linux PC](docs/user/getting-started-linux-pc.md) or [Windows PC](docs/user/getting-started-windows.md).

Each release also has `Haversack-v<version>.zip` with the same bytes. Copies named `Keepsake.zip` and `Keepsake-v<version>.zip` serve installs from before the rename. `SHA256SUMS` lists every name and is signed.

Moving from Ludusavi? Follow [docs/cutover.md](docs/cutover.md).

## Help

- **In Haversack:** Settings, Help (this guide), and Diagnostics, Health, **Run checks**.
- [docs/troubleshooting.md](docs/troubleshooting.md): what each message means and what to do.
- [CHANGELOG.md](CHANGELOG.md): what changed in each version.

## Development

- **Setup:** [docs/dev-setup.md](docs/dev-setup.md).
- **Contributions:** [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security reports:** [SECURITY.md](SECURITY.md).
- **Design decisions:** [docs/adr/](docs/adr/). The threat model is in [docs/threat-model.md](docs/threat-model.md).

## Licence

BSD-3-Clause. Based on [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template), whose notice is kept in [LICENSE](LICENSE).

- **Save locations** come from the [Ludusavi manifest](https://github.com/mtkennerly/ludusavi-manifest) (MIT), credited in the app next to the data.
- **The logo and icons** were drawn for this project.
- **Third-party notices** are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
