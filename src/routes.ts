// Route paths for Haversack's pages, and the last sub-page used in each section (ADR-0095).
import { Navigation } from "@decky/ui";
import { navlog } from "./navlog";
import { SectionId, firstPage, pagePath, resolve, sectionPath } from "./routeData";

export { LEGACY, ROUTE_PATH, pagePath, sectionPath } from "./routeData";
export type { SectionId } from "./routeData";

// The last sub-page used in each section, while Haversack is loaded. Not saved: a fresh start opens
// each section on its first sub-page.
const lastPage = new Map<SectionId, string>();

export function rememberPage(section: SectionId, page: string): void {
  lastPage.set(section, page);
}

export function lastPageOf(section: SectionId): string {
  return lastPage.get(section) ?? firstPage(section);
}

/** Open a section's sub-page from the sidebar's list: one step, from the section's sidebar entry. */
export function openPage(section: SectionId, page?: string): void {
  const [s, p] = resolve(section, page ?? lastPageOf(section));
  rememberPage(s, p);
  navlog("navigate", { to: pagePath(s, p) });
  Navigation.Navigate(pagePath(s, p));
}

/** Open a section's sub-page from anywhere else: the quick access menu, a toast, another page. The
 * sidebar, on that section, goes first, so B from the sub-page lands on it. Only ever from a user
 * action (or an old address being opened): never while the sidebar is being used. */
export function openSection(section: SectionId, page?: string): void {
  const [s, p] = resolve(section, page ?? lastPageOf(section));
  rememberPage(s, p);
  navlog("navigate", { to: pagePath(s, p), via: sectionPath(s) });
  Navigation.Navigate(sectionPath(s));
  Navigation.Navigate(pagePath(s, p));
}
