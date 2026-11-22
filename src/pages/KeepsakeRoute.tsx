import { Field, SidebarNavigation, SidebarNavigationPage } from "@decky/ui";
import { ReactElement, useEffect, useState } from "react";
import { FaCog, FaCompactDisc, FaExchangeAlt, FaMicrochip, FaPlay, FaSave, FaStethoscope } from "react-icons/fa";
import { modulesStatus } from "../backend";
import { openSection, ROUTE_PATH, SectionId } from "../routes";
import { sidebarEntries, sidebarKey } from "../sidebar";
import { ActivityPage } from "./ActivityPage";
import { AdvisorPage } from "./AdvisorPage";
import { ConflictsPage } from "./ConflictsPage";
import { DeviceChecks } from "./DeviceChecks";
import { DeviceStatusPage } from "./DeviceStatusPage";
import { DiagnosticsPage } from "./DiagnosticsPage";
import { ExportSection } from "./ExportSection";
import { GamesPage } from "./GamesPage";
import { HealthSection } from "./HealthSection";
import { HistoryPage } from "./HistoryPage";
import { ImportPage } from "./ImportPage";
import { InstallerPage } from "./InstallerPage";
import { LogsPage } from "./LogsPage";
import { NowPlaying } from "./NowPlaying";
import { BatteryPanel } from "./BatteryPanel";
import { ControllersPanel } from "./ControllersPanel";
import { ReconnectPanel } from "./ReconnectPanel";
import { ExtrasPanel } from "./ExtrasPanel";
import { PowerPanel } from "./PowerPanel";
import { ReplicationPage } from "./ReplicationPage";
import { SectionPage, SectionTab } from "./Section";
import { SettingsPage } from "./SettingsPage";
import { StoragePage } from "./StoragePage";

export { ROUTE_PATH };

// Layout v3 (ADR-0073, docs/design/layout-v3.md): seven sections grouped by what the player is
// doing, each with tabs. A module's tabs, and a section with none left, appear only while it runs
// (v2 spec 7.3: a disabled module has no UI).

type Module = "saves" | "core" | "installer" | "advisor" | "replication" | "device";

interface Tab extends SectionTab {
  module: Module;
}

interface Section {
  id: SectionId;
  title: string;
  icon: ReactElement;
  tabs: Tab[];
}

const SECTIONS: Section[] = [
  {
    id: "play",
    title: "Play",
    icon: <FaPlay />,
    tabs: [
      { module: "core", id: "now", title: "Now playing", content: <NowPlaying /> },
      { module: "advisor", id: "advisor", title: "Advisor", content: <AdvisorPage /> },
    ],
  },
  {
    id: "saves",
    title: "Saves",
    icon: <FaSave />,
    tabs: [
      { module: "saves", id: "games", title: "Games", content: <GamesPage /> },
      { module: "saves", id: "conflicts", title: "Conflicts", content: <ConflictsPage /> },
      { module: "saves", id: "history", title: "History", content: <HistoryPage /> },
      { module: "saves", id: "activity", title: "Activity", content: <ActivityPage /> },
      {
        module: "saves",
        id: "import",
        title: "Import and export",
        content: (
          <div>
            <ImportPage />
            <ExportSection />
          </div>
        ),
      },
    ],
  },
  {
    id: "games-devices",
    title: "Games and devices",
    icon: <FaExchangeAlt />,
    tabs: [
      { module: "replication", id: "moving", title: "Moving games", content: <ReplicationPage part="moving" /> },
      { module: "replication", id: "devices", title: "Other devices", content: <ReplicationPage part="devices" /> },
      { module: "core", id: "disk", title: "Disk use", content: <StoragePage /> },
    ],
  },
  {
    id: "device",
    title: "Device",
    icon: <FaMicrochip />,
    tabs: [
      { module: "core", id: "status", title: "Status", content: <DeviceStatusPage /> },
      { module: "device", id: "power", title: "Power", content: <PowerPanel /> },
      { module: "device", id: "battery", title: "Battery", content: <BatteryPanel /> },
      { module: "core", id: "controllers", title: "Controllers", content: <ControllersPanel /> },
      { module: "device", id: "reconnect", title: "Reconnect help", content: <ReconnectPanel /> },
      { module: "device", id: "other", title: "Other", content: <ExtrasPanel /> },
    ],
  },
  {
    id: "install",
    title: "Install",
    icon: <FaCompactDisc />,
    tabs: [{ module: "installer", id: "install", title: "Install", content: <InstallerPage /> }],
  },
  {
    id: "settings",
    title: "Settings",
    icon: <FaCog />,
    tabs: [
      { module: "core", id: "general", title: "General", content: <SettingsPage part="general" /> },
      { module: "core", id: "cloud", title: "Cloud", content: <SettingsPage part="cloud" /> },
      { module: "saves", id: "sync", title: "Sync and safety", content: <SettingsPage part="sync" /> },
      { module: "core", id: "modules", title: "Modules", content: <SettingsPage part="modules" /> },
      { module: "core", id: "updates", title: "Updates", content: <SettingsPage part="updates" /> },
    ],
  },
  {
    id: "diagnostics",
    title: "Diagnostics",
    icon: <FaStethoscope />,
    tabs: [
      { module: "core", id: "health", title: "Health", content: <HealthSection /> },
      { module: "core", id: "checks", title: "Device checks", content: <DeviceChecks /> },
      { module: "core", id: "tools", title: "Tools", content: <DiagnosticsPage /> },
      { module: "core", id: "logs", title: "Logs", content: <LogsPage /> },
    ],
  },
];

// v0.39.1: the sidebar is built once from the loaded module state (sidebar.ts), with no hidden
// entries; a change of modules rebuilds it under a new key, so the selection follows the route.
export function KeepsakeRoute() {
  const [running, setRunning] = useState<Set<string> | null>(null);
  useEffect(() => {
    let live = true;
    const fallback = setTimeout(() => live && setRunning((r) => r ?? new Set(["saves"])), MODULES_WAIT_MS);
    modulesStatus()
      .then((s) => live && setRunning(new Set(s.modules.filter((m) => m.running).map((m) => m.name))))
      .catch(() => live && setRunning(new Set(["saves"])));
    return () => {
      live = false;
      clearTimeout(fallback);
    };
  }, []);
  if (running === null) {
    return (
      <div style={{ marginTop: 40, padding: 24 }}>
        <Field label="Keepsake" description="Loading" />
      </div>
    );
  }
  const entries = sidebarEntries(SECTIONS, running);
  const pages: (SidebarNavigationPage | "separator")[] = entries.map((e) => {
    if (e.kind === "separator") return "separator";
    const section = SECTIONS.find((s) => s.id === e.section) as Section;
    const tabs = section.tabs.filter((t) => e.tabs.includes(t.id));
    return { title: section.title, icon: section.icon, content: <SectionPage section={section.id} tabs={tabs} />, route: e.route };
  });
  return (
    <div style={{ marginTop: 40, height: "calc(100% - 40px)" }}>
      <SidebarNavigation key={sidebarKey(entries)} title="Keepsake" showTitle pages={pages} />
    </div>
  );
}

const MODULES_WAIT_MS = 3000; // if the backend is slow, show the sidebar for Saves and Core

/** An old page's route (before v0.32.0): opens its new section and tab, then gets out of the way. */
export function LegacyRedirect({ section, tab }: { section: SectionId; tab: string }) {
  useEffect(() => {
    openSection(section, tab);
  }, []);
  return null;
}
