# ADR-0005: Repository protection without CI

- Status: accepted (the owner delegated the decision on 14 November 2026)
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

The build prompt asks for `main` to be protected with "pull requests only and CI must pass", and recommends protecting release tags. ADR-0004 removed CI, so "CI must pass" cannot apply. Branch protection is an escalation item; the owner asked Claude Code to make the best decision.

## Decision

- **GitHub Actions disabled** in the repository settings, so no workflow can run or use credit even if one is added by mistake.
- **`main`:** pull request required, zero approvals (single developer), applies to admins, no force pushes, no deletion. No required status checks.
- **Release tags:** a ruleset on `refs/tags/v*` blocks deletion and any update or force move. Tags can be created but never changed, so a published release cannot be silently repointed (threat model T10).

## Consequences

- Nobody, including the owner, pushes straight to `main`. Version bumps for releases go through a pull request (`scripts/release.py prepare`), and the release tag is created after merge (`scripts/release.py publish`).
- A mistaken tag cannot be deleted without first removing the ruleset in the repository settings. That is deliberate.
- The owner should enable two-factor authentication on the GitHub account if it is not already on.
