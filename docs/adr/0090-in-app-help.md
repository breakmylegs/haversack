# ADR-0090: The in-app Help is the user guide, built and checked by the gate

- Status: accepted (R28; decided under ADR-0037)
- Date: 23 November 2026
- Deciders: Peter (owner)

## Context

R28 asks for the README and an in-app Help to be rewritten, and to stay in step with every release. Haversack had no in-app Help. The user guide (`docs/user`, ADR-0046) was only on GitHub, which a handheld in Gaming Mode cannot easily open. Principle 7 says every feature must work from Gaming Mode, and that includes finding out how to use it.

Two copies of the same text drift apart. A separate Help text would need its own upkeep, and a release could ship with Help that contradicts the guide.

## Decision

1. **One text.** The user guide in `docs/user` is the only source. `scripts/help.py` turns it into `src/help.ts`, in the guide's index order with the index first, plus the troubleshooting page:
   - **headings**, with their level;
   - **paragraphs**;
   - **list items**, with depth, and numbered steps keep their numbers;
   - **table rows** and **code lines**.

   Images and Mermaid diagrams are left out, because the text around them says the same. A link to another guide page becomes its text, a web link becomes "text (address)", and HTML is dropped. `**bold**` is kept, and the page shows it bold. No Markdown library is added.
2. **The same file for the desktop app.** The desktop build sees only `desktop/src` (ADR-0040), so the identical file is also written to `desktop/src/help.ts`.
3. **The gate keeps it in step.** `scripts/check.py` runs `scripts/help.py --check`. A pull request that changes the guide without rebuilding the Help fails the gate. Because every release goes through the gate (ADR-0004), every release ships Help that matches its guide.
4. **The pages.**
   - **Gaming Mode:** Settings, **Help**. A topic dropdown, then one focusable field per section, so the D-pad moves from section to section and the right stick scrolls a long one. Nothing takes focus by itself (v0.41.1).
   - **Desktop app:** Settings, Help. A topic list and the same text, built from text nodes only. The indents are CSS classes, because the host's CSP allows no inline styles.
5. **The README** is rewritten for Haversack: what each module does, the principles, install on a handheld and on PCs, the rename, and where help is. From now on, each release's docs pull request checks that the README still describes the release.

## Consequences

- The Help adds about 90 kB to each frontend bundle.
- Writing the guide is now writing the Help. The gate names the command to run when they differ.
- **Threat model:** no change. The Help is static text compiled into the bundle, with no network access. It reaches the screen only as React text or DOM text nodes, never as markup.
- **Device run:** step 51.
