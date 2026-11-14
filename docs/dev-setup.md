# Development setup

## Tools

- Node.js 22 or later.
- pnpm 9. Either `npm i -g pnpm@9` or prefix commands with `npx -y pnpm@9.15.9`.
- Python 3.11 or later for tests and scripts. Decky Loader 3.3.1 runs plugins on Python 3.14.
- Git, and the OpenSSH client (built into Windows 10 and later).

```
pnpm install --frozen-lockfile
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt      # Windows
.venv/bin/python -m pip install -r requirements-dev.txt          # Linux
git config core.hooksPath .githooks
```

## Everyday commands

```
pnpm run lint
pnpm run typecheck
pnpm run build                 # dist/index.js
python scripts/package.py      # out/Keepsake-v<version>.zip and its SHA-256
python scripts/check_versions.py
python scripts/secret_scan.py
python -m pytest -q tests/test_freeze.py      # run the tests for what you changed
ruff check . && ruff format --check . && mypy
```

## Linux tests on a Windows laptop

WSL does not start on the owner's laptop and Docker is not installed (ADR-0003). Tests that need a real Linux `/proc`, signals, symlinks or file modes are skipped on Windows and run in CI on Ubuntu for every pull request. Most process logic is still tested on Windows through a synthetic `/proc` tree (`tests/helpers.write_fake_proc`).

If WSL becomes available: open the repository in Ubuntu, create a Linux venv and run `python -m pytest -q` there.

## Enable SSH on the device

### SteamOS

1. Switch to Desktop Mode once for setup only (development needs SSH; the plugin itself never needs Desktop Mode).
2. Open Konsole and set a password for `deck` if you have not: `passwd`.
3. Enable and start SSH: `sudo systemctl enable --now sshd`.
4. Find the address: `ip -4 addr` or Settings, Internet, the connected network.
5. From the PC, copy your key: `ssh-copy-id deck@<address>` (or append your public key to `~/.ssh/authorized_keys` on the device).

### Bazzite

SSH is available but off by default.

1. Run `ujust toggle-ssh` (or `sudo systemctl enable --now sshd`).
2. The user is the one created during setup, not necessarily `deck`. Home may be `/var/home/<user>`, which is a symlink target of `/home/<user>`.

## Deploy a development build

Create `deploy.local.json` in the repository root (git-ignored):

```json
{"host": "192.168.1.50", "user": "deck", "port": 22}
```

Then:

```
pnpm run build
pnpm run deploy:device
```

This builds the zip, copies it to the device home folder, replaces `~/homebrew/plugins/Keepsake`, and restarts Decky Loader. The plugins folder is owned by root on a standard Decky install, so the script runs `sudo` on the device and prompts for the device password in your terminal. The plugin itself has no root flag.

Alternative without SSH: copy the zip to the device and use Decky, Settings, Developer, "Install Plugin from ZIP File".

## Where things live on the device

| What | Path |
|---|---|
| Plugin | `~/homebrew/plugins/Keepsake` |
| Settings and diagnostics exports | `~/homebrew/settings/Keepsake` |
| Runtime state | `~/homebrew/data/Keepsake` |
| Logs (`keepsake.jsonl`, Decky's `plugin.log`) | `~/homebrew/logs/Keepsake` |

Copy a diagnostics export off the device with:

```
scp deck@<address>:homebrew/settings/Keepsake/diagnostics-*.json .
```
