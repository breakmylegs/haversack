import { ButtonItem, DialogButton, Field, PanelSection, PanelSectionRow, SidebarNavigation, SidebarNavigationPage, Tabs } from "@decky/ui";
import { ReactElement, ReactNode, useEffect, useRef, useState } from "react";
import { FaCog, FaCompactDisc, FaExchangeAlt, FaStethoscope } from "react-icons/fa";
import { ModuleStatus, modulesStatus } from "../backend";
import { navlog, setNavRoot } from "../navlog";
import { LAYOUT, ModuleName, section as sectionSpec } from "../routeData";
import { lastPageOf, openPage, openSection, rememberPage, ROUTE_PATH, SectionId } from "../routes";
import { sidebarEntries } from "../sidebar";
import { DeviceChecks } from "./DeviceChecks";
import { EmulatorsPanel } from "./EmulatorsPanel";
import { DiagnosticsPage } from "./DiagnosticsPage";
import { GamesList } from "./GamesList";
import { HelpPage } from "./HelpPage";
import { InstallerPage } from "./InstallerPage";
import { LogsPage } from "./LogsPage";
import { ReplicationPage } from "./ReplicationPage";
import { SettingsPage } from "./SettingsPage";
import { ShortcutsEditor } from "./ShortcutsEditor";

export { ROUTE_PATH };

// The menu redesign (ADR-0095, docs/design/layout-v3.md): two levels.
// - The sidebar: the seven sections and nothing else, built once, never rebuilt while the page is
//   open. Each section's entry lists its sub-pages; moving down the sidebar opens none of them.
// - A section's own page: Steam's native Tabs, the pattern Decky's own store uses (a full route,
//   40 px from the top). L1 and R1 switch sub-pages, B goes back to the sidebar.
// No page or tab takes focus by itself (v0.41.1): Tabs is not given autoFocusContents.

// Okabe-Ito colours (ADR-0088), one per section, so each section is easy to find.
const ICONS: Record<SectionId, ReactElement> = {
  install: <FaCompactDisc style={{ color: "#F0E442" }} />,
  "games-devices": <FaExchangeAlt style={{ color: "#E69F00" }} />,
  settings: <FaCog style={{ color: "#8a8fa3" }} />,
  diagnostics: <FaStethoscope style={{ color: "#D55E00" }} />,
};

// Each panel a sub-page is made of (routeData's parts).
const PARTS: Record<string, () => ReactElement> = {
  install: () => <InstallerPage />,
  games: () => <GamesList />,
  moving: () => <ReplicationPage part="moving" />,
  devices: () => <ReplicationPage part="devices" />,
  emulators: () => <EmulatorsPanel />,
  general: () => <SettingsPage part="general" />,
  "quick-menu": () => <ShortcutsEditor />,
  modules: () => <SettingsPage part="modules" />,
  updates: () => <SettingsPage part="updates" />,
  help: () => <HelpPage />,
  checks: () => <DeviceChecks />,
  tools: () => <DiagnosticsPage />,
  logs: () => <LogsPage />,
};

/** A module's state for a panel that needs it, read when the panel opens. Never affects the menu. */
function useModule(name: ModuleName): ModuleStatus | null | "unknown" {
  const [found, setFound] = useState<ModuleStatus | null | "unknown">(name === "core" ? null : "unknown");
  useEffect(() => {
    if (name === "core") return;
    let live = true;
    modulesStatus()
      .then((s) => live && setFound(s.modules.find((m) => m.name === name) ?? null))
      .catch(() => live && setFound(null));
    return () => {
      live = false;
    };
  }, [name]);
  return found;
}

/** One panel: stands in when its module is off. */
function PartShell({ module, children }: { module: ModuleName; children: ReactNode }) {
  const state = useModule(module);
  if (state === "unknown") return <Field label="Loading" />;
  if (state && !state.running) {
    return (
      <Field
        label="This is off"
        description={
          state.available
            ? `${state.title} is off. Turn it on in Settings, Modules.`
            : `${state.title} is not available here.${state.failed ? ` ${state.failed}` : ""}`
        }
      >
        {state.available && <DialogButton onClick={() => openSection("settings", "modules")}>Open Modules</DialogButton>}
      </Field>
    );
  }
  return <>{children}</>;
}

/** One sub-page: its panels, marked for the navigation recorder. */
function SubPage({ section, page }: { section: SectionId; page: string }) {
  const spec = sectionSpec(section)?.pages.find((p) => p.id === page);
  const id = `${section}/${page}`;
  useEffect(() => {
    navlog("page-mount", { page: id });
    return () => navlog("page-unmount", { page: id });
  }, []);
  return (
    <div data-keepsake-page={id} style={{ paddingBottom: 96 }}>
      {(spec?.parts ?? []).map((p) => (
        <PartShell key={p.id} module={p.module}>
          {PARTS[p.id]?.() ?? <Field label="Missing page" />}
        </PartShell>
      ))}
    </div>
  );
}

/** A section's entry in the sidebar: the list of its sub-pages. Shown as the sidebar moves; it takes
 * no focus and loads nothing, so moving down the sidebar opens nothing by itself. */
function SectionList({ section }: { section: SectionId }) {
  const spec = sectionSpec(section);
  if (!spec) return null;
  const last = spec.pages.find((p) => p.id === lastPageOf(section)) ?? spec.pages[0];
  return (
    <div data-keepsake-section={section}>
      <PanelSection>
        {spec.pages.length > 1 && (
          <PanelSectionRow>
            <ButtonItem layout="below" description={`Opens ${last.title}. L1 and R1 then move between the others.`} onClick={() => openPage(section)}>
              Open {spec.title}
            </ButtonItem>
          </PanelSectionRow>
        )}
        {spec.pages.map((p) => (
          <PanelSectionRow key={p.id}>
            <ButtonItem layout="below" description={p.about} onClick={() => openPage(section, p.id)}>
              {p.title}
            </ButtonItem>
          </PanelSectionRow>
        ))}
      </PanelSection>
    </div>
  );
}

// Built once, when the plugin loads: the same seven entries, in the same order, on every render.
const SIDEBAR: SidebarNavigationPage[] = sidebarEntries().map((e) => ({
  title: e.title,
  icon: ICONS[e.section],
  route: e.route,
  content: <SectionList section={e.section} />,
}));

export function KeepsakeRoute() {
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setNavRoot(rootRef.current);
    return () => setNavRoot(null);
  }, []);
  return (
    <div ref={rootRef} data-keepsake-root="" style={{ marginTop: 40, height: "calc(100% - 40px)" }}>
      <SidebarNavigation title="Haversack" showTitle pages={SIDEBAR} />
    </div>
  );
}

/** A section's own page: its sub-pages as Steam's native Tabs, opened on ``page``. The tab list is
 * built once per section and never changes while the page is open. */
export function SectionRoute({ section, page }: { section: SectionId; page: string }) {
  const spec = sectionSpec(section);
  const [active, setActive] = useState(page);
  const rootRef = useRef<HTMLDivElement>(null);
  const tabsRef = useRef(
    (spec?.pages ?? []).map((p) => ({ id: p.id, title: p.title, content: <SubPage section={section} page={p.id} /> })),
  );
  useEffect(() => {
    setNavRoot(rootRef.current);
    navlog("section-open", { section, page });
    return () => setNavRoot(null);
  }, []);
  const show = (tab: string) => {
    navlog("tab", { section, from: active, to: tab });
    rememberPage(section, tab);
    setActive(tab);
  };
  return (
    <div ref={rootRef} data-keepsake-root="" data-keepsake-section-page={section} style={{ marginTop: 40, height: "calc(100% - 40px)", background: "#0005" }}>
      <Tabs tabs={tabsRef.current} activeTab={active} onShowTab={show} />
    </div>
  );
}

/** An old address (a moved sub-page, or a page before v0.32.0): opens its sub-page. It is mounted
 * only when that exact address is opened, so it never fires during sidebar moves. */
export function LegacyRedirect({ section, page }: { section: SectionId; page: string }) {
  useEffect(() => {
    navlog("redirect", { section, page });
    openSection(section, page);
  }, []);
  return null;
}

/** For tests and the recorder: every section and sub-page this build has. */
export const MENU = LAYOUT.map((s) => ({ section: s.id, pages: s.pages.map((p) => p.id) }));
