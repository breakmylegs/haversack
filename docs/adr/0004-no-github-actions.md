# ADR-0004: No GitHub Actions; local checks, device tests and local releases

- Status: accepted
- Date: 14 November 2026
- Deciders: Peter (owner)

## Context

The build prompt assumes GitHub Actions: CI on every pull request (sections 6, 13, 16, 17), CI-built releases (section 1 outcome, section 13) and "CI must pass" branch protection. The owner does not have the Actions credit or account type for this, and has decided not to use GitHub CI. WSL is also unavailable on the development laptop (ADR-0003), so there is no Linux machine besides the handhelds.

This changes the build prompt's outcome "CI builds every release" and the T10 mitigation "CI-only releases".

## Decision

1. **No workflows.** The repository has no `.github/workflows`. Do not add any.
2. **Local quality gate.** `pnpm run check` (`scripts/check.py`) runs ESLint, tsc, the Rollup build, version consistency, packaging, ruff, mypy and the secret scan. Run it before opening every pull request and record the result in the pull request and slice report.
3. **Tests.** Run the tests for what changed, named one by one, on Windows. Tests needing Linux behaviour are marked `posix` and run on a device with `pnpm run test:device` (`scripts/test_on_device.py`), which streams the code to a temporary folder under `~/.cache`, runs pytest in a reusable venv with the device's `python3`, and deletes the run folder. Run them at the end of every slice and before every release.
4. **Releases (slice 2).** `pnpm release <version>` runs locally: it runs the quality gate and the release tests, builds the deterministic zip, writes `SHA256SUMS`, signs it with minisign when the owner's key is present locally, tags, pushes and creates the GitHub Release with `gh`. The zip is deterministic, so anyone can rebuild a tag and compare the hash.
5. **Branch protection.** "CI must pass" cannot apply. Whether to keep "pull requests only" on `main` is an escalation item, asked separately.

## Consequences

- The Python 3.11 compatibility run is gone. The code targets the device's Python (3.14 per Decky's source); `ruff` still targets `py311` syntax.
- Release integrity rests on the owner's machine and minisign key instead of CI isolation. Threat model T10 is updated: the minisign signature becomes the main control, and SHA-256 alone only proves the download matches what was published.
- Nothing is checked automatically on push. The slice report must state which checks were run and their results.
- The device venv lives at `~/.cache/keepsake-test-venv` on the device. It is development only and can be deleted at any time.
