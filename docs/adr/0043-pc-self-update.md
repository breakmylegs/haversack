# ADR-0043: PC self-update

- Status: accepted (decided under ADR-0037; P5 of ADR-0038, second part)
- Date: 17 November 2026
- Deciders: Peter (owner)

## Context

On a Decky device, updates go to Decky's own installer (ADR-0002). A PC has no Decky. ADR-0038 requires PCs to update from signed GitHub release assets, with the same checks as the plugin. ADR-0042 installs each version in its own folder and keeps the previous one, ready for this.

## Decision

1. **The same proof as the plugin.**
   - `Updater.prepare_desktop(tag)` reads the same cached release list as the plugin updater.
   - It downloads `SHA256SUMS` and requires a valid minisign signature from the pinned key, using the same `_check_signature` (ADR-0036).
   - It returns the line for `Keepsake-desktop-v<version>.zip`.
   - A release that is unsigned, badly signed, has no PC package, or whose checksums leave out the package is refused.
   - The plugin's `prepare()` is unchanged, since devices depend on it.
2. **A checked download.** `keepsake.pcupdate.apply`:
   - downloads the zip through `net.fetch_to_file` (GitHub hosts on the allowlist, redirects checked), capped at 64 MiB, into a temporary folder;
   - checks it against the signed SHA-256 before opening it.
3. **A safe unpack.**
   - **Checked first:** every member must sit under `Keepsake-desktop/`, with no `..` or `.` part, backslash, colon, leading slash or NUL. At most 5,000 members and 256 MiB unpacked.
   - **All or nothing:** one bad member refuses the whole package before anything is written.
   - **Plain files only:** members are written as plain files by Keepsake itself, so a symlink entry cannot point outside the folder.
   - **Version check:** the unpacked `VERSION` must equal the version the signed release names.
4. **Install beside the running version.**
   - `pcinstall.install(..., entries=False)` copies the package into a new version folder and switches `current.json`, keeping the running version as `previous`.
   - The start-up and menu entries stay as the user set them, so an update never turns autostart back on.
   - The running host keeps running the old files until it restarts.
5. **Host-only calls.**
   - **The calls:** `pc_update_status`, `pc_update_apply`, `pc_rollback` and `pc_restart` exist only on the PC host (`HOST_CALLABLES`). They sit apart from the plugin's `CALLABLES`, which a test keeps equal to `main.py`.
   - **Protection:** they carry the same token, `Host` and `Origin` checks as every other call.
   - **Not installed:** they refuse when Keepsake was not installed by the installer (running from source).
   - **Restart:** `pc_restart` refuses while a sync job or game session is busy. Otherwise it starts the installed launcher with `--restart` and stops the host. The launcher waits up to 30 seconds for the old host to stop answering, then starts the version in `current.json` and opens it in the browser, because the old page's token went with the old host.
6. **Rollback.** "Go back to <previous>" switches `current.json` back if the previous folder is still on disk. A restart then runs it.
7. **The user decides.** Nothing checks, downloads or installs on its own. Each step is a button on the desktop interface's Updates page.

## Consequences

- PCs update in three clicks: Check, Install, Restart. They can go back in one more.
- No new endpoint, binary or permission is added. The download hosts are the GitHub release hosts already allowed for plugin updates.
- Settings, state and saves are never touched, as in ADR-0042.
- A PC run is still needed to update a real install from one release to the next. That check is in the P5 device checklist.

## Sources

- ADR-0002, ADR-0036, ADR-0038 and ADR-0042.
- Python `zipfile` documentation: it warns that member names can be absolute or hold `..`, and that `extractall` should not be trusted with untrusted archives. That is why members are checked and written one at a time.
