// The full page's sidebar as plain data (layout v3, ADR-0073; fixed in v0.39.1 and v0.41.1).
//
// Steam's SidebarNavigation tracks the selected page and focus by position, and remounts when its
// pages change. So the list is static: built from LAYOUT alone, never from the module state, the
// same on every render for as long as the page is open (v0.41.1). Each tab is its own entry and
// lines separate the sections, so there is no row of tabs inside a page for the D-pad to cross.
// Kept free of React so it can be tested on its own.

import { LAYOUT, LEGACY, ModuleName, ROUTE_PATH, SECTION_IDS, SectionId, firstTab, pagePath, sectionPath } from "./routeData";

export type SidebarEntry =
  | { kind: "page"; section: SectionId; tab: string; title: string; module: ModuleName; route: string }
  | { kind: "separator" };

/** Every section's tabs, in order, with a line between sections. Takes no input on purpose. */
export function sidebarEntries(): SidebarEntry[] {
  const out: SidebarEntry[] = [];
  LAYOUT.forEach((section, i) => {
    if (i > 0) out.push({ kind: "separator" });
    for (const tab of section.tabs) {
      out.push({ kind: "page", section: section.id, tab: tab.id, title: tab.title, module: tab.module, route: pagePath(section.id, tab.id) });
    }
  });
  return out;
}

/** Old addresses that open a page: each section's own address (before v0.41.1 a section was one
 * page) and the pages before v0.32.0. Each goes to a different address, so none can loop. */
export function legacyRoutes(): { path: string; section: SectionId; tab: string }[] {
  const out = SECTION_IDS.map((section) => ({ path: sectionPath(section), section, tab: firstTab(section) }));
  for (const [old, [section, tab]] of Object.entries(LEGACY)) {
    if (!(SECTION_IDS as string[]).includes(old)) out.push({ path: `${ROUTE_PATH}/${old}`, section, tab });
  }
  return out;
}
