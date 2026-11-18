# D1 report: user documentation

Peter's D1 request, recorded in ADR-0046.

## What changed

- **`docs/user/`:** 14 pages.
  - **Getting started:** an index, plus guides for a handheld, a Linux PC and Windows.
  - **Features:** how syncing works (three Mermaid diagrams), cloud and sign-in, conflicts and history, Ludusavi import, Installer, Advisor, Replication (planned, with a diagram) and updates.
  - **Reference:** privacy (what is stored where, who Keepsake talks to, how to remove everything) and questions and answers.
- **Ten screenshots** of the desktop interface, from the real interface and API with synthetic sample data (`scripts/docs_screenshots.py`). They are reproducible byte for byte.
- **`scripts/check_docs.py`** is a new gate step. It checks links and images, unused screenshots, PNG text chunks, Mermaid diagram types and synthetic app IDs.
- **Release step:** added to `docs/releasing.md`.
- **README** now links to the guide, and its first-run cloud step points at the cloud page.
- **Interface fixes the screenshots revealed:**
  - the Overview store name;
  - nested conflict cards;
  - the "version(s)" text.

## Test results

- `tests/test_docs_checks.py` (7): passed. The real guide is clean, each fault is caught, and the harness serves only sample data through the real API.
- Mutation checks: 8 mutations of the checker, all killed.
- Screenshots regenerated twice with identical hashes.
- Quality gate: see the pull request.

## Known gaps

- Gaming Mode has no screenshots, because its screens only render inside Steam (ADR-0046). Photos from a device can be added after a personal-data review.
- The guide describes the current release. Built-in sign-in and Replication are marked as not yet available.

## Threat model and assumptions

- **T104** (new): screenshots or examples in public docs leaking personal data. Mitigated by synthetic sample data only, no harness access to real data, the PNG text-chunk check, synthetic app IDs and the secret scan.
- **A178** (new): headless Chromium's `--virtual-time-budget` waits for page loads once event streams close, and gives reproducible screenshots. Verified on this laptop with Edge.
