// Route data and the full page's layout, with no Steam or Decky imports, so they can be tested on
// their own (v0.39.1, v0.41.1, and the menu redesign, ADR-0095).

export const ROUTE_PATH = "/keepsake";
export const SETUP_PATH = "/keepsake-setup";

// Seven sections grouped by what the player is doing (layout v3, ADR-0073 and its ADR-0095 addendum).
// "games-devices", not "games": /keepsake/games was the old Games page, and the two must never
// share a route (v0.39.1: they did, and the sidebar matched the wrong entry).
export type SectionId = "play" | "saves" | "games-devices" | "device" | "install" | "settings" | "diagnostics";
export const SECTION_IDS: SectionId[] = ["play", "saves", "games-devices", "device", "install", "settings", "diagnostics"];

export type ModuleName = "saves" | "core" | "installer" | "advisor" | "replication" | "device" | "looks";

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

// The sidebar has these seven entries and nothing else, in this order, for as long as the page is
// open. A module that is off keeps its sub-pages, which say so inside. At most six sub-pages each.
export const LAYOUT: SectionSpec[] = [
  {
    id: "play",
    title: "Play",
    pages: [
      { id: "now", title: "Now playing", about: "The game you are playing, its saves and a checkpoint.", parts: [part("now", "core")] },
      { id: "advisor", title: "Advisor", about: "Recommended settings for this device. It never changes anything.", parts: [part("advisor", "advisor")] },
    ],
  },
  {
    id: "saves",
    title: "Saves",
    pages: [
      { id: "games", title: "Games", about: "Every game, whether its saves sync, and its own settings.", parts: [part("games", "saves")] },
      { id: "conflicts", title: "Conflicts", about: "Games whose saves changed on two devices.", parts: [part("conflicts", "saves")] },
      { id: "history", title: "History", about: "Every snapshot, to restore, pin or undo.", parts: [part("history", "saves")] },
      { id: "activity", title: "Activity", about: "What Haversack did, in plain words.", parts: [part("activity", "saves")] },
      { id: "import", title: "Import and export", about: "Bring in Ludusavi backups, or copy your snapshots out.", parts: [part("import", "saves")] },
    ],
  },
  {
    id: "games-devices",
    title: "Games and devices",
    pages: [
      { id: "moving", title: "Moving games", about: "Games on their way between your devices, and games kept in step.", parts: [part("moving", "replication")] },
      { id: "devices", title: "Other devices", about: "Pair your other handheld or PC.", parts: [part("devices", "replication")] },
      { id: "emulators", title: "Emulators", about: "Emulator games, and sending them to your other handheld.", parts: [part("emulators", "replication")] },
    ],
  },
  {
    id: "device",
    title: "Device",
    pages: [
      { id: "status", title: "Status", about: "Live readings, Wi-Fi power saving and the BIOS check.", parts: [part("status", "core"), part("other", "device")] },
      { id: "power", title: "Power and battery", about: "Performance for each game, power limits and the charge limit.", parts: [part("power", "device"), part("battery", "device")] },
      { id: "fans", title: "Fans", about: "Fan curves for each game.", parts: [part("fans", "device")] },
      { id: "controllers", title: "Controllers", about: "Controller settings and lights, and reconnect help.", parts: [part("controllers", "core"), part("reconnect", "device")] },
      { id: "storage", title: "Storage", about: "Disk use per game, shader caches and resetting a prefix.", parts: [part("storage", "core")] },
      { id: "looks", title: "Looks", about: "Boot and sleep animations, themes and sounds.", parts: [part("looks", "looks")] },
    ],
  },
  {
    id: "install",
    title: "Install",
    pages: [{ id: "install", title: "Install", about: "Install a game from an ISO, a folder or a network share.", parts: [part("install", "installer")] }],
  },
  {
    id: "settings",
    title: "Settings",
    pages: [
      { id: "general", title: "General", about: "This device's name, and what the quick menu shows.", parts: [part("general", "core"), part("quick-menu", "core")] },
      { id: "cloud", title: "Cloud", about: "Where your snapshots are kept, and signing in.", parts: [part("cloud", "core")] },
      { id: "sync", title: "Sync and safety", about: "When Haversack syncs, and the checks that guard your saves.", parts: [part("sync", "saves")] },
      { id: "modules", title: "Modules", about: "Switch Haversack's parts on or off.", parts: [part("modules", "core")] },
      { id: "updates", title: "Updates", about: "New versions, and going back to an earlier one.", parts: [part("updates", "core")] },
      { id: "help", title: "Help", about: "The user guide.", parts: [part("help", "core")] },
    ],
  },
  {
    id: "diagnostics",
    title: "Diagnostics",
    pages: [
      { id: "health", title: "Health", about: "Checks for sign-in, sync, prefixes and the manifest.", parts: [part("health", "core")] },
      { id: "checks", title: "Device checks", about: "Run the device checks and export the results.", parts: [part("checks", "core")] },
      { id: "tools", title: "Tools", about: "Diagnostics export, probes and the navigation recorder.", parts: [part("tools", "core")] },
      { id: "logs", title: "Logs", about: "Haversack's own log.", parts: [part("logs", "core")] },
    ],
  },
];

// Sub-pages from before the redesign that moved or merged (v0.41.1 to v0.56.0): section/page to its new home.
export const MOVED: Record<string, [SectionId, string]> = {
  "device/battery": ["device", "power"],
  "device/reconnect": ["device", "controllers"],
  "device/other": ["device", "status"],
  "games-devices/disk": ["device", "storage"],
  "settings/quick-menu": ["settings", "general"],
};

// The pages before v0.32.0, so old links keep working: page to [section, page].
export const LEGACY: Record<string, [SectionId, string]> = {
  games: ["saves", "games"],
  conflicts: ["saves", "conflicts"],
  history: ["saves", "history"],
  activity: ["saves", "activity"],
  import: ["saves", "import"],
  advisor: ["play", "advisor"],
  devices: ["games-devices", "moving"],
  storage: ["device", "storage"],
  install: ["install", "install"],
  settings: ["settings", "general"],
  updates: ["settings", "updates"],
  logs: ["diagnostics", "logs"],
  diagnostics: ["diagnostics", "health"],
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
