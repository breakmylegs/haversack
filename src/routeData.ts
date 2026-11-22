// Route data with no Steam or Decky imports, so it can be tested on its own (v0.39.1).

export const ROUTE_PATH = "/keepsake";
export const SETUP_PATH = "/keepsake-setup";

// Layout v3 (ADR-0073): seven sections, each with tabs.
// "games-devices", not "games": /keepsake/games was the old Games page, and the two must never
// share a route (v0.39.1: they did, and the sidebar matched the wrong entry).
export type SectionId = "play" | "saves" | "games-devices" | "device" | "install" | "settings" | "diagnostics";
export const SECTION_IDS: SectionId[] = ["play", "saves", "games-devices", "device", "install", "settings", "diagnostics"];

export function sectionPath(section: SectionId): string {
  return `${ROUTE_PATH}/${section}`;
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
