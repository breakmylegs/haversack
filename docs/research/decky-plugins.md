# Decky plugins: catalogue and feature verdicts for Keepsake

Research for R29. Gathered on 22 November 2026. 
## 1. Overview

**Where the list comes from.** The laptop's Forcepoint proxy blocks the store API at `plugins.deckbrew.xyz` as "Elevated Exposure", so I could not use it. Instead, the store list comes from the plugin database repository, `SteamDeckHomebrew/decky-plugin-database`. Its `.gitmodules` has 131 submodules, and its `plugins/` folder has 129 entries. Leaving out the template, that is **128 store plugins**.

The database can include plugins the store currently hides or has deprecated. For example, NonSteamLaunchers is in the database, but press reports say it was removed from the store in October 2024. Treat "in store" as "in the store database".

**How each field was checked.**
- **Purpose:** from each repository's description and the `publish.description` in its `plugin.json`, or its README where those were blank.
- **Licence:** GitHub's licence detector first. Where GitHub reports `NOASSERTION`, I read the opening lines of the LICENCE file. Most of those are the decky-plugin-template's BSD-3-Clause, often still showing the template's "Hypothetical Plugin Developer" copyright. "Unknown" means no licence file was found, or it could not be read.
- **Root:** from `plugin.json` `flags`. `root` means the backend runs as root. Decky treats `_root` as disabled, so that counts as **no**.

**Where Keepsake already stands.** Keepsake already covers several areas of the plugin ecosystem:
- save sync, which supersedes Decky Cloud Save, decky-ludusavi, SDH-GameSync, Save Manager and Steamback;
- device control, which overlaps PowerTools, SimpleDeckyTDP, PowerControl, LegionGoRemapper, Fantastic and HueSync;
- storage clean-up of shader cache and prefix reset, which overlaps Storage Cleaner;
- playtime across devices, which overlaps PlayTime;
- SteamGridDB artwork and library badges for streaming tiles;
- Advisor data from ProtonDB, Deck Verified and PCGamingWiki, which overlaps ProtonDB Badges, DeckSettings, Game Settings and Lookup;
- the sleep inhibitor, Wake-on-LAN and controller reconnect help.

**Main conclusions.**
1. Most of the rest is better left to dedicated plugins.
2. The best new direction suits what Keepsake already is: **carry other plugins' user data (themes, sound packs, boot videos, artwork, tabs, playtime) between the user's devices.** Keepsake would sync it, not reimplement it.
3. A few small, self-contained features are worth building natively:
   - boot and suspend animations;
   - a ProtonDB badge on the game page;
   - a launch options editor;
   - compatibility tool install (GE-Proton);
   - an SD card game index;
   - "pause a game".

## 2. Catalogue

Root: **yes** = `root` flag. **no** = no flag or the disabled `_root`. "(arch.)" = repository archived. Repositories are on github.com unless shown otherwise.

### 2.1 Looks

| Plugin | Purpose | Repository | Licence | Root |
|---|---|---|---|---|
| CSS Loader | Injects CSS themes from deckthemes.com into the Steam UI | DeckThemes/SDH-CssLoader | GPL-3.0 | no |
| Audio Loader | Replaces UI sounds, adds menu music (packs from deckthemes) | DeckThemes/SDH-AudioLoader | MIT | no |
| Animation Changer | Changes or randomises boot and suspend videos (steamdeckrepo.com) | TheLogicMaster/SDH-AnimationChanger | BSD-3-Clause | no |
| Game Theme Music | Plays a game's theme song on its page | MegalonVII/SDH-GameThemeMusic (store fork of OMGDuke's, arch.) | GPL-3.0 | no |
| GameView Music (arch.) | Background music on the game page | lcd1232/gameview-music-deck | GPL-3.0 | no |
| Deck Shelves | Customisable Steam home screen shelves | santojon/Deck-Shelves | BSD-3-Clause | no |
| Brightness Bar | Shows an on-screen bar when brightness changes | rasitayaz/decky-brightness-bar | BSD-3-Clause | no |
| Crosshair | On-screen crosshair through MangoHud | xXJSONDeruloXx/crosshair-plugin | BSD-3-Clause (template notice, own terms unconfirmed) | no |

### 2.2 Library extras

| Plugin | Purpose | Repository | Licence | Root |
|---|---|---|---|---|
| SteamGridDB | Custom artwork and capsule style tweaks from Gaming Mode | SteamGridDB/decky-steamgriddb | GPL-3.0 | no |
| ProtonDB Badges | Tappable ProtonDB badges on game pages (store fork; original OMGDuke repository archived) | bschelst/protondb-decky | GPL-3.0 | no |
| HLTB for Deck | HowLongToBeat lengths on game pages | morwy/hltb-for-deck | MIT | no |
| TabMaster | Customise, add and hide library tabs | Tormak9970/TabMaster | GPL-3.0 | no |
| PlayTime | Daily, weekly and all-time playtime including non-Steam | 0u73r-h34v3n/SDH-PlayTime | BSD-3-Clause | no |
| PlayCount | Current player counts for Steam games | itsOwen/playcount-decky | BSD-3-Clause | no |
| Non-Steam Badges | Badges on non-Steam games | sebet/decky-nonsteam-badges | BSD-3-Clause | no |
| Deck Progress Tracker | Tags games Completed, In Progress or Mastered | maroun2/deck-progress-tracker | BSD-3-Clause | no |
| IsThereAnyDeal for Deck | Price data on store pages | JtdeGraaf/IsThereAnyDeal-DeckyPlugin | GPL-3.0 | no |
| DeckRoulette | Random game from library or collection | davocarli/deck-roulette | unknown | no |
| deck-roulette (fork) | Same, maintained fork | chrisae9/deck-roulette | BSD-3-Clause | no |
| SuggestMe | Smart game suggestion from library | lemossilva/suggestme-decky-plugin | BSD-3-Clause | no |
| Emuchievements | RetroAchievements progress | EmuDeck/Emuchievements | GPL-3.0 | no |
| DeckFAQs | GameFAQs browser | SDH-Stewardship/deckfaqs | MIT | no |
| Decky Lookup | Per-game web searches (PCGamingWiki, guides) | xXJSONDeruloXx/Decky-Lookup | unknown | no |
| DeckSettings | ShareDeck and SteamDeckHQ recommended settings | davocarli/sharedeck-y | MIT | no |
| Game Settings | Deck Verified performance and settings reports | DeckSettings/decky-game-settings | BSD-3-Clause | no |
| VARTA | Labels developers and publishers by origin (Ukrainian project) | HARd/varta-decky | MIT | yes |
| Steam Status | Steam service status | bschelst/steamstatus-decky | GPL-3.0 | no |
| Free Loader | Notifications of free games (Steam, GOG, Epic, itch) | jwhitlow45/free-loader | BSD-3-Clause | no |
| Download All | Starts all scheduled downloads now | bentemple/decky-download-all | GPL-3.0 | no |

### 2.3 Performance, display and handheld control

| Plugin | Purpose | Repository | Licence | Root |
|---|---|---|---|---|
| PowerTools | CPU, GPU, TDP and SMT control, per-game | gitlab.com/NGnius/PowerTools | GPL-3.0+ | yes |
| Fantastic | Fan curve control | gitlab.com/NGnius/Fantastic | GPL-3.0+ | yes |
| Decky-Undervolt | Curve Optimiser undervolt through ryzenadj | totallynotbakadestroyer/Decky-Undervolt | custom notice (derivative work), unconfirmed | yes |
| vibrantDeck | Saturation, gamma and colour settings | libvibrant/vibrantDeck | LGPL-3.0 | no |
| MangoPeel | Custom MangoHud overlay styles | Gawah/MangoPeel | BSD-3-Clause | no |
| Reshadeck | ReShade shaders in Gamescope | safijari/Reshadeck | GPL-3.0 | no |
| LetMeReShade (arch.) | ReShade installer and manager per game | itsOwen/LetMeReShade | BSD-3-Clause | no |
| Decky-Framegen | Installs OptiScaler upscaling and frame generation mods | xXJSONDeruloXx/Decky-Framegen | BSD-3-Clause (template notice) | no |
| lsfg-vk | Installs and configures lsfg-vk (Lossless Scaling frame generation layer) | xXJSONDeruloXx/decky-lsfg-vk | BSD-3-Clause | no |
| MuraDeck | Mura correction on the Deck OLED | Moonveil-Kanata/MuraDeck | GPL-3.0 | no |
| DimmerDeck | Dimmer than minimum brightness | chenx-dust/DimmerDeck | MIT | no |
| MagicBlack | Black overlay emulating screen off (OLED) | steam3d/MagicBlackDecky | GPL-3.0 | no |
| HueSync | Handheld RGB LED control | honjow/HueSync | BSD-3-Clause | yes |
| Controller Tools (arch.) | External controller battery and charging | jfernandez/ControllerTools | GPL-3.0 | no |
| Pause Games | Pause and resume games (SIGSTOP) | wynn1212/SDH-PauseGames | GPL-3.0 | no |
| AutoSuspend | Warns and suspends at low battery | jurassicplayer/decky-autosuspend | unknown | no |
| Battery Tracker | Battery history | safijari/steam-deck-battery-tracker | BSD-3-Clause | no |
| Output Manager | Switch display and audio outputs | joeatethebeans/OutputManager | unknown | yes |
| XIVOmega | Latency mitigation for FFXIV | shingonati0n/xivomega-decky | BSD-3-Clause | yes |

### 2.4 Utilities

| Plugin | Purpose | Repository | Licence | Root |
|---|---|---|---|---|
| Storage Cleaner | Visualise and clear shader cache and compatdata | mcarlucci/decky-storage-cleaner | GPL-3.0 | no |
| MicroSDeck | Tracks which games are on which microSD card | CEbbinghaus/MicroSDeck | GPL-2.0 | no |
| Decky Recorder | Game recording | SDH-Stewardship/decky-recorder-fork | BSD-3-Clause | no |
| Decky Clipper | Screen recording outside games | Managor/Decky-Clipper | GPL-2.0 | no |
| Shotty | Copies screenshots to Pictures | safijari/Shotty | unknown | no |
| ScreenshotUploader | Uploads screenshots to cloud | codehz/DeckScreenshotManager | BSD-3-Clause | no |
| Bluetooth | Quick connect to paired devices | Outpox/Bluetooth | BSD-3-Clause | no |
| Bluetooth Wake Control | Controls Bluetooth wake from sleep (details not retrieved) | gitlab.com/finewolf-projects/decky-plugin-bluetooth-wake-control | unknown | unknown |
| MagicPods | AirPods, Beats, Galaxy Buds battery and ANC | steam3d/MagicPodsDecky | GPL-3.0 | no |
| Pixel Buddy | Pixel Buds Pro management | Phill544/Pixel-Buddy | MIT | no |
| Volume Mixer | Per-app and Bluetooth source volume | isiah-lloyd/VolumeMixer-decky | custom notice, unconfirmed | no |
| Volume Mixer (allmazz) | Per-app volume | allmazz/decky-volume-mixer | GPL-3.0 | no |
| Volume Boost | Boost beyond 100% | saumya-banthia/volume-boost | BSD-3-Clause | no |
| DeckSP | JamesDSP effects suite | jessebofill/DeckSP | unknown | no |
| Virtual Surround Sound | 7.1 to binaural through a PipeWire filter chain | DeckSettings/decky-virtual-surround-sound | BSD-3-Clause | no |
| Music Control | Media player controls | martinpl/MusicControl | GPL-3.0 | no |
| Museck | Music player | Nezreka/Museck | MIT | no |
| RadiYo! | Internet radio | isiah-lloyd/radiyo-steam-deck | MIT | no |
| Mute On Sleep | Mutes before sleep | genc-v/mute-on-sleep | BSD-3-Clause | no |
| Network Info | Interface details | kimar/decky-networkinfo (now DK1DA) | GPL-3.0 | no |
| Network Sentinel | Latency and quality diagnostics | KrishGaur1354/network-sentinel | BSD-3-Clause | no |
| Speed Test | Cloudflare speed test | Dukeman330/decky-speed-test | BSD-3-Clause | no |
| Tailscale Control | Tailscale on and off | saumya-banthia/tailscale-control | BSD-3-Clause | no |
| ZeroTier | ZeroTier control | hyacz/decky-zerotier | BSD-3-Clause | yes |
| TunnelDeck | WireGuard and OpenVPN in Gaming Mode | bkohler616/TunnelDeck | BSD-3-Clause | yes |
| ShadowDeck | Shadowsocks client | tikh-iv/ShadowDeck | unknown | yes |
| DeckyClash | Clash/Mihomo proxy | chenx-dust/DeckyClash | BSD-3-Clause | yes |
| Spoof DPI | Anti-censorship | ohaiibuzzle/decky-spoof-dpi | BSD-3-Clause | no |
| DoT DNS | DNS over TLS | ohaiibuzzle/decky-dot-dns | GPL-3.0 | yes |
| IPv6 | Enables IPv6 | spmzt/decky-ipv6 | BSD-3-Clause | yes |
| Wi-Fi Locker | Locks Wi-Fi to stop periodic scans (streaming stutter) | felipejfc/decky-wifi-locker | BSD-3-Clause | yes |
| Muon | Ad hoc networking | wtlnetwork/muon | GPL-3.0 | no |
| Syncthing | Manage Syncthing | theCapypara/steamdeck-decky-syncthing | GPL-3.0 | no |
| LocalSend | LocalSend file sharing | MoYoez/decky-localsend | BSD-3-Clause | no |
| DeckMTP | MTP over USB to a PC | dafta/DeckMTP | BSD-3-Clause | yes |
| DeckyFileServer | On-demand web file server | grimkor/DeckyFileServer | GPL-3.0 | no |
| Decky-CP | copyparty file server | 39sdev/Decky-CP | BSD-3-Clause | no |
| Decky Clipboard (arch.) | Share clipboard over LAN web page | Torther/DeckyClipboard | BSD-3-Clause | yes |
| KDE Connect | KDE Connect in Gaming Mode | safijari/Decky-KDE-Connect | BSD-3-Clause | no |
| Decky Notifications | Phone notifications through the KDE Connect protocol | Firemoon777/decky-notifications | BSD-3-Clause | no |
| Decky Terminal | Terminal emulator in Gaming Mode | Alex4386/decky-terminal | unknown | no |
| SSH Switch | SSH on and off, startup, account password | nicholasyoannou/decky-ssh-switch | MIT | yes |
| AutoFlatpaks | Flatpak update management | jurassicplayer/decky-autoflatpaks | unknown | yes |
| Inhibit Screen Saver | Stops dimming during video playback | xfangfang/DeckyInhibitScreenSaver | BSD-3-Clause | no |
| Docky | Dock, AC and controller triggered automation, Sunshine control | datbird/docky | MIT | yes |
| BetterKeyboard | Physical keyboard improvements | chenx-dust/BetterKeyboard | BSD-3-Clause | yes |
| Input Disabler | Disable built-in inputs | BurritoSpray/steamdeck-input-disabler | BSD-3-Clause | yes |
| Decky Dictation | Speech to text (Vosk) | cboiangiu/decky-dictation (now antiquitte) | BSD-3-Clause | no |
| Decky Translator | Translate on-screen text | cat-in-a-box/Decky-Translator | GPL-3.0 | no |
| Notebook | Notes during play | wynn1212/SDH-Notebook | GPL-3.0 | no |
| Simple Timer | Timer | decktools-xyz/simple-timer | BSD-3-Clause | no |
| Alarme | Alarms, timers, Pomodoro | lemossilva/alarme-decky-plugin | BSD-3-Clause | no |
| DeckPass | KeePassXC passwords | Teppichseite/DeckPass | GPL (version not read) | no |
| Web Browser | Tabbed browser | jessebofill/DeckWebBrowser | GPL-3.0 | no |
| Decky PiP | Picture-in-picture streams | rossimo/decky-pip | BSD-3-Clause | no |
| TS3 QuickAccess | TeamSpeak 3 client | ILadis/ts3-qs4sd | GPL-2.0 | no |
| Discord Status (arch.) | Current game to Discord | andrewburgess/steamdeck-discord-status | BSD-3-Clause | no |
| FriendsFix | Friends list fix (self-hosted repository, not checked) | git.catvibers.me/aa/FriendsFix | unknown | unknown |
| Decky Spy | Memory and process monitor | Seraphli/decky-spy | BSD-3-Clause | no |
| Multi User | Run a game from another account | nikitaclicks/decky-multi-user | BSD-3-Clause | no |
| DeckyClocker | Changes the SteamOS clock (per its description) | Jaccident/DeckyClocker | BSD-3-Clause | yes |

### 2.5 Launchers and stores

| Plugin | Purpose | Repository | Licence | Root |
|---|---|---|---|---|
| Junk-Store | Epic, GOG and other stores launcher (Pro version paid, closed) | ebenbruyns/junkstore | BSD-3-Clause | no |
| NonSteamLaunchers | Installs launchers and Proton-GE, adds shortcuts | moraroy/NonSteamLaunchersDecky | MIT | no |
| EmuDecky | EmuDeck companion | EmuDeck/EmuDecky | AGPL-3.0 | no |
| Quick Launch | Launch apps from the quick menu without shortcuts | Fisch03/SDH-QuickLaunch | GPL-3.0 | yes |
| Desktop Apps | Apps browser | allmazz/decky-desktop-apps | GPL-3.0 | no |
| Bash Shortcuts (arch.) | Quick menu shortcuts running Bash | Tormak9970/bash-shortcuts | BSD-3-Clause | no |
| Wine Cellar | Manage compatibility tools (GE-Proton and others) | FlashyReese/decky-wine-cellar | MIT | no |
| Launch Options | Launch option manager | Wurielle/decky-launch-options | unknown | no |
| Proton Launch | Proton launch option manager | moi952/decky-proton-launch | BSD-3-Clause | no |
| CheatDeck | Launch options for cheats and trainers | SheffeyG/CheatDeck | GPL-3.0 | no |
| GamesPrefixManager | Proton prefix management | Saad-Alareqi/GamesPrefixManager | GPL-3.0 | yes |
| MoonDeck | Moonlight streaming of the Steam library | MoonDeckTeam/moondeck | GPL-3.0 | no |
| Decky Sunshine | Toggle Sunshine streaming server | s0t7x/decky-sunshine | unknown | yes |
| XR Gaming | XR glasses virtual display modes | wheaney/decky-XRGaming | GPL-3.0 | yes |

### 2.6 Save tools (Keepsake's own area)

| Plugin | Purpose | Repository | Licence | Root |
|---|---|---|---|---|
| Decky Cloud Save | rclone cloud save sync | GedasFX/decky-cloud-save | BSD-3-Clause | no |
| SDH-GameSync | Per-game fork of Decky Cloud Save (rclone) | AkazaRenn/SDH-GameSync | unknown | no |
| decky-ludusavi | Ludusavi front end | GedasFX/decky-ludusavi | BSD-3-Clause | no |
| Save Manager | Store and load save files | SDH-Stewardship/decky-save-manager | GPL-3.0 | no |
| Steamback | Versioned snapshots for Steam Cloud games | geeksville/steamback | GPL-3.0 | no |

### 2.7 Other

| Plugin | Purpose | Repository | Licence | Root |
|---|---|---|---|---|
| Memory Deck | scanmem memory editor | CameronRedmore/memory-deck | GPL-3.0 | yes |
| Reroll | Memory scanner | kayon/decky-reroll | GPL-3.0 | yes |

### 2.8 Well-known plugins outside the store

| Plugin | Purpose | Repository | Licence | Root |
|---|---|---|---|---|
| SimpleDeckyTDP | TDP, GPU and CPU control for PC handhelds | aarron-lee/SimpleDeckyTDP | BSD-3-Clause | yes |
| LegionGoRemapper | Legion Go remapping, LEDs, controller | aarron-lee/LegionGoRemapper | BSD-3-Clause | yes |
| hhd-decky (arch.) | Handheld Daemon settings from Gaming Mode | hhd-dev/hhd-decky | BSD-3-Clause | yes |
| PowerControl | TDP, CPU and GPU, fans, for many handhelds | mengmeet/PowerControl | BSD-3-Clause | yes |
| Unifideck | Epic, GOG, Amazon, Ubisoft, xCloud in one library | mubaraknumann/unifideck | GPL-3.0 | no |
| ProtonDB Badges (original, arch.) | Original of the store fork | OMGDuke/protondb-decky | GPL-3.0 | no |
| Game Theme Music (original, arch.) | Original of the store fork | OMGDuke/SDH-GameThemeMusic | GPL-3.0 | no |

The brief also named Junk-Store, Decky-Framegen, CSS Loader, Audio Loader, SteamGridDB, Animation Changer, ProtonDB Badges, HLTB, Tab Master, Storage Cleaner, Decky Recorder, Wine Cellar, MagicPods, Bluetooth, PlayTime, PlayCount and lsfg-vk (the Lossless Scaling frame generation plugin). All of these are in the store database, so they appear in the tables above. I found no Heroic-specific Decky plugin.

## 3. Feature verdicts per area

Constraints behind the verdicts:
- principle 9: no bundled or downloaded binaries;
- principle 15: Steam writes only through `SteamClient`;
- the network allowlist;
- GPL code cannot be copied (clean-room reimplementation of a feature is fine);
- the root helper's job list (ADR-0075, ADR-0083).

### 3.1 Looks

| Feature | Verdict |
|---|---|
| CSS theme engine (deckthemes packs) | **Skip as an engine.** See 3.1.1. |
| Sync CSS Loader themes, presets and settings between devices | **Add.** It is Keepsake's core skill. Replicate `~/homebrew/themes/` (shared by CSS Loader and Audio Loader) and the CSS Loader settings, which live under `~/homebrew/settings/` (exact file name to verify on device). Needs a write allowlist entry (escalation item, needs an ADR). No licence issue: no code is copied. |
| UI sound packs | **Skip as an engine** (Audio Loader is MIT, mature and owns the sound hooks). **Add sync** of packs with the theme folder above. |
| Boot and suspend animations | **Add (small).** Mechanism, verified in Animation Changer's source: copy a `.webm` into `~/.steam/root/config/uioverrides/movies/`, as `deck_startup.webm` for boot plus suspend variants. No root. Local files and sync between devices need no new endpoint. Browsing steamdeckrepo.com would need an endpoint ADR. Write the code fresh; Animation Changer is BSD-3, so copying with attribution would also be allowed. |
| Game page theme music | **Skip.** Low value, and it needs YouTube or a similar source outside the allowlist. |
| Home screen shelves (Deck Shelves) | **Skip.** Deep UI patching that breaks with client updates; better left to a dedicated plugin. |
| Brightness bar, crosshair | **Skip.** Low value. Crosshair depends on MangoHud configuration. |

#### 3.1.1 deckthemes.com theme pack format, and whether Keepsake could support packs without CSS Loader

This is verified from the CSS Loader source: `css_theme.py`, `css_themepatch.py`, `css_themepatchcomponent.py`, `css_inject.py` and `css_browserhook.py`.

**Folder layout.** Each pack is a folder in `~/homebrew/themes/<name>/` with a `theme.json` and its `.css` files and images. CSS Loader symlinks the themes folder to `<steam>/steamui/themes_custom`, so images are served as `/themes_custom/...`. Presets are themes that carry the `PRESET` flag.

**theme.json top-level fields:**

| Field | Meaning |
|---|---|
| `name` | Required. |
| `display_name`, `id`, `author` | Optional. |
| `version` | Optional. Defaults to `v1.0`. |
| `manifest_version` | Optional. Defaults to 1. A newer version than the loader supports is rejected. |
| `flags` | Optional. For example `PRESET` and `KEEP_DEPENDENCIES`. |
| `tabs` | Optional. Custom tab aliases, with `default`. |
| `dependencies` | Optional. Other themes, with patch values. |
| `inject` | Optional. A map of CSS file to target list, or `"--css-var": [value, ...targets]` for a variable. |
| `patches` | Optional. A map of patch name to patch. |

**Patches.**
- A patch has `type`, which is `dropdown` (the default), `checkbox` (needs the options `Yes` and `No`), `slider` or `none`.
- It also has `default` and `values`. Each value is an `inject` map. That is the v2 form; v1 puts the values at the top level.
- A patch can have `components` of type `color-picker` or `image-picker`. Each component has `name`, `on` (the value it belongs to), `css_variable`, `default` and `tabs`.
- A colour picker sets `--var`, plus `_r`, `_g`, `_b` and `_rgb` variants.
- An image picker takes a path relative to the theme. Absolute paths and `..` are rejected.

**Targets.** Targets are CEF window or tab names, or aliases:
- `bigpicture`, from the Valve Steam Gamepad window;
- `bigpictureoverlay`, which is `QuickAccess` and `MainMenu`;
- `desktop`, `desktoppopup`, `desktopcontextmenu`, `desktopchat` and `store`;
- legacy aliases `SP`, `QuickAccess`, `MainMenu` and `All`.

**How it works.** The backend connects to Steam's CEF remote debugger on `127.0.0.1:8080`. It runs `Runtime.evaluate` in each matching tab to add `<style class="css-loader-style">` elements.

It also rewrites Valve's hashed class names using `css_translations.json`. DeckThemes maintains this file and updates it with each client release. Without it, most themes break after a Steam update.

**Could Keepsake support packs without CSS Loader? Not realistic, and not advisable.**
1. **Class translations.** Keepsake would have to fetch DeckThemes' translation map. That is a new endpoint, and a dependency on their service anyway.
2. **Licence.** The engine is GPL-3.0, so a clean-room rewrite would be needed.
3. **Window reach.** Reaching windows other than the one the plugin runs in would mean either the CEF debugger on port 8080 (CLAUDE.md says to avoid that port, and it is CSS Loader's own channel) or frontend access to other windows' documents (unverified).
4. **Clashes.** Two injectors fighting over the same windows would cause coexistence problems.

The clean option is to detect CSS Loader, sync its themes folder and settings, and link to it. Individual themes carry their own author licences on deckthemes.com.

### 3.2 Library extras

| Feature | Verdict |
|---|---|
| SteamGridDB artwork | **Already in Keepsake** for streaming tiles and installs (ADR-0027, ADR-0081). **Add (small):** "Find artwork" for any non-Steam game, using the same code path and the same endpoint. |
| Capsule style tweaks (square, uniform) | **Skip.** CSS territory; leave to SteamGridDB and CSS Loader. |
| ProtonDB badge on the game page | **Add.** Advisor already has the ProtonDB data source. Show a tier badge using the R18 badge mechanism. Clean-room: ProtonDB Badges is GPL-3.0. |
| Deck Verified, ShareDeck and community settings reports | **Already in Keepsake** (Advisor sources). |
| PCGamingWiki and guide lookups | **Already in Keepsake** (Advisor). **Add (tiny):** a "Copy link" or "Open in browser" item per game, no new endpoint. |
| HowLongToBeat lengths | **Skip.** No official API, the scraping is fragile, and the endpoint is not on the allowlist. |
| Library tabs and collections | **Skip** (TabMaster owns it). **Add sync** of TabMaster settings between devices (`~/homebrew/settings/TabMaster`, to verify). |
| Playtime | **Already in Keepsake** (across devices, ADR-0049). **Add (optional):** import PlayTime's local database once, so history is not lost (read-only). |
| Non-Steam badges | **Already in Keepsake** (R18 library badges). |
| Player counts, prices, free game alerts, Steam status | **Skip.** Off-mission, and new endpoints. |
| Completion tags, random game, suggestions | **Skip.** Low value; collections writes would need Steam writes outside Keepsake's remit. |
| RetroAchievements | **Skip.** Dedicated plugin (EmuDeck, GPL). |
| GameFAQs browser, VARTA labels | **Skip.** Off-mission. |
| Download all queued | **Skip.** Low value. |

### 3.3 Performance and display

| Feature | Verdict |
|---|---|
| TDP, SPL, SPPT and FPPT, per-game profiles | **Already in Keepsake** (ADR-0076, ADR-0084). |
| Fan curves | **Already in Keepsake** (ADR-0085). |
| Battery charge limit | **Already in Keepsake** (ADR-0077). |
| RGB and stick lights, controller settings | **Already in Keepsake** (ADR-0086). The power LED is not built. |
| CPU and GPU clocks, SMT, governor | **Add, only if the device run shows a need.** Needs root, so it would need new root helper jobs; a decision belongs in ADR-0075. PowerTools is GPL, so clean-room only. |
| Undervolt (Curve Optimiser) | **Skip.** Needs `ryzenadj`, which is a binary not on the System Binary Register. It carries a stability risk and needs root beyond the helper's jobs. |
| Colour saturation and gamma | **Consider later.** Gamescope supports this through X atoms, but the method is unverified on both devices, and the Legion Go IPS and Go 2 OLED differ. vibrantDeck is LGPL-3.0, so clean-room only. |
| MangoHud overlay styles | **Skip.** Steam's performance overlay covers the need. MangoPeel is the dedicated tool. |
| ReShade, OptiScaler and frame generation, lsfg-vk | **Skip.** They download or install DLLs and Vulkan layers, which breaks principle 9. Advisor may mention them as read-only text. |
| Mura correction, extra dimming, OLED black overlay | **Skip.** Specific to the Deck OLED, or low value. |
| External controller battery | **Already in Keepsake**, or close to it (controllers read-only stage and reconnect help). Check that battery percentage is shown. |
| Pause a game | **Add (small).** Keepsake already freezes games under a watchdog (principle 11). A user-triggered pause and resume reuses that code. Clean-room: Pause Games is GPL-3.0. |
| Auto-suspend at low battery | **Skip.** SteamOS already handles critical battery. |
| Output switching | **Skip.** Needs root; Steam handles it. |
| Game-specific network hacks (XIVOmega) | **Skip.** |

### 3.4 Utilities

| Feature | Verdict |
|---|---|
| Shader cache and compatdata clean-up | **Already in Keepsake** (Storage page, ADR-0052). **Add (small):** clear orphaned compatdata for uninstalled app IDs, with the same reversible rules. |
| microSD card game index | **Add.** Keepsake already reasons about SD card labels and canonical roots. List which games live on which card, including cards not inserted. Clean-room: MicroSDeck is GPL-2.0. |
| Recording and clipping | **Skip.** Steam Game Recording is built in. |
| Screenshot copy and upload | **Consider later.** "Back up screenshots to your cloud" reuses Saves' cloud providers. Low priority. |
| Bluetooth quick connect | **Largely already in Keepsake** (reconnect help, device list). **Add (small):** one-tap connect for paired devices in the quick menu, if not already there. |
| Earbud battery and ANC | **Skip.** Vendor-specific protocols. |
| Volume mixers, boost, DSP, virtual surround | **Skip.** PipeWire tooling; better left to dedicated plugins. |
| Music, radio, PiP, web browser, TeamSpeak, Discord | **Skip.** Off-mission. |
| VPNs, proxies, DNS, IPv6 | **Skip.** Most need root; off-mission. |
| Wi-Fi scan lock | **Skip.** Keepsake already has Wi-Fi power saving (ADR-0079); a lock needs root. |
| Network diagnostics, speed test | **Consider later.** The Replication link test already measures peer throughput. Show it as "Link speed" on Devices. No third-party endpoint. |
| File transfer (Syncthing, LocalSend, MTP, file servers, clipboard) | **Already in Keepsake** for its own purposes (Replication). Skip general file sharing. |
| KDE Connect, phone notifications | **Skip.** |
| Terminal, SSH toggle | **Skip.** Principle 7 is that nothing should need a terminal. SSH toggling needs root. |
| Flatpak updates | **Skip.** Needs root (system flatpaks); Discover handles it. |
| Sleep and screensaver inhibit | **Already in Keepsake** (the sleep inhibitor during transfers). |
| Dock automation | **Consider later.** Applying a device control profile on AC or dock is a natural follow-on to per-game profiles. No root beyond existing jobs. |
| Mute before sleep | **Add (tiny, optional)** next to handheld controls. Needs `wpctl` or PulseAudio, which would need a System Binary Register entry, so probably skip. |
| Notes, timers, alarms, translator, dictation, passwords, multi-account, memory editors | **Skip.** Off-mission. |

### 3.5 Launchers and stores

| Feature | Verdict |
|---|---|
| Epic, GOG and Amazon libraries (Junk-Store, Unifideck, NonSteamLaunchers) | **Skip.** They need binaries such as `legendary` and `gogdl`, store sign-in endpoints outside the allowlist, and in places GPL code. **Coexist instead:** make sure Replication and Saves handle the shortcuts these tools create. Junk-Store and Unifideck prefixes are ordinary shortcut compatdata. |
| Compatibility tool install (GE-Proton) | **Add.** Keepsake already copies compatibility tools between devices. Installing a GE-Proton release from GitHub uses release assets. These are allowlisted only for update checks, so widening that is an endpoint ADR. Extract with stdlib `tarfile`, using safe member filtering, into `~/.steam/root/compatibilitytools.d/`. That folder needs a write allowlist check or an ADR. Wine Cellar is MIT, so its approach can be studied freely. |
| Launch options editor with presets | **Add.** Keepsake already writes launch options through `SteamClient` (principle 15), stores the originals and reads them back. Offer presets such as `PROTON_*`, `gamemoderun` and `mangohud`, on an explicit user action. Each preset should be checked against the register before it is offered. |
| Trainers and cheats in launch options | **Skip.** |
| Prefix management | **Already in Keepsake** (reset prefix, keep saves). |
| Quick launch without shortcuts, Bash shortcuts | **Skip.** Quick Launch needs root; Bash shortcuts are terminal territory. Keepsake's quick menu shortcuts cover its own features. |
| Emulator front end | **Already in Keepsake** for copying emulator games (ADR-0087). Skip as a front end; EmuDecky is AGPL. |
| Moonlight and Sunshine streaming | **Already in Keepsake**, in part (streaming tiles, R9). Skip the server control, which needs root and the Sunshine binary. |
| XR glasses | **Skip.** |

### 3.6 Save tools

All of these are **already in Keepsake** and superseded by it: Decky Cloud Save, SDH-GameSync, decky-ludusavi, Save Manager and Steamback. They matter only for coexistence and migration (section 5).

## 4. Recommended build order

Each stage is a release of its own, following the queue rules.

1. **Looks**
   - Boot and suspend animations, from local files and synced between devices.
   - Sync of `~/homebrew/themes` (CSS Loader and Audio Loader packs) plus CSS Loader settings and presets through Replication, with a write allowlist ADR.
   - Detect CSS Loader and Audio Loader and link to them. No theme engine.
2. **Library extras**
   - ProtonDB tier badge on the game page, using Advisor data.
   - "Find artwork" for any non-Steam game.
   - Sync of TabMaster and SteamGridDB settings.
   - Optional one-time PlayTime import.
   - PCGamingWiki "open or copy link".
3. **Performance and display**
   - Pause and resume a game, reusing the freeze watchdog.
   - Profile on AC or dock.
   - Clocks and SMT only if needed, with root helper jobs per ADR-0075.
   - Saturation only after a gamescope probe on both devices.
4. **Utilities**
   - SD card game index.
   - Orphaned compatdata clean-up.
   - Bluetooth one-tap connect in the quick menu, if missing.
   - Link speed on Devices.
   - Later: screenshot backup to cloud.
5. **Launchers and stores**
   - Launch options editor with presets.
   - GE-Proton install, with an endpoint ADR and a write allowlist check.
   - Coexistence checks for Junk-Store, Unifideck and NonSteamLaunchers shortcuts in Replication and Saves.

## 5. Coexistence notes

**How to detect other plugins.** Read `~/homebrew/plugins/*/plugin.json` read-only and match the `name` field. Decky's home can be overridden by `DECKY_HOME`; CSS Loader honours it too. Also check `~/homebrew/settings/<plugin>` for configuration. Use a frontend list of loaded plugins only if the `@decky/api` types confirm one exists (not verified). For system daemons, query systemd units read-only.

| Clash | Plugins | Risk | Detection and handling |
|---|---|---|---|
| TDP, power limits, CPU and GPU | PowerTools, SimpleDeckyTDP, PowerControl, hhd-decky, Decky-Undervolt, also Steam's own TDP slider | Last writer wins, and the settings flap on game switch | Detect by plugin name. Also detect the `hhd` service and Steam's per-game TDP setting. Warn on Keepsake's control page and offer "let the other tool manage TDP". |
| Fans | Fantastic, PowerControl, LegionGoRemapper | Two curves fight | Same detection. Keepsake's fan control off by default when one of these is found. |
| RGB and controller settings | HueSync, LegionGoRemapper, hhd (Bazzite often ships hhd or InputPlumber) | LED and mapping flicker; hidraw contention | Detect plugins, plus the `hhd` and `inputplumber` units. Pause Keepsake's lights and controller jobs. |
| Theme and CSS injection | CSS Loader (style elements with class `css-loader-style`), SteamGridDB style tweaks | Clashes if Keepsake injects CSS | Keepsake should not inject global CSS. Its own badges should use scoped class names. |
| Boot videos | Animation Changer | Both write `uioverrides/movies` | Detect it. Keepsake defers, or takes over only after the user confirms. Record the original file. |
| Library badges and route patches | ProtonDB Badges, Non-Steam Badges, HLTB, PlayCount, IsThereAnyDeal, Game Theme Music | Overlapping elements on the game page | Use a distinct position. Hide Keepsake's ProtonDB badge when ProtonDB Badges is present. |
| Artwork | SteamGridDB plugin | Both set artwork through `SteamClient` | Read back before replacing. Never overwrite artwork Keepsake did not set without asking. |
| Saves | Decky Cloud Save, SDH-GameSync, decky-ludusavi, Save Manager, Steamback, plus Ludusavi and rclone during cutover | Double restores and divergent histories | Already covered by the build prompt section 19 cutover. Warn per game when another tool manages the same paths. |
| Launch options | Launch Options, Proton Launch, CheatDeck, NonSteamLaunchers | Overwrites Keepsake's wrapper or presets | Read back after every write. Show "changed outside Keepsake" rather than reverting silently. |
| Compatibility tools | Wine Cellar, NonSteamLaunchers (installs GE) | Duplicate installs or removal of a tool a game uses | Before removing anything, check which games reference the tool. Treat existing folders as user-owned. |
| Process freezing | Pause Games | A Keepsake watchdog could resume a game the user paused elsewhere, or the reverse | Detect it. Only resume processes Keepsake itself stopped, which is already the watchdog's rule. Document the interaction. |
| Sleep inhibition | Inhibit Screen Saver, Docky | Stacking inhibitors (harmless) | No action needed. Keepsake must release its own. |
| Bluetooth | Bluetooth plugin, Bluetooth Wake Control, MagicPods | Keepsake's confirmed `bluetoothd` restart disconnects their devices | The restart prompt already asks for confirmation. Mention other Bluetooth plugins in it. |
| Wi-Fi | Wi-Fi Locker | Conflicts with Keepsake's Wi-Fi power saving | Detect it and show a note. |
| Store launchers | Junk-Store, Unifideck | Their shortcuts and prefixes are replicated by Keepsake | Make sure replication carries their launch wrapper scripts, or marks such games "needs the store plugin on the other device". |

## 6. Sources

**Plugin data**
- Store database: https://github.com/SteamDeckHomebrew/decky-plugin-database (`.gitmodules` and the `plugins/` folder, read through `gh api` on 22 November 2026).
- Store API: https://plugins.deckbrew.xyz/plugins (blocked by the corporate proxy, not used).
- Each plugin's GitHub repository: licence detection, LICENCE file heads, `plugin.json` flags, descriptions and READMEs, as listed in section 2.
- GitLab project API for PowerTools and Fantastic. Bluetooth Wake Control and FriendsFix could not be read.

**Mechanisms checked in source**
- CSS Loader theme format: `css_theme.py`, `css_themepatch.py`, `css_themepatchcomponent.py`, `css_inject.py`, `css_browserhook.py`, `css_utils.py` and `css_remoteinstall.py` at https://github.com/DeckThemes/SDH-CssLoader
- Audio Loader pack location: https://github.com/DeckThemes/SDH-AudioLoader (README)
- Animation Changer mechanism: https://github.com/TheLogicMaster/SDH-AnimationChanger (`main.py`)

**Press reports**
- Unifideck: https://github.com/mubaraknumann/unifideck and https://www.techradar.com/gaming/steam-deck/if-you-ever-doubted-steamos-think-again-this-new-decky-loader-plugin-is-possibly-the-best-one-yet
- NonSteamLaunchers removal: https://gamingonlinux.com/2024/10/nonsteamlaunchers-gets-booted-from-steam-deck-plugin-store-decky-loader
- Junk Store paid version: https://gamingonlinux.com/2025/03/junk-store-plugin-for-steam-deck-plans-new-release-as-closed-source-paid-software-to-run-other-stores

**Keepsake context**
- `docs/plan.md` and `CHANGELOG.md` in this repository, for what Keepsake already does.

---

**Unverified, to check before building:**
- the exact CSS Loader and TabMaster settings file names under `~/homebrew/settings/`;
- whether the Decky frontend exposes a list of loaded plugins;
- the gamescope colour atoms;
- what DeckyClocker, Bluetooth Wake Control and FriendsFix actually do.

Nine licences are unknown and should be checked again before studying those plugins' code: DeckRoulette (davocarli), Decky Lookup, AutoSuspend, Output Manager, DeckSP, Decky Terminal, ShadowDeck, Launch Options and Decky Sunshine. A few more have custom notices that need a manual read: Decky-Undervolt, Volume Mixer (isiah-lloyd), Crosshair and Decky-Framegen.
