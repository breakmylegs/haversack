// The full page's sidebar as plain data (layout v3, ADR-0073; fixed in v0.39.1).
//
// Steam's SidebarNavigation tracks the selected page and focus by position. So the list must
// be built once, from the loaded module state, and never contain hidden entries: before
// v0.39.1 it started with a guess (Saves only), grew when the real module state arrived, and
// carried hidden legacy pages at the end, so clicks and the D-pad landed on the wrong entries.
// Kept free of React so it can be tested on its own.

import { LEGACY, ROUTE_PATH, SECTION_IDS, SectionId, sectionPath } from "./routeData";

export type ModuleName = "saves" | "core" | "installer" | "advisor" | "replication" | "device";

export interface TabSpec {
  id: string;
  module: ModuleName;
}

export interface SectionSpec {
  id: SectionId;
  tabs: TabSpec[];
}

export type SidebarEntry = { kind: "page"; section: SectionId; route: string; tabs: string[] } | { kind: "separator" };

// Where the sidebar draws a line: after Play, after Games and devices, and after Install.
export const SEPARATE_AFTER: SectionId[] = ["play", "games-devices", "install"];

/** The sidebar for the modules that run: sections with no tab left are dropped, and no
 * separator is ever first, last or doubled. Every page entry is visible. */
export function sidebarEntries(sections: SectionSpec[], running: Set<string>): SidebarEntry[] {
  const out: SidebarEntry[] = [];
  for (const section of sections) {
    const tabs = section.tabs.filter((t) => t.module === "core" || running.has(t.module)).map((t) => t.id);
    if (!tabs.length) continue;
    out.push({ kind: "page", section: section.id, route: sectionPath(section.id), tabs });
    if (SEPARATE_AFTER.includes(section.id)) out.push({ kind: "separator" });
  }
  while (out.length && out[out.length - 1].kind === "separator") out.pop();
  return out;
}

/** A stable key for the sidebar: it changes only when the set of sections or tabs changes. */
export function sidebarKey(entries: SidebarEntry[]): string {
  return entries.map((e) => (e.kind === "page" ? `${e.section}:${e.tabs.join(",")}` : "|")).join(";");
}

/** The pages before v0.32.0 that need a redirect: their old route, and the section and tab they
 * now open. An old route that is also a section's route today (install, settings, diagnostics)
 * is that section, so it gets no redirect: one would loop back to itself. */
export function legacyRoutes(): { path: string; section: SectionId; tab: string }[] {
  return Object.entries(LEGACY)
    .filter(([old]) => !(SECTION_IDS as string[]).includes(old))
    .map(([old, [section, tab]]) => ({ path: `${ROUTE_PATH}/${old}`, section, tab }));
}
