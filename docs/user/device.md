# Your device

Keepsake's **Device** section shows your handheld, and lets you choose its performance for each game. It is built for the Legion Go and Legion Go 2, and works on any SteamOS or Bazzite device where Valve's steamos-manager runs.

## Status

**Device**, **Device status** shows:

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

### Separate power limits

With the Keepsake Helper installed, **Device**, **Power** also has **Separate power limits**:
- **SPL** is the sustained power;
- **SPPT** is the slow boost;
- **FPPT** is the fast boost.

Move the sliders, then select **Apply**. Keepsake switches to Custom mode first, because the firmware ignores the limits in any other mode. With a game running, the limits are kept for that game, like the TDP.

## Fans

**Device**, **Fans** shows the temperature and fan speed. With the Keepsake Helper installed:

- **Legion Go 2:**
  - Switch on **Keepsake controls the fan**, then edit a curve: each point is a temperature and a fan speed.
  - Save it, make it the default, or use it in the current performance mode or for the game you are playing.
  - **Smooth curve** blends between points; off, each point's speed holds until the next.
  - The fan speeds up at once and slows down gently. At 101 °C it runs at full speed whatever the curve says.
  - If Keepsake stops, the fan goes back to the firmware within seconds. **Hand back** does it straight away.
  - On a BIOS other than RRCN16WW with EC 1.16, run **the fan test** first. It takes about 15 seconds.
  - **Unlock wider limits** lets curves reach 5200 RPM. It is off by default, because it is louder and wears the fan more.
- **Legion Go:**
  - **Full fan speed** (kernel 7.2 and later).
  - The Legion Go's own fan table needs a kernel module SteamOS does not include, so curves are not offered yet.

If another fan tool is installed (or Handheld Daemon is running), Keepsake only shows the readings.

## Battery

**Device**, **Battery** has **Stop charging at 80%**, Lenovo's charge limit. It keeps the battery healthier if the device is plugged in for long spells. The same toggle is in the quick access menu.

Keepsake changes it through Valve's steamos-manager. Where steamos-manager does not offer it yet, Battery shows whether the limit is on and tells you where to change it: Steam's settings, Power.

## Controllers

**Device**, **Controllers** shows each controller's battery, the settings the controllers report, and the stick lights. Remap buttons, set dead zones and use the gyro in Steam's controller settings. Changing the controllers' own settings and the lights needs root, which waits for a separate decision.

## Reconnect help

**Device**, **Reconnect help** is for Bluetooth controllers, often clones, that pair once and then will not reconnect when you press their normal button.

1. Pair the controller in Steam's Bluetooth settings.
2. Find it in the list and turn on help for it. Help acts only on the controllers you turn it on for.
3. Select **Help options**:
   - **Pair and commit** (on by default): the next time you pair this controller, Keepsake connects to it at once, so that it saves the pairing. Forget it and pair it again after turning help on.
   - **Reconnect**: put the controller in pairing mode (on a DualShock 4, hold Share and PS until the light flashes quickly), then select Reconnect. This is also in the quick menu.
   - **Diagnose**: turn the controller off, wait 10 seconds, select **Start** and press the controller's normal button once. Keepsake says what went wrong and what to try.
   - **Read stored host over USB** (DualShock 4 on a USB data cable): whether the controller will call this handheld.
   - **Export report bundle**: the last diagnosis and the Bluetooth journal lines in a zip, to share on an issue. This handheld's address is replaced.
   - **Full report mode** (DualShock 4 only): for clones that send reduced reports, such as a missing touchpad or motion.

The desktop app has the same page under Device, Reconnect help. Install the Keepsake Helper from Gaming Mode.

The list also shows a note when a controller's address is not from a registered manufacturer. That is only information: Keepsake never acts on it.

If a controller connects and drops at once, Keepsake suggests a diagnosis. It does nothing to the controller unless you choose.

### The Keepsake Helper: cable pairing and the SSP gate

The lasting fixes need root, so they run in a small separate plugin, the **Keepsake Helper**. Select **Install helper** at the top of Reconnect help. Keepsake checks the helper's signature, and Decky asks you to confirm. After each Keepsake update, select **Update helper**.

- **Cable pairing** (DualShock 4 and clones using its IDs):
  1. Connect the controller with a USB data cable.
  2. Open its Help options and select **Cable pair**, then **Confirm**. Bluetooth restarts, so every Bluetooth device drops for a few seconds. It never runs during a game.
  3. Unplug the controller, turn it off, and press PS.

  If it still fails, try once more with **Reversed key order**. **Restore backup** puts back the pairing from before.
- **SSP gate:** offered when the diagnosis says the controller is refused while security starts. It lowers Bluetooth security for the whole adapter, so it asks twice. Secure Simple Pairing comes back on while you pair, when you switch the gate off, and by itself if Keepsake stops.
- **Bluetooth capture:** with the helper, Diagnose also records 40 seconds of Bluetooth traffic, to tell the causes apart.

## Other

**Device**, **More device settings** has:
- **Wi-Fi power saving**, through steamos-manager. Turn it off if streaming or online games stutter.
- **A BIOS check**, with what is known about your Legion Go's BIOS version.

Refresh rate, frame limit and brightness stay in Steam's own quick access menu.

## Coming next

Fan curves, and changing the controllers' settings and lights, need root. They wait for a separate decision.
