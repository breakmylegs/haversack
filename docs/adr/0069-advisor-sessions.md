# ADR-0069: The Advisor remembers how each game ran on this device

- Status: accepted (Peter's request of 21 November 2026, decided under ADR-0037)
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

Advisor advice comes from community reports and device profiles. Peter wants it to also use real measurements from this device, recorded with no setup in the background while a game runs:
- frame rate, power, battery drain, load, clocks, temperatures, throttling, and the settings in force;
- shown as a Last session card and a Recent sessions trend for any game, running or not;
- used in the recommendations, weighted above community data.

P16 (the Advisor is read-only) rules out changing launch options or injecting anything into the game.

## Where the frame rate can come from without changing the game

| Source | Read-only? | Verdict |
|---|---|---|
| Steam's own performance overlay: `SteamClient.System.Perf.RegisterForDiagnosticInfoChanges` (in the `@decky/ui` 4.16.5 types) | Yes: Steam pushes diagnostic entries (name and value pairs, raw protobuf) to the frontend | **Used.** The frontend forwards them at most once a second while a game runs. The backend decodes the protobuf without a schema and takes the entries named like "FPS" or "frame time". Whether Steam sends them while the overlay is hidden is A211. |
| MangoHud's own CSV logs, when the user already logs with MangoHud | Yes: files MangoHud writes; Keepsake only reads those written during the session, in `output_folder` from MangoHud's config or its default folders | **Used** when present. They give real frame times, so the 1% and 0.1% lows. |
| gamescope's frame timing for mangoapp (a System V message queue) | No: reading the queue takes messages away from mangoapp, Steam's own overlay | Rejected. |
| amdgpu `gpu_metrics`, DRM counters | Yes, but no per-game frame count | Not a frame-rate source. |
| Turning on MangoHud logging or a wrapper in launch options | No: it changes the game's launch | **Not built.** It would be an Advisor write (P16, an escalation item). It is reconsidered only if the device run shows neither read-only source works (the Device check below says so); then it would be an off-by-default, clearly labelled switch in its own ADR. |

## Decision

1. **Recording** (`advisor/sessions.py`). The Advisor module starts a recorder on the lifecycle bus's `game_started` and finishes it on `game_exited`. A background thread samples once a second, read only.
   - **Files:** `Sensors` finds the files once per session, then each reading opens only those:
     - the amdgpu `hwmon` (socket power, edge temperature, GPU clock);
     - `gpu_metrics` version 2 (CPU and GPU power, throttle status), for Van Gogh, Rembrandt and Phoenix, including the Z1 Extreme. The Z2 Extreme's version 3 layout differs and is left to `hwmon` (A212);
     - `k10temp`, `/proc/stat` (CPU use), `gpu_busy_percent`, `scaling_cur_freq` on four cores, `/proc/meminfo` and `mem_info_vram_used`;
     - the battery's `power_now` (or current times voltage), `capacity` and `energy_now`, and whether mains power is connected. A controller's battery (`scope=Device`) is ignored.
   - **Paused** between `on_suspend` and the new `on_resume` (Steam's resume event, from the frontend).
2. **Summary only.** No sample is kept. Each session stores:
   - start, end and length;
   - the device and its display (the device profile's resolution and refresh rate);
   - plugged in, on battery, or mixed;
   - frame rate: average and 1% and 0.1% lows from frame times, else the average and the lowest 5-second average, else "frame rate not available";
   - APU, CPU and GPU watts (average and peak);
   - battery drain in watts and % per hour, and battery life at that rate;
   - CPU and GPU use, clocks and temperatures;
   - throttling and after how many minutes (throttle status, or 95 °C);
   - RAM and VRAM peaks;
   - the settings in force: TDP from the user's TDP tool (`advisor/current.py`), Proton version, launch options, and frame generation.

   The frame cap is not readable yet (A213). Sessions shorter than a minute are not kept. The last 20 per game and a running summary go in `<runtime>/advisor-cache/sessions/<appid>.json`, never the cloud.
3. **Advice measured here** (`sessions.advice`). Each item says "Measured on this device, N sessions", and the page shows them above community reports:
   - 1% lows well under the frame cap: lower the cap or raise the TDP;
   - GPU over 95 % with CPU at or under 50 %: GPU-bound, so lower the resolution or use FSR;
   - the same frame rate (within 5 %) at a lower TDP across sessions: save the battery;
   - throttled after N minutes.
4. **The page.** On the Advisor page for any game:
   - a **Last session** card: frame rate, watts, battery life, temperatures, settings, load, power split, memory;
   - **Recent sessions**: the last five;
   - the measured advice.
5. **AI.** The optional explanation gets the last five sessions as plain numbers: minutes, power state, frame rate and lows, watts, CPU and GPU use, peak temperature, throttle minutes, TDP and frame cap. There are no paths, names, launch options or Proton names (P18).
6. **Cost.** A reading is a few dozen small file reads. The perf gate has two new budgets:
   - "100 session readings": about 3.4 ms a reading on the laptop, far less on sysfs;
   - "an hour of session samples summarised".
7. **Device check "Session stats sources":**
   - which readings this handheld gives: frame rate, APU, CPU and GPU power, battery, temperatures, GPU load;
   - whether MangoHud is configured.

   It passes with a frame rate, warns without one (and says to play a minute first), and fails with neither power nor battery readings.

## Consequences

- Sessions record from the first game after updating. Nothing is asked of the user.
- Without a frame rate source the cards say "frame rate not available" and the frame-rate advice does not appear; power, heat and battery still do.
- T128 in `docs/threat-model.md`; A211 to A213 in `docs/assumptions.md`.
