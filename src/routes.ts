// Route paths for Keepsake's pages.
import { Navigation } from "@decky/ui";
import { SectionId, sectionPath } from "./routeData";

export { LEGACY, ROUTE_PATH, SETUP_PATH, sectionPath } from "./routeData";
export type { SectionId } from "./routeData";



// The tab a link asked for, taken by the section when it opens.
const requested: Partial<Record<SectionId, string>> = {};


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

