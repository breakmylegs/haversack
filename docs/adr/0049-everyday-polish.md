# ADR-0049: Everyday polish (R2): newer saves, playtime, mains power, What's new

- Status: accepted (slice R2 of ADR-0047; decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0047 accepted these items for R2:
- show a newer save from another device before play (item 2);
- combined playtime for non-Steam games across devices (item 12), with its own decision on the cloud layout;
- sensible behaviour on devices with no battery (item 18);
- accessibility basics (item 27);
- What's new after an update, and first-run tips (item 28).

## Decision

1. **Newer save from another device.**
   - **Where it is noticed:** the idle pass already prefetches cloud heads. When there is exactly one head, it moved on from this device's base, and another device made it, the game's sync state records it.
   - **Where it shows:** "Newer save from <device>, <when>" on the game's row, in the Quick Access Menu and on the desktop Overview.
   - **What is excluded:** a fork is a conflict, not a newer save, and a device's own saves never count.
   - **"Get it now" (`bring_newer`):** runs the same decision table as a launch. It restores only when nothing changed here since the base, reports a conflict otherwise, and never restores under a running game (P6). It opens no play session.
   - **At launch:** the save is still brought in automatically, as before.
2. **Combined playtime, as a layout addition.**
   - **Where it is stored:** each finished session becomes a write-once object, `games/<gameKey>/sessions/<deviceId>/<seq>-<seconds>.json`.
   - **What it holds:** start, end, seconds and device ID. No paths, names or titles (P10).
   - **Why the length is in the key:** totals come from one listing, with no download per session.
   - **What counts:** only sessions from 1 minute to 24 hours. A missed exit never adds a day of play.
   - **Offline:** sessions wait in a local queue and go up on the next idle pass.
   - **Never deleted:** retention does not touch these objects, and Keepsake never deletes them (P2).
   - **Informational only:** playtime never decides which save wins (P4).
   - **Why this addition is allowed:** a new prefix that older versions never read is the smallest change to the frozen layout. It stays inside the game's folder, which the user already controls.
3. **Mains-powered devices.**
   - **The check:** `keepsake.power.battery_present`.
     - **Linux:** a `power_supply` entry of type `Battery` whose scope is not `Device`. A controller's battery does not count.
     - **Windows:** `GetSystemPowerStatus`, where `BatteryFlag` 128 means no system battery.
     - **Unknown is None,** and callers treat None as "may have a battery" (fail closed).
   - **Advisor on such a device:** it leaves out battery estimates. With no device profile, it suggests no TDP, because the power limits of a desktop or Steam Machine are unknown.
   - **Replication's battery rule** (ADR-0045) uses the same check when it is built.
4. **Accessibility.**
   - **Status words:** every status keeps a text label next to its icon. This was already true in Gaming Mode, and Activity adds "Needs attention" in words.
   - **Desktop text size:** desktop font sizes are in `rem`, so the browser's own text size setting applies.
   - **Gaming Mode:** it uses Steam's own scaling and controller hints.
5. **What's new and tips.**
   - **Shipped with the release:** both packages now include `CHANGELOG.md`.
   - **After an update:** the startup notice carries that version's section, at most 4,000 characters. Gaming Mode shows it once in a "What's new" modal, as plain text, never as HTML.
   - **First-run tip:** a short tip in the Quick Access Menu (checkpoints, restoring single files) stays until "Got it" (`tipsDismissed`).

## Consequences

- **The layout grows by one write-once prefix.** Older devices ignore it.
- **Playtime starts counting from this version.** Earlier sessions are not known.
- **Not built:** a full i18n framework stays deferred (ADR-0047).
