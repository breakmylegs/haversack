# ADR-0015: Steam write policy and the Steam Operations Executor

- Status: proposed (slice C0, awaiting Peter's approval)
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 4 (P15), 7.2 and 8.2 to 8.3; research sections 2.1 and 4.2

## Context

Replication and Installer must create non-Steam shortcuts and set their name, exe, start dir, launch options, compatibility tool and artwork. v1 forbids editing Steam settings except the opt-in launch wrapper (ADR-0010). The research found that `shortcuts.vdf` edits only take effect after a Steam restart and that Steam has read the file from different `userdata` folders in Desktop and Gaming Mode. The Steam client's own APIs apply changes immediately but only run in the Steam UI context, which only the plugin frontend reaches.

## Decision

1. **Only through `SteamClient`.** Shortcut, launch option, compatibility tool and artwork changes go through `SteamClient` APIs called from the frontend. Never write `shortcuts.vdf`, `config.vdf` or `localconfig.vdf` directly. Reading `shortcuts.vdf` for discovery stays allowed (slice 3).
2. **Only after an explicit user action.** No Steam write happens in the background or because of a peer message alone. The user's action creates the operation; the operation then runs when Gaming Mode is active.
3. **Store, write, read back.** Before changing an existing shortcut, the original values are stored in Core state. After every write, each field is read back and compared. A mismatch retries with a short delay (the research reports that `Set*` calls within about 500 ms of `AddShortcut` silently fail) and, if it still fails, marks the operation failed and offers to restore the stored originals.
4. **Steam Operations Executor.** A `steam_ops` queue in the backend holds operations (create shortcut, set fields, set compatibility tool, set artwork, remove installer shortcut). The frontend claims operations, runs them through `SteamClient`, reads back and reports the result. Operations created while Gaming Mode is not active (for example from Desktop Mode) wait and every UI shows them as pending. Runtime probes check that each API exists before use and disable the dependent feature if one is missing.
5. **No pre-quoted exe paths** (research section 2.1: they get double quoted).
6. **The v1 launch wrapper** (ADR-0010) is unchanged and remains the only change Saves makes to launch options.

## Consequences

- API names and signatures in `@decky/ui` 4.16.5 are verified for `AddShortcut`, `SetShortcutName`, `SetShortcutExe`, `SetShortcutStartDir`, `SetAppLaunchOptions`, `SpecifyCompatTool`, `SetCustomArtworkForApp`, `RemoveShortcut` and `SetShortcutIcon`. Their runtime behaviour (delays, ignored arguments, read-back fields) is unverified and listed in `docs/assumptions.md` (A70 onwards) for slice 13 probes.
- Artwork files under `userdata/<id>/config/grid` are a fallback only, API first (spec section 6.3).
- A consented VDF fallback executor and a CEF DevTools executor stay in the backlog. Either would need a new ADR and Peter's approval.
