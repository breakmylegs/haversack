# ADR-0046: User documentation: where it lives, screenshots and checks

- Status: accepted (Peter's D1 request, 17 November 2026; details decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)

## Context

Peter asked for detailed user documentation on GitHub:
- getting started for each device type;
- a guide per feature, privacy and an FAQ;
- automated screenshots from a harness with sample data, with a personal-data check;
- Mermaid or SVG diagrams;
- a release-time step that regenerates screenshots and checks links and images.

Where it lives and how it is published is decided here.

## Decision

1. **Plain Markdown in the repository, under `docs/user/`.**
   - **Rendering:** GitHub renders Markdown and Mermaid diagrams natively. It is linked from the top of `README.md`.
   - **Not GitHub Pages:** publishing from a branch runs through GitHub Actions, which ADR-0004 rules out.
   - **Not a wiki:** a wiki lives outside the pull request flow, so its pages could drift from the code.
   - **The benefit:** in the repository, the docs are reviewed and versioned with the change they describe.
2. **Screenshots from the real interface with sample data.**
   - **The harness:** `scripts/docs_screenshots.py` serves the built desktop interface through the real loopback API (`keepsake.host.Api`), backed by `SampleApp`. It answers every call the pages make with synthetic games, devices and snapshots, and nothing else.
   - **Capture:** headless Edge or Chromium captures each page at 1100 by 820 in the light theme into `docs/user/images/desktop-<page>.png`.
   - **Stable output:** each event stream is closed at once, so the browser's virtual time budget waits for the page to finish loading. The output is byte-for-byte reproducible.
   - **Reading real data is impossible by construction:** the harness never constructs `KeepsakeApp`, so it cannot read this machine's games, settings or saves.
3. **Gaming Mode is described in words.** Its screens are `@decky/ui` components that only render inside Steam, so they cannot be captured automatically. The handheld guides name each control exactly as the code labels it. Screenshots taken on a device can be added later, after the same personal-data review.
4. **Checks in the quality gate.** `scripts/check_docs.py` runs as the gate's `docs` step and fails on:
   - a relative link or image in `README.md` or `docs/user/*.md` that does not resolve;
   - a screenshot no page uses;
   - a PNG carrying text chunks (`tEXt`, `iTXt`, `zTXt`), which could hold a path or a name;
   - a Mermaid block that does not start with a diagram type GitHub renders;
   - an app ID in the sample data that is not synthetic (Steam IDs from 1999999000, shortcuts from 2^31; P12).

   The secret scan already covers every page and the harness, including the denylist of personal strings.
5. **A release step.** `docs/releasing.md` adds three steps to each release:
   - rebuild the desktop interface;
   - regenerate the screenshots;
   - run the docs check.

   Changed images go in the changelog pull request.

## Consequences

- The guide covers getting started on a handheld, a Linux PC and Windows; how syncing works; cloud sign-in; conflicts and history; Ludusavi import; the Installer; Advisor; Replication (as planned, marked in development); updates; privacy; and questions and answers.
- The harness found three interface faults, all fixed in the same change:
  - the Overview showed the raw store name;
  - conflict cards were nested inside a second card;
  - the conflict text read "version(s)".
- Pages describe the released behaviour. Where a feature waits on something, the page says so, for example that releases up to 0.25.0 need your own app registration.
