# Troubleshooting

Start with Haversack, **Diagnostics**, **Device checks**, **Run all**. Each check says what is wrong and what to do.

| What you see | What it means | What to do |
|---|---|---|
| Find devices lists nothing | The other handheld is not letting devices reach it, or your network blocks the search | On the other handheld, Games and devices, Other devices: switch on Let other devices reach this one. Or type its address under Pair by address |
| "doesn't have enough space" when sending | The other handheld has too little free space for the game | Free some space there, or send the game to a different drive |
| A transfer says the link looks slow | A VPN may be relaying the connection | Use your home network, or check your VPN's direct connection settings |
| Install cannot open an ISO on a share | The share does not let the system mount the ISO there | Nothing: Haversack copies it to the device first and installs from the copy |
| Find shares lists nothing | Your network blocks the search (some mesh and guest Wi-Fi do) | Type the address, for example `smb://nas.local/Games/` |
| Update refused: "not signed" or "signature is not valid" | A release key is pinned and the release does not carry a valid signature | Do not install it; report it on the repository's Issues page |
| Update refused while busy | Updates wait for installs, transfers and open game sessions | Wait for them to finish, or quit the game |
| Settings are read-only ("safe mode") | You went back to an older version than the one that wrote the settings | Update Haversack from the Updates page |
| Updates stuck on "Checking", no installed version shown, and Games or shortcuts never load | Haversack's backend did not start, so the page waits for answers that never come. The usual cause is a Python module missing from this Decky build | Read Decky's journal (below). If it names a missing module, install the latest Haversack from the install link and report the module name on the repository's Issues page |
| My saves from before 0.61.0 are missing | Version 0.61.0 removed save sync; nothing was deleted | Install version 0.60.0 from Settings, Updates ([Updates](user/updates.md#going-back-to-a-version-with-save-sync)) |

## Reading Decky's journal

When Haversack's page loads but nothing answers (Updates stays on "Checking" and no installed version is shown), its backend failed to start. Decky records why in the system journal.

1. Open a terminal: Desktop Mode's Konsole, or SSH from another computer (`ssh deck@<address>`).
2. Run `journalctl -u plugin_loader -b` to see this boot's Decky messages. Add `--no-pager | grep -i -A5 keepsake` to show only Haversack's lines, or `-f` to follow it live while you open Haversack.
3. Look for a `Traceback` near `Haversack`. The last line says what failed, for example `ModuleNotFoundError: No module named 'xml.etree'`.

Decky runs plugins with its own built-in Python, which only includes the standard modules Decky itself uses. Haversack imports anything else only inside the feature that needs it, so a missing module switches that feature off instead of stopping the backend (ADR-0030). If the journal shows a missing module anyway, that is a Haversack bug: report the line on the repository's Issues page. Installing the latest release from the install link (see the README) is the fix once it is out.

## Getting details off the device

Diagnostics, Tools, **Export diagnostics** writes one JSON file in `~/homebrew/settings/Haversack/`. It is redacted (no keys, passwords or account names) but lists your games. Logs are in `~/homebrew/logs/Haversack/`. Over SSH: `scp deck@<address>:homebrew/settings/Haversack/diagnostics-*.json .`
