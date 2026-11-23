# ADR-0097: Launch option presets, and the rest of launchers and stores

- Status: accepted (R29 stage 5; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

R29's research recommends three things for launchers and stores:
- a launch options editor with presets;
- GE-Proton install;
- coexistence checks for store launchers' shortcuts (Junk-Store, Unifideck, NonSteamLaunchers).

It skips Epic and GOG libraries, which need binaries, sign-in endpoints and in places GPL code.

Principle 15 governs launch options: only through `SteamClient`, after a user action, originals stored first, every field read back. Principle 9 forbids downloading or installing a binary.

## Decision

1. **Launch option presets on each game's page** (Saves, Games), for Steam and non-Steam games. Five switches, each a documented Proton runtime variable set to 1 in front of `%command%` (ValveSoftware/Proton README, "Runtime Config Options", read 23 November 2026):
   - `PROTON_LOG`;
   - `PROTON_USE_WINED3D`;
   - `PROTON_NO_FSYNC`;
   - `PROTON_NO_ESYNC` (obsolete from Proton 11, and labelled so);
   - `PROTON_OLD_GL_STRING`.

   Some were left out: `PROTON_FORCE_LARGE_ADDRESS_AWARE` is already on by default, and the Nvidia-only variables do not apply to these handhelds. No preset adds a program, so the System Binary Register is unaffected (P9).
2. **Everything else is kept exactly:** other variables, wrappers such as `gamemoderun`, and the game's own arguments after `%command%`. A line of arguments only gains `%command%` in front when a preset is switched on, and stays as it was otherwise. A line Haversack cannot read (an unmatched quote) is left alone.
3. **P15, as the strict launch gate already does it.**
   - The page reads Steam's current options (`AppDetails.strLaunchOptions`, loading the details with `RegisterForAppDetails` when needed), and the backend works out the new line.
   - The page sets it with `SteamClient.Apps.SetAppLaunchOptions` and reads it back, and says so when Steam did not keep it.
   - The first time a game is changed, the options as they were are kept (`launch-presets.json`), and **Put back original** restores them exactly.
   - Nothing changes without a press.
   - While a game uses the strict launch gate, which manages its options, the presets are refused, so the two never fight.
4. **GE-Proton install is not added.** Installing GE-Proton means downloading and unpacking a compatibility tool, which is a binary, and P9 says never to download or install one. That is a non-negotiable principle, so it is kept, not loosened. Haversack already copies a compatibility tool from the user's own other device when sending a game (ADR-0072), which is the user's own copy.
5. **Coexistence with store launchers:** their shortcuts are ordinary non-Steam shortcuts with their own prefixes, which Saves and Replication already handle. A shortcut whose program is another launcher's wrapper is copied like any other; that it needs the launcher on the other device is listed in the guide's questions and answers. No code change is needed.

## Consequences

- R29's five stages are complete. Its remaining "later" items stay in `docs/research/decky-plugins.md`:
  - a profile on AC or dock;
  - colour saturation after a probe;
  - a screenshot backup;
  - syncing TabMaster and SteamGridDB settings, once their files are verified.
- **Threat model:** T168.
- **Device run:** step 58.
