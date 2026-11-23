# Your device

Haversack's **Device** section shows your handheld, and lets you choose its performance for each game. It is built for the Legion Go and Legion Go 2, and works on any SteamOS or Bazzite device where Valve's steamos-manager runs.

## Status

**Device**, **Status** shows:

- the model Haversack recognised;
- its power range and screen;
- the battery and charging;
- live readings, every 2 seconds:
  - temperatures;
  - fan speed;
  - power;
  - Lenovo's performance mode;
  - the BIOS version;
  - CPU boost and threads.

Haversack only reads these.

### More device settings

**Device**, **Status** has:
- **Wi-Fi power saving**, through steamos-manager. Turn it off if streaming or online games stutter.
- **A BIOS check**, with what is known about your Legion Go's BIOS version.

Refresh rate, frame limit and brightness stay in Steam's own quick access menu.

## Power and battery

**Device**, **Power and battery** has:

- **Mode:** Quiet, Balanced, Performance or Custom. On the Legion Go these are the same modes as Legion L + Y.
- **TDP:** the power limit in watts. Setting it switches to Custom, the only mode where the firmware uses it.
- **CPU boost:** on or off.

While a game runs, what you choose is kept for that game and applied each time you start it. When you quit, Haversack puts back what was there before. The same controls are in the quick access menu, under **Now playing**.

Haversack never fights another tool:

- If SimpleDeckyTDP, PowerControl, LegionGo2Companion, Legion Go Toolbox, Legion Center or Handheld Daemon manages performance, Haversack only shows the settings, and says which tool is in charge.
- If Steam's own performance settings change something Haversack set, Haversack leaves Steam's value until you next start the game.

Haversack changes these settings through Valve's steamos-manager, and never needs root.

### Separate power limits

With the Haversack Helper installed, **Device**, **Power and battery** also has **Separate power limits**:
- **SPL** is the sustained power;
- **SPPT** is the slow boost;
- **FPPT** is the fast boost.

Move the sliders, then select **Apply**. Haversack switches to Custom mode first, because the firmware ignores the limits in any other mode. With a game running, the limits are kept for that game, like the TDP.

### Battery

**Device**, **Power and battery** has **Stop charging at 80%**, Lenovo's charge limit. It keeps the battery healthier if the device is plugged in for long spells. The same toggle is in the quick access menu.

Haversack changes it through Valve's steamos-manager. Where steamos-manager does not offer it yet, Battery shows whether the limit is on and tells you where to change it: Steam's settings, Power.

## Fans

**Device**, **Fans** shows the temperature and fan speed. With the Haversack Helper installed:

- **Legion Go 2:**
  - Switch on **Haversack controls the fan**, then edit a curve: each point is a temperature and a fan speed.
  - Save it, make it the default, or use it in the current performance mode or for the game you are playing.
  - **Smooth curve** blends between points; off, each point's speed holds until the next.
  - The fan speeds up at once and slows down gently. At 101 °C it runs at full speed whatever the curve says.
  - If Haversack stops, the fan goes back to the firmware within seconds. **Hand back** does it straight away.
  - On a BIOS other than RRCN16WW with EC 1.16, run **the fan test** first. It takes about 15 seconds.
  - **Unlock wider limits** lets curves reach 5200 RPM. It is off by default, because it is louder and wears the fan more.
- **Legion Go:**
  - **Full fan speed** (kernel 7.2 and later).
  - The Legion Go's own fan table needs a kernel module SteamOS does not include, so curves are not offered yet.

If another fan tool is installed (or Handheld Daemon is running), Haversack only shows the readings.

## Controllers

**Device**, **Controllers** shows each controller's battery, the settings the controllers report, and the stick lights. Remap buttons, set dead zones and use the gyro in Steam's controller settings.

With the Haversack Helper installed, you can also change:
- **the controllers' own settings:** mode, button chords, rumble and its style, FPS mouse DPI, how soon each controller sleeps, the left gyro, the touchpad and its haptics;
- **the stick lights:** on or off, effect, brightness, speed and colour (select **Apply colour**).

Leave **Keep my changes** on, and Haversack applies them again when the controllers reconnect or the device wakes. This needs kernel 7.1 or later; on the Legion Go it also needs Lenovo's 2025 controller firmware. If Handheld Daemon is running, Haversack only shows the settings. If InputPlumber is installed, it keeps the button chords and touchpad haptics.

The power LED cannot be changed: every known way needs a kernel module or memory access that Haversack will not use.

### Reconnect help

**Device**, **Controllers**, **Reconnect help** is for Bluetooth controllers, often clones, that pair once and then will not reconnect when you press their normal button.

1. Pair the controller in Steam's Bluetooth settings.
2. Find it in the list and turn on help for it. Help acts only on the controllers you turn it on for.
3. Select **Help options**:
   - **Pair and commit** (on by default): the next time you pair this controller, Haversack connects to it at once, so that it saves the pairing. Forget it and pair it again after turning help on.
   - **Reconnect**: put the controller in pairing mode (on a DualShock 4, hold Share and PS until the light flashes quickly), then select Reconnect. This is also in the quick menu.
   - **Diagnose**: turn the controller off, wait 10 seconds, select **Start** and press the controller's normal button once. Haversack says what went wrong and what to try.
   - **Read stored host over USB** (DualShock 4 on a USB data cable): whether the controller will call this handheld.
   - **Export report bundle**: the last diagnosis and the Bluetooth journal lines in a zip, to share on an issue. This handheld's address is replaced.
   - **Full report mode** (DualShock 4 only): for clones that send reduced reports, such as a missing touchpad or motion.

The desktop app has the same page under Device, Controllers, Reconnect help. Install the Haversack Helper from Gaming Mode.

The list also shows a note when a controller's address is not from a registered manufacturer. That is only information: Haversack never acts on it.

If a controller connects and drops at once, Haversack suggests a diagnosis. It does nothing to the controller unless you choose.

#### The Haversack Helper: cable pairing and the SSP gate

The lasting fixes need root, so they run in a small separate plugin, the **Haversack Helper**. Select **Install helper** at the top of Reconnect help. Haversack checks the helper's signature, and Decky asks you to confirm. After each Haversack update, select **Update helper**.

- **Cable pairing** (DualShock 4 and clones using its IDs):
  1. Connect the controller with a USB data cable.
  2. Open its Help options and select **Cable pair**, then **Confirm**. Bluetooth restarts, so every Bluetooth device drops for a few seconds. It never runs during a game.
  3. Unplug the controller, turn it off, and press PS.

  If it still fails, try once more with **Reversed key order**. **Restore backup** puts back the pairing from before.
- **SSP gate:** offered when the diagnosis says the controller is refused while security starts. It lowers Bluetooth security for the whole adapter, so it asks twice. Secure Simple Pairing comes back on while you pair, when you switch the gate off, and by itself if Haversack stops.
- **Bluetooth capture:** with the helper, Diagnose also records 40 seconds of Bluetooth traffic, to tell the causes apart.

## Storage

**Device**, **Storage** shows the disk space each game uses, clears a shader cache and resets a broken prefix without losing your saves: see [Storage](storage.md).

## Looks

**Device**, **Looks** changes the videos Steam plays when the device starts and when it goes to sleep. First switch on **Looks** in **Settings**, **Modules**.

1. Put WebM videos in your **Videos** or **Downloads** folder. Animation Changer's sets are offered too.
2. For **Boot**, **Sleep** or **Sleep from the loading screen**, choose a video. It shows the next time the device starts or sleeps.
3. **Use Steam's own** goes back.

Nothing is lost:
- If a video was already there, Haversack keeps a copy first, and **Use Steam's own** puts that one back.
- Haversack never removes a video another tool put there.
- While Animation Changer is installed, Haversack only shows the videos and leaves them to it.

The page also lists the themes and sound packs that **CSS Loader** and **Audio Loader** have installed. Haversack does not change themes or sounds itself; install those plugins from Decky's store.

### Sending looks to your other handheld

With Replication on and your handhelds paired, **Send to your other handheld** at the bottom of Looks sends any of:
- your CSS Loader themes;
- your Audio Loader sound packs;
- the animations you chose above.

The other handheld keeps everything it already has. Only themes and packs it lacks are added, where CSS Loader and Audio Loader find them. Videos arrive as choices on its own Looks page, so its screen only changes when someone picks one there. The other handheld needs Looks switched on, and Haversack 0.55.0 or later.
