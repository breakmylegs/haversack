// The full page's menu as plain data (layout v3, ADR-0073; v0.39.1, v0.41.1; the redesign, ADR-0095).
//
// Two levels. The sidebar holds the seven sections and nothing else. Steam's SidebarNavigation
// tracks the selected entry and focus by position and remounts when its pages change, so the list
// is static: built from LAYOUT alone, never from the module state. Each section's sub-pages live on
// the section's own route as Steam's native Tabs (the pattern Decky's own store uses), so L1 and R1
// switch them and B goes back to the sidebar. No Tabs inside a sidebar page, and no home-made row.
// Kept free of React so it can be tested on its own.

import { LAYOUT, LEGACY, MOVED, ModuleName, ROUTE_PATH, SECTION_IDS, SectionId, pagePath, resolve, sectionPath } from "./routeData";

export interface SidebarEntry {
  section: SectionId;
  title: string;
  route: string;
}

/** The seven sections, in order. Takes no input on purpose. */
export function sidebarEntries(): SidebarEntry[] {
  return LAYOUT.map((s) => ({ section: s.id, title: s.title, route: sectionPath(s.id) }));
}

export interface PageRoute {
  path: string;
  section: SectionId;
  page: string;
  modules: ModuleName[];
}

/** Every sub-page's own address, one exact route each (no route parameters to parse). */
export function pageRoutes(): PageRoute[] {
  return LAYOUT.flatMap((s) =>
    s.pages.map((p) => ({ path: pagePath(s.id, p.id), section: s.id, page: p.id, modules: p.parts.map((x) => x.module) })),
  );
}

/** Old addresses that open a sub-page: pages that moved in the redesign, and the pages before
 * v0.32.0. Each goes to a sub-page's own address, never to another old one, so none can loop. A
 * section's own address (a page before v0.41.1) is its sidebar entry again, so it is not here. */
export function legacyRoutes(): { path: string; section: SectionId; page: string }[] {
  const out: { path: string; section: SectionId; page: string }[] = [];
  for (const [old, [s, p]] of Object.entries(MOVED)) out.push({ path: `${ROUTE_PATH}/${old}`, section: s, page: p });
  for (const [old, [s, p]] of Object.entries(LEGACY)) {
    if (!(SECTION_IDS as string[]).includes(old)) {
      const [rs, rp] = resolve(s, p);
      out.push({ path: `${ROUTE_PATH}/${old}`, section: rs, page: rp });
    }
  }
  return out;
}
