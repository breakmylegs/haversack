# Troubleshooting

Start with Haversack, Diagnostics, Health, **Run checks**. Each check says what is wrong and what to do. The Quick Access Menu badge shows the worst result.

| What you see | What it means | What to do |
|---|---|---|
| "Test store on this device" in the Quick Access Menu | Snapshots are not leaving the device | Settings, Cloud: choose OneDrive, Google Drive, WebDAV or S3 and finish its setup |
| Cloud check fails: "not signed in or set up" | No sign-in, or settings incomplete | Settings, Cloud, the backend in use: sign in or fill in the settings, then Test connection |
| "Sign-in needs attention" | The cloud stopped accepting the saved sign-in (password change, revoked access, or Google's 7-day limit for apps in testing mode) | Settings, Cloud: Sign out, then Sign in again. Waiting saves are uploaded afterwards |
| WebDAV or S3: "ignores create-only writes" | The server would overwrite files, which could lose saves | Use a server that supports `If-None-Match` (Nextcloud, ownCloud, AWS S3), see `docs/setup-backends.md` |
| A game says "Conflict: your choice needed" | Both devices have new progress, or the cloud and this device differ | Conflicts tab, Choose. Whichever save you do not choose is kept and pinned |
| "A suspicious save was kept on this device" | A save lost many files or much of its size, so it was not uploaded | History: if the game really did drop those files, Release quarantine; otherwise play on and the next good save replaces it |
| "Prefix mismatch, sync blocked" | The running game used a different Proton prefix from the one Haversack found | Check the shortcut's compatibility settings; Rescan on the Games page; the block clears when the prefixes agree |
| "Played while Haversack was not running" | Steam saw a play Haversack missed | Nothing: the idle pass saved it. Make sure Decky starts with the device |
| A game is not matched | The manifest does not know it, or the name differs | Game page: Change match, approve a suggested match, or "Give it its own game key" and add custom folders |
| Saves restored but "registry keys were left unchanged" | `user.reg` could not be read safely or the game was running | Quit the game and restore again from History; the save files are already in place |
| Update refused: "not signed" or "signature is not valid" | A release key is pinned and the release does not carry a valid signature | Do not install it; report it on the repository's Issues page |
| Update refused while syncing | Updates wait for sync jobs and open game sessions | Use "Update when idle", or quit the game |
| Settings are read-only ("safe mode") | You went back to an older version than the one that wrote the settings | Update Haversack from the Updates page |
| Updates stuck on "Checking", no installed version shown, and Games, the manifest update or shortcuts never load | Haversack's backend did not start, so the page waits for answers that never come. The usual cause is a Python module missing from this Decky build | Read Decky's journal (below). If it names a missing module, install the latest Haversack from the install link and report the module name on the repository's Issues page |
| Diagnostics, "Python modules in this Decky build" warns about `xml` | Decky's Python on this device has no XML module | Save sync is fine with OneDrive, Google Drive or the local store. WebDAV and S3 need it, so choose another cloud |

## Reading Decky's journal

When Haversack's page loads but nothing answers (Updates stays on "Checking" and no installed version is shown), its backend failed to start. Decky records why in the system journal.

1. Open a terminal: Desktop Mode's Konsole, or SSH from another computer (`ssh deck@<address>`).
2. Run `journalctl -u plugin_loader -b` to see this boot's Decky messages. Add `--no-pager | grep -i -A5 keepsake` to show only Haversack's lines, or `-f` to follow it live while you open Haversack.
3. Look for a `Traceback` near `Haversack`. The last line says what failed, for example `ModuleNotFoundError: No module named 'xml.etree'`.

Decky runs plugins with its own built-in Python, which only includes the standard modules Decky itself uses. Haversack imports anything else only inside the feature that needs it, so a missing module switches that feature off instead of stopping the backend (ADR-0030). If the journal shows a missing module anyway, that is a Haversack bug: report the line on the repository's Issues page. Installing the latest release from the install link (see the README) is the fix once it is out.

## Getting details off the device

Diagnostics, Tools, **Export diagnostics** writes one JSON file in `~/homebrew/settings/Haversack/`. It is redacted (no tokens, passwords or account names) but lists your games. Logs are in `~/homebrew/logs/Keepsake/`. Over SSH: `scp deck@<address>:homebrew/settings/Keepsake/diagnostics-*.json .`

## Starting again on one device

Settings, General, Run setup again walks through every step. Your cloud history is never deleted by setup.
