# ADR-0003: Development tooling on Windows and secret scanning

- Status: accepted, points 1, 3 and 5 amended by [ADR-0004](0004-no-github-actions.md) (no GitHub Actions)
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

- The owner develops on Windows. WSL does not start on the laptop (policy) and Docker is not installed.
- The template's build and deploy tasks need bash, rsync and Docker (for the Decky CLI).
- The build prompt asks for a pre-commit secret scan (threat model T11). The owner's standing rule bans gitleaks in every project.

## Decision

1. **Tests.** Backend tests run locally on Windows Python. Tests that need a real Linux `/proc`, POSIX signals, symlinks or file modes are marked `posix` and skipped on Windows; they run on a device over SSH (ADR-0004). `/proc` reading takes a `proc_root` argument and signal sending is injectable, so most process logic is tested on every platform with a synthetic `/proc` tree.
2. **Packaging and deploy.** `scripts/package.py` builds a deterministic zip in the template's documented layout with Unix modes set explicitly. `scripts/deploy.py` uses the OpenSSH client built into Windows. VS Code tasks call these.
3. **Secret scanning.** `scripts/secret_scan.py`, a plain stdlib script the owner can read, runs from `.githooks/pre-commit` and in `pnpm run check`. A git-ignored `.secret-scan-denylist` holds personal strings. No third-party scanner.
4. **Commit identity.** The repository's local git config uses the owner's GitHub noreply address so no personal email reaches the public history.
5. **Supply chain.** Superseded: there are no GitHub Actions (ADR-0004).

## Consequences

- Linux-only behaviour is verified on a device, not on the laptop.
- The Decky CLI is not used. Slice 2 must prove that "Install plugin from URL" accepts our zip.
