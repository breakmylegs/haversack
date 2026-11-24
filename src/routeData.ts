// Route data and the full page's layout, with no Steam or Decky imports, so they can be tested on
// their own (v0.39.1, v0.41.1, the menu redesign, ADR-0095, and the strip, ADR-0098).

export const ROUTE_PATH = "/keepsake";

// The strip (ADR-0098): Haversack installs games and moves them between your devices. Four sections.
// "games-devices", not "games": /keepsake/games was the old Games page, and the two must never
// share a route (v0.39.1: they did, and the sidebar matched the wrong entry).
export type SectionId = "install" | "games-devices" | "settings" | "diagnostics";
export const SECTION_IDS: SectionId[] = ["install", "games-devices", "settings", "diagnostics"];

export type ModuleName = "core" | "installer" | "replication";

/** One panel inside a sub-page, with the module it needs. */
export interface PartSpec {
  id: string;
  module: ModuleName;
}

/** A sub-page: one of Steam's native tabs on the section's own page. */
export interface PageSpec {
  id: string;
  title: string; // unique within its section
  about: string; // one line on the section's list in the sidebar
  parts: PartSpec[];
}

export interface SectionSpec {
  id: SectionId;
  title: string;
  pages: PageSpec[];
}

const part = (id: string, module: ModuleName): PartSpec => ({ id, module });

// The sidebar has these entries and nothing else, in this order, for as long as the page is open.
// A module that is off keeps its sub-pages, which say so inside. At most six sub-pages each.
export const LAYOUT: SectionSpec[] = [
  {
    id: "install",
    title: "Install",
    pages: [{ id: "install", title: "Install", about: "Install a game from an ISO, a folder or a network share.", parts: [part("install", "installer")] }],
  },
  {
    id: "games-devices",
    title: "Games and devices",
    pages: [
      { id: "games", title: "Games", about: "Your non-Steam games: send one, keep it in step, find its artwork.", parts: [part("games", "core")] },
      { id: "moving", title: "Moving games", about: "Games on their way between your devices, and games kept in step.", parts: [part("moving", "replication")] },
      { id: "devices", title: "Other devices", about: "Pair your other handheld.", parts: [part("devices", "replication")] },
      { id: "emulators", title: "Emulators", about: "Emulator games, and sending them to your other handheld.", parts: [part("emulators", "replication")] },
    ],
  },
  {
    id: "settings",
    title: "Settings",
    pages: [
      { id: "general", title: "General", about: "This device's name, and what the quick menu shows.", parts: [part("general", "core"), part("quick-menu", "core")] },
      { id: "modules", title: "Modules", about: "Switch Installer and Replication on or off.", parts: [part("modules", "core")] },
      { id: "updates", title: "Updates", about: "New versions, and going back to an earlier one.", parts: [part("updates", "core")] },
      { id: "help", title: "Help", about: "The user guide.", parts: [part("help", "core")] },
    ],
  },
  {
    id: "diagnostics",
    title: "Diagnostics",
    pages: [
      { id: "checks", title: "Device checks", about: "Run the device checks and export the results.", parts: [part("checks", "core")] },
      { id: "tools", title: "Tools", about: "Diagnostics export and the navigation recorder.", parts: [part("tools", "core")] },
      { id: "logs", title: "Logs", about: "Haversack's own log.", parts: [part("logs", "core")] },
    ],
  },
];

// Sub-pages that moved or went (v0.41.1 to v0.60.0): section/page to where it is now. Pages of
// removed features open the nearest page that is left, never a blank one.
export const MOVED: Record<string, [SectionId, string]> = {
  "settings/quick-menu": ["settings", "general"],
  "settings/cloud": ["settings", "general"],
  "settings/sync": ["settings", "general"],
  "diagnostics/health": ["diagnostics", "checks"],
  "games-devices/disk": ["games-devices", "games"],
};

// The pages before v0.32.0, and the sections the strip removed (ADR-0098), so old links keep working:
// page or section to [section, page].
export const LEGACY: Record<string, [SectionId, string]> = {
  games: ["games-devices", "games"],
  saves: ["games-devices", "games"],
  storage: ["games-devices", "games"],
  play: ["install", "install"],
  advisor: ["install", "install"],
  device: ["diagnostics", "checks"],
  devices: ["games-devices", "moving"],
  install: ["install", "install"],
  settings: ["settings", "general"],
  updates: ["settings", "updates"],
  logs: ["diagnostics", "logs"],
  diagnostics: ["diagnostics", "checks"],
};

export function section(id: SectionId): SectionSpec | undefined {
  return LAYOUT.find((s) => s.id === id);
}

/** The section's own address: its entry in the sidebar. */
export function sectionPath(id: SectionId): string {
  return `${ROUTE_PATH}/${id}`;
}

export function firstPage(id: SectionId): string {
  return section(id)?.pages[0]?.id ?? "";
}

/** Where a section and sub-page really are: moved pages follow their move, unknown ones open the first. */
export function resolve(sectionId: SectionId, page?: string): [SectionId, string] {
  const moved = page ? MOVED[`${sectionId}/${page}`] : undefined;
  if (moved) return moved;
  const spec = section(sectionId);
  return [sectionId, spec?.pages.some((p) => p.id === page) ? (page as string) : firstPage(sectionId)];
}

/** A sub-page's address: the section's own page with that tab open. */
export function pagePath(sectionId: SectionId, page?: string): string {
  const [s, p] = resolve(sectionId, page);
  return `${sectionPath(s)}/${p}`;
}
