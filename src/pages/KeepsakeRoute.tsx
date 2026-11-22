import { DialogButton, Field, SidebarNavigation, SidebarNavigationPage } from "@decky/ui";
import { ReactElement, ReactNode, useEffect, useRef, useState } from "react";
import { FaCog, FaCompactDisc, FaExchangeAlt, FaMicrochip, FaPlay, FaSave, FaStethoscope } from "react-icons/fa";
import { ModuleStatus, modulesStatus } from "../backend";
import { navlog, setNavRoot } from "../navlog";
import { ModuleName } from "../routeData";
import { openSection, ROUTE_PATH, SectionId } from "../routes";
import { sidebarEntries } from "../sidebar";
import { ActivityPage } from "./ActivityPage";
import { AdvisorPage } from "./AdvisorPage";
import { BatteryPanel } from "./BatteryPanel";
import { ConflictsPage } from "./ConflictsPage";
import { ControllersPanel } from "./ControllersPanel";
import { DeviceChecks } from "./DeviceChecks";
import { DeviceStatusPage } from "./DeviceStatusPage";
import { EmulatorsPanel } from "./EmulatorsPanel";
import { DiagnosticsPage } from "./DiagnosticsPage";
import { ExportSection } from "./ExportSection";
import { ExtrasPanel } from "./ExtrasPanel";
import { FansPanel } from "./FansPanel";
import { GamesPage } from "./GamesPage";
import { HealthSection } from "./HealthSection";
import { HistoryPage } from "./HistoryPage";
import { ImportPage } from "./ImportPage";
import { InstallerPage } from "./InstallerPage";
import { LogsPage } from "./LogsPage";
import { NowPlaying } from "./NowPlaying";
import { PowerPanel } from "./PowerPanel";
import { ReconnectPanel } from "./ReconnectPanel";
import { ReplicationPage } from "./ReplicationPage";
import { SettingsPage } from "./SettingsPage";
import { ShortcutsEditor } from "./ShortcutsEditor";
import { StoragePage } from "./StoragePage";

export { ROUTE_PATH };

// Layout v3 (ADR-0073, docs/design/layout-v3.md), v0.41.1: a static sidebar. Every tab is its own
// entry, sections are separated by lines, and the list is built once and never changes while the
// page is open. A module that is off keeps its entries; they say so inside instead of vanishing.

const ICONS: Record<SectionId, ReactElement> = {
  play: <FaPlay />,
  saves: <FaSave />,
  "games-devices": <FaExchangeAlt />,
  device: <FaMicrochip />,
  install: <FaCompactDisc />,
  settings: <FaCog />,
  diagnostics: <FaStethoscope />,
};

const CONTENT: Record<string, () => ReactElement> = {
  "play/now": () => <NowPlaying />,
  "play/advisor": () => <AdvisorPage />,
  "saves/games": () => <GamesPage />,
  "saves/conflicts": () => <ConflictsPage />,
  "saves/history": () => <HistoryPage />,
  "saves/activity": () => <ActivityPage />,
  "saves/import": () => (
    <div>
      <ImportPage />
      <ExportSection />
    </div>
  ),
  "games-devices/moving": () => <ReplicationPage part="moving" />,
  "games-devices/devices": () => <ReplicationPage part="devices" />,
  "games-devices/emulators": () => <EmulatorsPanel />,
  "games-devices/disk": () => <StoragePage />,
  "device/status": () => <DeviceStatusPage />,
  "device/power": () => <PowerPanel />,
  "device/battery": () => <BatteryPanel />,
  "device/fans": () => <FansPanel />,
  "device/controllers": () => <ControllersPanel />,
  "device/reconnect": () => <ReconnectPanel />,
  "device/other": () => <ExtrasPanel />,
  "install/install": () => <InstallerPage />,
  "settings/general": () => <SettingsPage part="general" />,
  "settings/cloud": () => <SettingsPage part="cloud" />,
  "settings/sync": () => <SettingsPage part="sync" />,
  "settings/modules": () => <SettingsPage part="modules" />,
  "settings/quick-menu": () => <ShortcutsEditor />,
  "settings/updates": () => <SettingsPage part="updates" />,
  "diagnostics/health": () => <HealthSection />,
  "diagnostics/checks": () => <DeviceChecks />,
  "diagnostics/tools": () => <DiagnosticsPage />,
  "diagnostics/logs": () => <LogsPage />,
};

/** A module's state for a page that needs it, read when that page opens. Never affects the sidebar. */
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

/** One sidebar page: marks itself for the navigation recorder, and stands in when its module is off. */
function PageShell({ section, tab, module, children }: { section: SectionId; tab: string; module: ModuleName; children: ReactNode }) {
  const id = `${section}/${tab}`;
  const state = useModule(module);
  useEffect(() => {
    navlog("page-mount", { page: id });
    return () => navlog("page-unmount", { page: id });
  }, []);
  let body: ReactNode = children;
  if (state === "unknown") body = <Field label="Loading" />;
  else if (state && !state.running) {
    body = (
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
  return <div data-keepsake-page={id}>{body}</div>;
}

// Built once, when the plugin loads: the same array, in the same order, on every render.
const PAGES: (SidebarNavigationPage | "separator")[] = sidebarEntries().map((e) =>
  e.kind === "separator"
    ? "separator"
    : {
        title: e.title,
        icon: ICONS[e.section],
        route: e.route,
        content: (
          <PageShell section={e.section} tab={e.tab} module={e.module}>
            {CONTENT[`${e.section}/${e.tab}`]?.() ?? <Field label="Missing page" />}
          </PageShell>
        ),
      },
);

export function KeepsakeRoute() {
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setNavRoot(rootRef.current);
    return () => setNavRoot(null);
  }, []);
  return (
    <div ref={rootRef} data-keepsake-root="" style={{ marginTop: 40, height: "calc(100% - 40px)" }}>
      <SidebarNavigation title="Keepsake" showTitle pages={PAGES} />
    </div>
  );
}

/** An old address (a section before v0.41.1, a page before v0.32.0): opens its page. It is
 * mounted only when that exact address is opened, so it never fires during sidebar moves. */
export function LegacyRedirect({ section, tab }: { section: SectionId; tab: string }) {
  useEffect(() => {
    navlog("redirect", { section, tab });
    openSection(section, tab);
  }, []);
  return null;
}
