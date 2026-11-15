# ADR-0018: System Binary Register

- Status: proposed (slice C0, awaiting Peter's approval)
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: `docs/build-prompt-v2.md` sections 4 (P9) and 6.4

## Context

v1 principle 9 allowed no binaries at all. Some v2 features need tools that only the OS provides without root: mounting an ISO, holding a sleep inhibitor, possibly generating a certificate, detecting a firewall and running the tray. Bundling or downloading binaries stays forbidden.

## Decision

1. **Register.** Keepsake may call only these system binaries, each from `PATH` as installed by the OS:

   | Binary | Module | Use | Verified in |
   |---|---|---|---|
   | `udisksctl` | Installer | Read-only ISO loop setup and mount without root (`loop-setup -r`, `mount`, `unmount`, `loop-delete`) | slice 21 |
   | `systemd-inhibit` | Replication | Sleep inhibitor during active transfers only | slice 18 |
   | `openssl` | Replication | Candidate for certificate generation at pairing, subject to the slice 16 spike | slice 16 |
   | `firewall-cmd` | Replication | Detection only (`--state` and queries). Never changes rules | slice 17 |
   | `python3` | Desktop | Runs the tray process in the desktop session | slice 24 |

2. **Verify per distribution.** Each entry is verified present on SteamOS and on Bazzite in the slice that first uses it, recorded in `docs/assumptions.md` with versions.
3. **Missing means disabled.** A missing or failing binary disables only the dependent feature, with a clear message. Nothing falls back to a bundled or downloaded copy.
4. **Safe invocation.** Fixed argument lists, no shell, timeouts, output size caps, and arguments validated by the path validator where they are paths.
5. **Changes are escalations.** Adding a binary, or relying on one that failed verification, needs Peter's approval and an ADR.

## Consequences

- P9 is amended (ADR-0014). The no-root rule (P8) is unchanged: every entry must work as the `deck` user, which is why `udisksctl` (polkit) is preferred over `mount`.
- Diagnostics will report the presence and version of each registered binary.
