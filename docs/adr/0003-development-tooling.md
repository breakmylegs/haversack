# ADR-0003: Development tooling on Windows and secret scanning

- Status: accepted
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

- The owner develops on Windows. WSL does not start on the laptop (policy) and Docker is not installed.
- The template's build and deploy tasks need bash, rsync and Docker (for the Decky CLI).
- The build prompt asks for a pre-commit secret scan (threat model T11). The owner's standing rule bans gitleaks in every project.

## Decision

1. **Tests.** Backend tests run locally on Windows Python. Tests that need a real Linux `/proc`, POSIX signals, symlinks or file modes are marked and skipped on Windows. GitHub Actions on Ubuntu runs everything on Python 3.11 and 3.14 and is the authoritative Linux run. `/proc` reading takes a `proc_root` argument and signal sending is injectable, so most process logic is tested on every platform with a synthetic `/proc` tree.
2. **Packaging and deploy.** `scripts/package.py` builds a deterministic zip in the template's documented layout with Unix modes set explicitly. `scripts/deploy.py` uses the OpenSSH client built into Windows. VS Code tasks call these.
3. **Secret scanning.** `scripts/secret_scan.py`, a plain stdlib script the owner can read, runs from `.githooks/pre-commit` and in CI. A git-ignored `.secret-scan-denylist` holds personal strings. No third-party scanner.
4. **Commit identity.** The repository's local git config uses the owner's GitHub noreply address so no personal email reaches the public history.
5. **Supply chain.** GitHub Actions are pinned to commit SHAs.

## Consequences

- Linux-only behaviour is verified in CI, not before push. A failing CI run is the signal.
- The Decky CLI is not used. Slice 2 must prove that "Install plugin from URL" accepts our zip.
