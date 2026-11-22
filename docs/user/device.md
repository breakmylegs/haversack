# Your device

Keepsake's **Device** section shows your handheld, and lets you choose its performance for each game. It is built for the Legion Go and Legion Go 2, and works on any SteamOS or Bazzite device where Valve's steamos-manager runs.

## Status

**Device**, **Status** shows:

- the model Keepsake recognised;
- its power range and screen;
- the battery and charging;
- live readings, every 2 seconds:
  - temperatures;
  - fan speed;
  - power;
  - Lenovo's performance mode;
  - the BIOS version;
  - CPU boost and threads.

Keepsake only reads these.

## Power

**Device**, **Power** has:

- **Mode:** Quiet, Balanced, Performance or Custom. On the Legion Go these are the same modes as Legion L + Y.
- **TDP:** the power limit in watts. Setting it switches to Custom, the only mode where the firmware uses it.
- **CPU boost:** on or off.

While a game runs, what you choose is kept for that game and applied each time you start it. When you quit, Keepsake puts back what was there before. The same controls are in the quick access menu, under **Now playing**.

Keepsake never fights another tool:

- If SimpleDeckyTDP, PowerControl, LegionGo2Companion, Legion Go Toolbox, Legion Center or Handheld Daemon manages performance, Keepsake only shows the settings, and says which tool is in charge.
- If Steam's own performance settings change something Keepsake set, Keepsake leaves Steam's value until you next start the game.

Keepsake changes these settings through Valve's steamos-manager, and never needs root.

## Battery

**Device**, **Battery** has **Stop charging at 80%**, Lenovo's charge limit. It keeps the battery healthier if the device is plugged in for long spells. The same toggle is in the quick access menu.

Keepsake changes it through Valve's steamos-manager. Where steamos-manager does not offer it yet, Battery shows whether the limit is on and tells you where to change it: Steam's settings, Power.

## Controllers

**Device**, **Controllers** shows each controller's battery, the settings the controllers report, and the stick lights. Remap buttons, set dead zones and use the gyro in Steam's controller settings. Changing the controllers' own settings and the lights needs root, which waits for a separate decision.

## Other

**Device**, **Other** has:
- **Wi-Fi power saving**, through steamos-manager. Turn it off if streaming or online games stutter.
- **A BIOS check**, with what is known about your Legion Go's BIOS version.

Refresh rate, frame limit and brightness stay in Steam's own quick access menu.

## Coming next

Fan curves, and changing the controllers' settings and lights, need root. They wait for a separate decision.
