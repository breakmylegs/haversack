# ADR-0040: The desktop interface: plain TypeScript, no framework

- Status: accepted (decided under ADR-0037; P3 of ADR-0038, amending its "plain React" wording)
- Date: 17 November 2026
- Deciders: Peter (owner)

## Context

ADR-0038 planned the desktop interface as plain React served by the PC host. The Decky interface's React comes from Steam's own copy through `@decky/ui`, and Decky's rollup preset builds for that. A React page outside Steam would need:
- its own React bundle;
- a second Rollup set-up with new plugins, which means new dependencies and a changed lockfile;
- an inline bootstrap, which the host's strict content security policy (`default-src 'self'`, ADR-0039) refuses.

## Decision

1. **Plain TypeScript.** The desktop interface is written against the DOM, in `desktop/src`. `tsc -p tsconfig.desktop.json` compiles it to browser ES modules in `desktop/dist`, with no bundler and no third-party code. It is built at packaging time; the build output is ignored by git.
2. **Text never becomes markup.** Every element is built by a small helper (`desktop/src/dom.ts`) that sets text through `textContent`, never `innerHTML`. Game names, device names and server messages can never inject markup. The CSP blocks inline scripts as well.
3. **Served from a fixed list.** The host serves only:
   - `/` (`index.html`);
   - `/app.css`;
   - `/dist/<name>.js`, where the name matches `[a-z][a-z0-9_-]{0,40}`.

   No path from the request is ever joined to a folder, so `..`, encoded separators and other folders are refused. When the interface is not built, `/` serves the placeholder page.
4. **Token and first page.** The token arrives once in the URL fragment, is kept for the tab only (`sessionStorage`) and is cleared from the address bar. The fragment may also name the first page (`#token=...&page=history`). The launcher and the documentation screenshots use that.
5. **Gate and build.**
   - **Gate:** a `desktop` step builds the interface, and ESLint covers `desktop/src`.
   - **Layout:** follows the system light or dark setting and has visible keyboard focus.
   - **Same rules as Gaming Mode:** conflict choices that replace files need a second, explicit press.
6. **Parity order.** The first pass covers Overview with Sync now, Conflicts with the choices, History, Health and Modules. Next come game setup and matching, cloud sign-in with the device code, settings, Import, Advisor (where on), and Updates.

## Consequences

- No new dependencies, no lockfile change, and the strictest CSP stays.
- The interface is more code per screen than React would be, which is acceptable at this size. A move to a framework later would be its own ADR.
- Rendered on this laptop: the real host served the built interface to headless Edge, through the launcher link, and the Modules page showed live data (Saves on, Advisor off on a PC, Replication not available yet).
