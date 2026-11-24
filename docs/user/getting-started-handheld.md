# Getting started on a handheld

For SteamOS and Bazzite handhelds with [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader). Everything happens in Gaming Mode with the controller. You never need Desktop Mode or a terminal.

## 1. Install Haversack

1. In Decky, open **Settings**, then **General**, and turn on **Developer mode**. You only do this once per device.
2. In Decky, open **Settings**, then **Developer**, then **Install Plugin from URL**, and enter:
   ```
   https://github.com/breakmylegs/haversack/releases/latest/download/Haversack.zip
   ```
3. After that, Haversack updates itself from its own **Settings**, **Updates** tab ([Updates](updates.md)).

There is nothing to set up. Open Haversack from the Quick Access Menu and choose **Open Haversack**.

## 2. Install a game

Open **Install** and choose an ISO, a folder holding an installer, or a network share. Haversack mounts the ISO, adds a shortcut that runs the installer in the game's own Proton prefix, and turns that shortcut into the game when the installer finishes ([Installing games](installer.md)).

## 3. Send it to your other handheld

1. On both handhelds, open **Games and devices**, **Other devices**, and switch on **Let other devices reach this one**.
2. On one of them, press **Find devices**, choose the other and press **Pair**. Accept on the other handheld and type the code it shows.
3. Open **Games and devices**, **Games**, choose the game and press **Send to <device>**.

The other handheld gets the game, added to Steam with the same name, launch options, Proton version and artwork ([Replication](replication.md)). After a patch or a mod, Haversack offers to send the update; your saves on each handheld are never replaced by one.

## Your quick menu

Haversack's panel in the quick access menu can show what you use most. Open **Settings**, **General**, **Quick menu**:
- tick the shortcuts you want, and move them with **Up** and **Down**;
- they can be pages to open, actions that run straight from the menu, or status lines;
- shortcuts for modules you have switched off are not offered;
- **Open Haversack** is always there, last.
