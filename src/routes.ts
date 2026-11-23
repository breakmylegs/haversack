// Route paths for Haversack's pages.
import { Navigation } from "@decky/ui";
import { navlog } from "./navlog";
import { SectionId, pagePath } from "./routeData";

export { LEGACY, ROUTE_PATH, SETUP_PATH, pagePath, sectionPath } from "./routeData";
export type { SectionId } from "./routeData";

/** Open a section's tab from anywhere: the quick access menu, another page, a toast. Only ever
 * from a user action (or an old address being opened): never while the sidebar is being used. */
export function openSection(section: SectionId, tab?: string): void {
  const path = pagePath(section, tab);
  navlog("navigate", { to: path });
  Navigation.Navigate(path);
}
