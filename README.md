<p align="center"><img src="assets/logo.svg" width="128" height="128" alt="Haversack logo: a satchel on teal"></p>

# Haversack

Haversack installs Windows games on your handhelds and moves them between them. It is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for SteamOS and Bazzite, used entirely from Gaming Mode with the controller.

Haversack was called Keepsake until version 0.51.0. Updating from Keepsake moves everything across, and nothing is lost ([how](docs/user/updates.md#keepsake-is-now-haversack)).

Version 0.61.0 took Haversack back to these two jobs. Save sync, Advisor, the desktop app, PC support and the device pages were removed; nothing in your cloud was deleted, and version 0.60.0 still has them ([how to go back](docs/user/updates.md#going-back-to-a-version-with-save-sync)).

**[User guide](docs/user/README.md)**: getting started, a guide to each feature, privacy, and questions and answers. The same guide is inside Haversack, under Settings, Help.

## What it does

- **Install.** Install a Windows game from an ISO, a folder or a network share (SMB, WebDAV or a web server) into its own Steam shortcut and Proton prefix. Multi-disc sets, a queue of installs, and artwork from SteamGridDB with your own key.
- **Replication.** Send a whole game from one handheld to another over your home network or your own VPN, with its Proton version, artwork and launch options. The first copy carries the game's saves; after that, the game stays in step when you patch or mod it, and updates never replace a save or settings file on either device. Emulator games can be sent too.

## Principles

- **Never overwrite a save.** After the first copy of a game, no update replaces its saves or settings, on either device.
- **Device to device only.** Games go straight between your own paired handhelds, encrypted. Nothing goes through the cloud.
- **Gaming Mode first.** No Desktop Mode, no terminal and no root are needed. Nothing is bundled or downloaded as a program.
- **Nothing is sent anywhere you did not choose.** Haversack has no server and collects nothing ([privacy](docs/user/privacy.md)).

## Install

**On a handheld**, install from one address that never changes:

```
https://github.com/breakmylegs/haversack/releases/latest/download/Haversack.zip
```

1. In Decky Loader, open Settings, General, and switch on Developer mode (once per device).
2. Open Decky, Settings, Developer, **Install Plugin from URL**, and paste the address above.
3. Open Haversack in the Quick Access Menu and choose **Open Haversack**. There is nothing to set up.
4. After that, Haversack updates itself from Settings, Updates. Every release is signed, and Haversack checks the signature before installing.

Each release also has `Haversack-v<version>.zip` with the same bytes. Copies named `Keepsake.zip` and `Keepsake-v<version>.zip` serve installs from before the rename. `SHA256SUMS` lists every name and is signed.

## Help

- **In Haversack:** Settings, Help (this guide), and Diagnostics, Device checks, **Run all**.
- [docs/troubleshooting.md](docs/troubleshooting.md): what each message means and what to do.
- [CHANGELOG.md](CHANGELOG.md): what changed in each version.

## Development

- **Setup:** [docs/dev-setup.md](docs/dev-setup.md).
- **Contributions:** [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security reports:** [SECURITY.md](SECURITY.md).
- **Design decisions:** [docs/adr/](docs/adr/). The threat model is in [docs/threat-model.md](docs/threat-model.md).

## Licence

BSD-3-Clause. Based on [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template), whose notice is kept in [LICENSE](LICENSE).

- **Save locations**, which keep saves out of game updates, come from the [Ludusavi manifest](https://github.com/mtkennerly/ludusavi-manifest) (MIT).
- **The logo and icons** were drawn for this project.
- **Third-party notices** are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
