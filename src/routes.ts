// Route paths for Keepsake's pages.
import { Navigation } from "@decky/ui";

export const ROUTE_PATH = "/keepsake";
export const SETUP_PATH = "/keepsake-setup";

// Layout v3 (ADR-0073): seven sections, each with tabs.
export type SectionId = "play" | "saves" | "games" | "device" | "install" | "settings" | "diagnostics";

// The tab a link asked for, taken by the section when it opens.
const requested: Partial<Record<SectionId, string>> = {};

export function sectionPath(section: SectionId): string {
  return `${ROUTE_PATH}/${section}`;
}

/** Ask for ``tab`` the next time ``section`` opens (or now, if it is open). */
export function requestTab(section: SectionId, tab?: string): void {
  if (tab) requested[section] = tab;
  window.dispatchEvent(new CustomEvent("keepsake-tab", { detail: { section, tab } }));
}

/** Open ``section`` at ``tab``, from anywhere: the quick access menu, another section, a toast. */
export function openSection(section: SectionId, tab?: string): void {
  requestTab(section, tab);
  Navigation.Navigate(sectionPath(section));
}

export function takeRequestedTab(section: SectionId): string | undefined {
  const tab = requested[section];
  delete requested[section];
  return tab;
}

// The pages before v0.32.0, so old links keep working: page to [section, tab].
export const LEGACY: Record<string, [SectionId, string]> = {
  games: ["saves", "games"],
  conflicts: ["saves", "conflicts"],
  history: ["saves", "history"],
  activity: ["saves", "activity"],
  import: ["saves", "import"],
  advisor: ["play", "advisor"],
  devices: ["games", "moving"],
  storage: ["games", "disk"],
  install: ["install", "install"],
  settings: ["settings", "general"],
  updates: ["settings", "updates"],
  logs: ["diagnostics", "logs"],
  diagnostics: ["diagnostics", "health"],
};
