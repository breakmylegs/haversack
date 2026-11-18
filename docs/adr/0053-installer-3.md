# ADR-0053: Installer III: disc sets, the install queue and runtime hints (R6)

- Status: accepted (slice R6 of ADR-0047; decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

ADR-0047 accepted three Installer items for R6:
- multi-disc installs (item 22);
- an install queue that resumes after a reboot (item 24);
- a post-install runtime check that guides the user without bundling anything (item 25).

ADR-0027 already makes a mounted ISO a CD drive in the installer shortcut's prefix. That is a `dosdevices` link set while the installer is closed, with the drive type set in the registry.

## Decision

1. **Disc sets.**
   - **Which discs are offered:** for an ISO install, the other `.iso` files in the same folder (in name order, at most ten). The choice is checked against that list, so no other path can be named.
   - **"Swap to <disc>":**
     1. mount the chosen ISO read-only;
     2. repoint each of Keepsake's own drive links at it, as a new link renamed over the old one;
     3. release the previous disc.
   - **Allowed while the installer runs:** this is the one prefix change Keepsake makes while an installer runs, because a disc change is exactly what the installer is waiting for. The registry, other links and every other file stay untouched.
   - **Safety:** every link is checked before any changes, so a drive changed outside Keepsake stops the swap. The newly mounted disc is released if the swap fails.
   - **Visibility:** the folder discs are mounted under (for example `/run/media/deck`) is the one passed to the Steam runtime container in `STEAM_COMPAT_MOUNTS`, so a disc swapped in later is visible too. A colon in a disc's own name no longer matters; a colon in the library folder is still refused.
2. **The install queue.**
   - **Joining:** a new install while another is active joins the queue (state `queued`; nothing is mounted yet). Cancelling a queued install just drops it.
   - **Starting:** when an install ends (done, failed or cancelled), the oldest queued one starts by itself. One that cannot start (its folder gone, its ISO unreadable) fails with the reason, and the next is tried.
   - **Restarts:** the queue is in the Installer's state database, so it survives a restart.
   - **Resume after a restart:** the discs of active installs are mounted again, then the queue continues.
   - **A disc that moves:** if a disc comes back at a different mount point after its installer shortcut was made, the shortcut would point at a folder that no longer exists. That install fails with a plain reason rather than guessing.
3. **Runtime hints.**
   - **What is looked for:** when the installer closes, Keepsake lists the runtime installers the game ships, in the install folder and on the disc: Visual C++, DirectX, .NET Framework, PhysX, XNA and OpenAL, by their usual file names, at most 20.
   - **What the page says:** Proton already provides most of these, so it suggests running one only if the game will not start, through the same shortcut.
   - **Nothing is run, bundled or downloaded** (P9).

## Consequences

- No new endpoint, binary or permission. `udisksctl` (System Binary Register) is used as before.
- **Device checks:** a two-disc install, and a restart in the middle of one, need the device run (A187).
