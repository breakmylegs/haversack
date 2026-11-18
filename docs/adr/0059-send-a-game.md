# ADR-0059: Sending a game between devices (slice 19a)

- Status: accepted (decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

Spec section 8.2, "Send a game", sets out the steps:
1. take a source checkpoint;
2. send an offer;
3. run a preflight and pull into staging;
4. register the game through the Steam Operations Executor;
5. promote the prefix into `compatdata/<new appid>`;
6. re-key the `gameKey` so Saves adopts silently;
7. offer the compatibility tool if the device lacks it.

Slice 18 froze the protocol (ADR-0058), but an offer needs one new message. Slice 19 is built in two parts:
- **19a (this ADR):** the backend and the calls;
- **19b:** the pages and the user guide.

## Decision

1. **The `offer` request is an additive extension of protocol version 1, not a new version.**
   - **Why the freeze allows it:** the freeze protects devices running different versions from misreading each other. A new request type does not change any existing message. A device that does not know it answers `error` with "unknown request", which the sender shows as "update Keepsake on the other device".
   - **The rule for future changes:** only new request types may be added under version 1. A change to an existing message still needs version 2 (CLAUDE.md escalation).
   - **Where it is recorded:** `docs/protocol.md` lists it under "Additions". The golden test pins that `manifest` and `chunk` are unchanged.
2. **What is sent, as up to four shares** (`replication/sendgame.py`):
   - **`install`:** the game's own folder. That is its top folder in the library root when the program is there, otherwise its start folder. It is never home itself, the library root, or Steam's own folders.
   - **`prefix`:** its `compatdata/<appid>`.
   - **`tool`:** its compatibility tool from `compatibilitytools.d`, if it has one there.
   - **`art`:** its custom grid images copied under neutral names (`capsule`, `header`, `hero`, `logo`). Icons are not sent, because Steam's artwork call does not take them.
   - **A game inside its own prefix** (as the Installer makes them) is the `prefix` share alone.
3. **Always excluded:** DXVK and VKD3D caches, crash dumps, `*.log`, `shadercache`, and the prefix's Windows and user Temp folders (spec, Exclusions). Saves are included in the first copy, so Saves finds matching hashes and adopts them silently.
4. **No device paths in the offer (P10).**
   - **Program and start folder:** each is a share and a relative path.
   - **Launch options:** this device's install folder, prefix and home become `{install}`, `{prefix}` and `{home}`.
   - **Dropped and shown to the user:** `STEAM_COMPAT_MOUNTS` (always this device's own mounts) and any other token that still looks like a local path, such as a mounted disc.
   - **On the receiving device:** the placeholders become its own folders. A test asserts that none reaches Steam.
5. **The source checkpoint.** A game Saves manages is pushed first.
   - A conflict stops the send, with "resolve it first".
   - If the push fails, for example offline, the user is warned and the copy carries this device's saves (spec step 1).
6. **The receiving device decides.** An offer is stored, and a toast and the Devices page show it. Nothing is written until the user accepts.
   - **Preflight** checks:
     - that the library root is set;
     - that the install folder does not exist yet;
     - that Steam's `compatdata` folder exists;
     - the compatibility tool: present, offered to copy (the user chooses), or missing with "install it";
     - free space with margin on each file system involved.
   - **Before creation:** every target is recorded before anything is created.
7. **The order:** copy, then register, then promote. This is the spec's order, so a failed copy leaves no shortcut.
   1. The prefix is pulled into `compatdata/.keepsake-prefix-<offer>`, and the game into `<library>/<title>`.
   2. When every copy is verified and in place, `add-shortcut` is queued with the name, program, start folder, local launch options and the wanted tool. The executor uses that tool when Steam lists it.
   3. With the new app ID, the prefix folder is renamed to `compatdata/<appid>`. An empty folder Steam made already is replaced; anything else stops with a plain reason.
   4. The program, start folder, launch options, compatibility tool and artwork are set, and each is read back.
   5. **Re-keying:** discovery runs again, and the new shortcut gets the sending device's `gameKey`. If Saves synced the game there, it is switched on here and adopts the identical saves silently.
   6. A tool Steam has not seen yet (copied while Steam ran) is reported as "restart Steam, then choose it in the game's properties".
8. **"Stop and remove" for a received game.** It does these things and nothing else:
   - stops its transfers;
   - deletes each folder the offer recorded, and only when that folder sits directly in the library, `compatdata`, `compatibilitytools.d` or Keepsake's artwork folder;
   - removes the shortcut, if the offer made one.
9. **On the sending side:**
   - offers are kept, with their manifests, until the user withdraws them, so a transfer resumes after either device restarts;
   - withdrawing deletes only Keepsake's own manifests and artwork copies, never the game;
   - at most 16 offers are kept on each side.
10. **A fix found on the way.** On Windows, a rename just after writing can fail for a moment while a scanner holds the file. Promote retries such sharing violations for up to 2 seconds, on Windows only.

## Consequences

- **No new endpoint or binary.** Steam writes stay with the executor (P15). The write allowlist (spec 6.3) covers every target: the library root, `compatdata/<appid>` for this game, `compatibilitytools.d/<tool>` after the user chose to copy it, and Keepsake's own folders.
- **T117 and A195:**
  - T117: offer abuse and removing too much;
  - A195: whether Steam accepts the copied prefix and a tool copied while it runs.
- **Device checks:** the acceptance run from the spec, in both directions, in `docs/slices/19a-report.md`.

## Addendum (19b)

A finished offer can be cleared from the list (`dismiss`). This forgets the record and keeps the game: removing a game Keepsake installed stays Steam's own Uninstall, or "Stop and remove" while the copy is still under way.
