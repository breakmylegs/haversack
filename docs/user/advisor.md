# Advisor

Advisor recommends settings for the game you are playing or have selected, tuned to your device. **It never changes anything.** It shows advice, says where each piece came from and how sure it is, and lets you copy launch options.

It is on by default on a handheld. On a PC it starts switched off, because its advice is built for handhelds. Turn it on under **Modules**.

![The Modules page on a PC](images/desktop-modules.png)

## What it recommends

- **Power:** the TDP to set, in the terms of the tool you use.
- **Display:** the refresh rate and frame cap, with VRR where your screen has it.
- **Scaling:** the game's own upscaler first, then the gamescope filter. Frame generation (lsfg-vk) only when the base frame rate is high enough.
- **The game's own preset**, plus the Proton version and launch options.

On a machine without a battery, such as a Steam Machine or a desktop, Advisor leaves out battery estimates. If it has no profile for the machine, it suggests no TDP, because the machine's power limits are unknown.

Advisor recognises your device from its hardware (for example the Legion Go and Legion Go 2) and the tools you have installed, such as TDP tools, lsfg-vk and OptiScaler. It only reads them.

## How your games ran on this device

While you play, Advisor quietly measures how the game runs on this device: frame rate, power use, battery drain, CPU and GPU load, clocks, temperatures and whether it throttled, along with the TDP and Proton version you used. There is nothing to set up, and it only reads what the system already reports; it never changes the game. After you quit, the game's Advisor page shows a **Last session** card and your **Recent sessions**, even when the game is not running.

These measurements feed the advice, marked "Measured on this device", and they count for more than community reports. For example: the frame rate dropped well under your frame cap, so lower the cap or raise the TDP; the GPU was flat out while the CPU idled, so lower the resolution or use FSR; you got the same frame rate at a lower TDP, so save the battery; or it throttled after 20 minutes.

The frame rate comes from Steam's own performance overlay, or from MangoHud's logs if you already log with MangoHud. If neither is available, the card says "frame rate not available" and everything else is still measured. Only a summary of each session is kept, the last 20 per game, on this device only. If you ask for an AI explanation, only plain numbers from them are sent, never names, paths or launch options.

## Where its advice comes from

Each source can be switched off, and each is contacted only while it is on:

- **Deck Verified** community reports, from deckverified.games.
- **PCGamingWiki**, using your own PCGamingWiki bot password.
- **ProtonDB** reports, from Keepsake's own monthly index. Games are looked up on your device, so no game is named to anyone.
- **Are We Anti-Cheat Yet**, to warn about games whose anti-cheat blocks Proton.

## Optional AI explanations

If you add your own Anthropic, OpenAI or Google Gemini API key and turn that provider on, Advisor can explain its advice in plain words. A request carries only:
- the game's title;
- your device's hardware profile;
- your tool versions;
- the settings being discussed.

Nothing else is sent, and nothing is sent until you press the button. Without a key, Advisor gives the same advice from its own rules.
