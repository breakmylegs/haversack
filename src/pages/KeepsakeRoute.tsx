import { SidebarNavigation, SidebarNavigationPage } from "@decky/ui";
import { ReactElement, useEffect, useState } from "react";
import { FaCog, FaCompactDisc, FaExchangeAlt, FaMicrochip, FaPlay, FaSave, FaStethoscope } from "react-icons/fa";
import { modulesStatus } from "../backend";
import { LEGACY, ROUTE_PATH, SectionId, sectionPath } from "../routes";
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
    id: "games",
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

// Where the sidebar draws a line: after Play, after Games and devices, and after Install.
const SEPARATE_AFTER: SectionId[] = ["play", "games", "install"];

export function KeepsakeRoute() {
  const [running, setRunning] = useState<Set<string>>(new Set(["saves"]));
  useEffect(() => {
    modulesStatus()
      .then((s) => setRunning(new Set(s.modules.filter((m) => m.running).map((m) => m.name))))
      .catch(() => undefined);
  }, []);
  const shown = SECTIONS.map((s) => ({ ...s, tabs: s.tabs.filter((t) => t.module === "core" || running.has(t.module)) })).filter(
    (s) => s.tabs.length,
  );
  const pages: (SidebarNavigationPage | "separator")[] = [];
  for (const s of shown) {
    pages.push({ title: s.title, icon: s.icon, content: <SectionPage section={s.id} tabs={s.tabs} />, route: sectionPath(s.id) });
    if (SEPARATE_AFTER.includes(s.id)) pages.push("separator");
  }
  // The pages before v0.32.0 still open, at their new tab, for links and habits from older versions.
  for (const [old, [section, tab]] of Object.entries(LEGACY)) {
    const target = shown.find((s) => s.id === section);
    if (!target) continue;
    const content = <SectionPage section={section} tabs={target.tabs} initial={tab} />;
    pages.push({ title: target.title, content, route: `${ROUTE_PATH}/${old}`, visible: false });
  }
  if (pages[pages.length - 1] === "separator") pages.pop();
  return (
    <div style={{ marginTop: 40, height: "calc(100% - 40px)" }}>
      <SidebarNavigation title="Keepsake" showTitle pages={pages} />
    </div>
  );
}
