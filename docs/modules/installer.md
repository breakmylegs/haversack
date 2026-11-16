# Module: Installer

ISO and installer assistant with exe retargeting.

| | |
|---|---|
| Flag default | On |
| Spec | `docs/build-prompt-v2.md` sections 4, 6.3, 6.4 and 8.3; research section 6.2 (Rclone SMB mounting is a spike, not a feature) |
| ADRs | 0012, 0014, 0015, 0018, 0026, 0027 |
| Code | `py_modules/keepsake/installer/`, `src/pages/InstallerPage.tsx` |
| Slices | 21 (Installer I), 22 (Installer II, minor release) |

## What it does

1. Source: a local ISO, a local folder, or a path on a network share the user has already mounted.
2. ISO: `udisksctl loop-setup -r` and mount, without root. Unmount and detach when the flow ends or fails.
3. Creates a temporary shortcut `Install: <Title>` pointing at the installer exe, with the compatibility tool Advisor recommends and `STEAM_COMPAT_MOUNTS` for the mount path, through the Steam Operations Executor.
4. Recommends installing to a registered library root and shows the exact Windows path to type, for example `Z:\home\deck\Games\<Title>`.
5. Snapshots the file lists of the prefix and the chosen root before and after, and diffs them on `game_exited`.
6. Exe retarget assistant: ranks new executables (excluding uninstallers, redistributables, crash handlers and setup stubs) by location, size and title similarity. The user confirms.
7. Retargets the same shortcut (name, exe, start dir), removes the installer-only launch options and keeps the prefix.
8. Offers to enable Saves and Replication for the new game.

Should: CD drive emulation (`dosdevices/d:` link plus the drive type set to CD-ROM through the slice 11 registry engine), and SteamGridDB artwork with the user's own key.

Spike, escalate before building: automated SMB and NFS mounting (likely needs root or a binary).

## What it writes (spec section 6.3)

User-registered library roots; `compatdata/<appid>` for the game being installed; `<pfx>/dosdevices/<letter>:` links for that game; `grid` artwork as a fallback; staging. Steam changes only through the executor (ADR-0015). Never Saves-managed paths.

## Network

`www.steamgriddb.com` only with a user-supplied SteamGridDB key.

## Accepted risk

A Wine prefix is not a sandbox. Running an installer runs untrusted Windows code as the user (T51). Documented in the README.

## Health checks

`udisksctl` present, loop devices left attached, installer shortcuts left behind, pending Steam operations.
