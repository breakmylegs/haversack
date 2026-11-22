// Route data and the full page's layout, with no Steam or Decky imports, so they can be tested on
// their own (v0.39.1, v0.41.1).

export const ROUTE_PATH = "/keepsake";
export const SETUP_PATH = "/keepsake-setup";

// Layout v3 (ADR-0073): seven sections grouped by what the player is doing.
// "games-devices", not "games": /keepsake/games was the old Games page, and the two must never
// share a route (v0.39.1: they did, and the sidebar matched the wrong entry).
export type SectionId = "play" | "saves" | "games-devices" | "device" | "install" | "settings" | "diagnostics";
export const SECTION_IDS: SectionId[] = ["play", "saves", "games-devices", "device", "install", "settings", "diagnostics"];

export type ModuleName = "saves" | "core" | "installer" | "advisor" | "replication" | "device";

export interface TabSpec {
  id: string;
  title: string; // the sidebar entry's name: unique across the whole sidebar
  module: ModuleName;
}

export interface SectionSpec {
  id: SectionId;
  title: string;
  tabs: TabSpec[];
}

// v0.41.1: every tab is its own sidebar entry, and a section is the group between two lines, as
// in Steam's own settings. The list never changes while the page is open: a module that is off
// keeps its entries, which say so inside (ADR-0073 addendum).
export const LAYOUT: SectionSpec[] = [
  {
    id: "play",
    title: "Play",
    tabs: [
      { id: "now", title: "Now playing", module: "core" },
      { id: "advisor", title: "Advisor", module: "advisor" },
    ],
  },
  {
    id: "saves",
    title: "Saves",
    tabs: [
      { id: "games", title: "Games", module: "saves" },
      { id: "conflicts", title: "Conflicts", module: "saves" },
      { id: "history", title: "History", module: "saves" },
      { id: "activity", title: "Activity", module: "saves" },
      { id: "import", title: "Import and export", module: "saves" },
    ],
  },
  {
    id: "games-devices",
    title: "Games and devices",
    tabs: [
      { id: "moving", title: "Moving games", module: "replication" },
      { id: "devices", title: "Other devices", module: "replication" },
      { id: "disk", title: "Disk use", module: "core" },
    ],
  },
  {
    id: "device",
    title: "Device",
    tabs: [
      { id: "status", title: "Device status", module: "core" },
      { id: "power", title: "Power", module: "device" },
      { id: "battery", title: "Battery", module: "device" },
      { id: "fans", title: "Fans", module: "device" },
      { id: "controllers", title: "Controllers", module: "core" },
      { id: "reconnect", title: "Reconnect help", module: "device" },
      { id: "other", title: "More device settings", module: "device" },
    ],
  },
  { id: "install", title: "Install", tabs: [{ id: "install", title: "Install", module: "installer" }] },
  {
    id: "settings",
    title: "Settings",
    tabs: [
      { id: "general", title: "General", module: "core" },
      { id: "cloud", title: "Cloud", module: "core" },
      { id: "sync", title: "Sync and safety", module: "saves" },
      { id: "modules", title: "Modules", module: "core" },
      { id: "updates", title: "Updates", module: "core" },
    ],
  },
  {
    id: "diagnostics",
    title: "Diagnostics",
    tabs: [
      { id: "health", title: "Health", module: "core" },
      { id: "checks", title: "Device checks", module: "core" },
      { id: "tools", title: "Tools", module: "core" },
      { id: "logs", title: "Logs", module: "core" },
    ],
  },
];

export function sectionPath(section: SectionId): string {
  return `${ROUTE_PATH}/${section}`;
}

export function firstTab(section: SectionId): string {
  return LAYOUT.find((s) => s.id === section)?.tabs[0]?.id ?? "";
}

/** One sidebar entry's route: the section and the tab. A tab that does not exist opens the first. */
export function pagePath(section: SectionId, tab?: string): string {
  const spec = LAYOUT.find((s) => s.id === section);
  const id = spec?.tabs.some((t) => t.id === tab) ? tab : firstTab(section);
  return `${sectionPath(section)}/${id}`;
}

// The pages before v0.32.0, so old links keep working: page to [section, tab].
export const LEGACY: Record<string, [SectionId, string]> = {
  games: ["saves", "games"],
  conflicts: ["saves", "conflicts"],
  history: ["saves", "history"],
  activity: ["saves", "activity"],
  import: ["saves", "import"],
  advisor: ["play", "advisor"],
  devices: ["games-devices", "moving"],
  storage: ["games-devices", "disk"],
  install: ["install", "install"],
  settings: ["settings", "general"],
  updates: ["settings", "updates"],
  logs: ["diagnostics", "logs"],
  diagnostics: ["diagnostics", "health"],
};
