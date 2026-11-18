import { SidebarNavigation } from "@decky/ui";
import { ReactElement, useEffect, useState } from "react";
import {
  FaClipboardList,
  FaCloudDownloadAlt,
  FaCodeBranch,
  FaCompactDisc,
  FaCog,
  FaFileImport,
  FaGamepad,
  FaHistory,
  FaLightbulb,
  FaStethoscope,
  FaStream,
  FaHdd,
} from "react-icons/fa";
import { ROUTE_PATH } from "../routes";
import { ConflictsPage } from "./ConflictsPage";
import { DiagnosticsPage } from "./DiagnosticsPage";
import { GamesPage } from "./GamesPage";
import { HistoryPage } from "./HistoryPage";
import { ImportPage } from "./ImportPage";
import { InstallerPage } from "./InstallerPage";
import { AdvisorPage } from "./AdvisorPage";
import { modulesStatus } from "../backend";
import { ActivityPage } from "./ActivityPage";
import { StoragePage } from "./StoragePage";
import { LogsPage } from "./LogsPage";
import { SettingsPage } from "./SettingsPage";
import { UpdatesPage } from "./UpdatesPage";

export { ROUTE_PATH };

// Tabs are grouped by module so later modules (Advisor, Replication, Installer, Desktop) add
// their own entries here without touching the Saves tabs (build prompt v2 section 10, slice 9).
type Module = "saves" | "core" | "installer" | "advisor";

interface Tab {
  module: Module;
  title: string;
  icon: ReactElement;
  content: ReactElement;
  path: string;
}

const TABS: Tab[] = [
  { module: "saves", title: "Games", icon: <FaGamepad />, content: <GamesPage />, path: "games" },
  { module: "saves", title: "Conflicts", icon: <FaCodeBranch />, content: <ConflictsPage />, path: "conflicts" },
  { module: "saves", title: "History", icon: <FaHistory />, content: <HistoryPage />, path: "history" },
  { module: "saves", title: "Import saves", icon: <FaFileImport />, content: <ImportPage />, path: "import" },
  { module: "advisor", title: "Advisor", icon: <FaLightbulb />, content: <AdvisorPage />, path: "advisor" },
  { module: "installer", title: "Install", icon: <FaCompactDisc />, content: <InstallerPage />, path: "install" },
  { module: "core", title: "Settings", icon: <FaCog />, content: <SettingsPage />, path: "settings" },
  { module: "core", title: "Updates", icon: <FaCloudDownloadAlt />, content: <UpdatesPage />, path: "updates" },
  { module: "saves", title: "Activity", icon: <FaStream />, content: <ActivityPage />, path: "activity" },
  { module: "core", title: "Storage", icon: <FaHdd />, content: <StoragePage />, path: "storage" },
  { module: "core", title: "Logs", icon: <FaClipboardList />, content: <LogsPage />, path: "logs" },
  { module: "core", title: "Diagnostics", icon: <FaStethoscope />, content: <DiagnosticsPage />, path: "diagnostics" },
];

export function KeepsakeRoute() {
  // A module's tabs appear only while it runs (v2 spec 7.3: a disabled module has no UI).
  const [running, setRunning] = useState<Set<string>>(new Set(["saves"]));
  useEffect(() => {
    modulesStatus()
      .then((s) => setRunning(new Set(s.modules.filter((m) => m.running).map((m) => m.name))))
      .catch(() => undefined);
  }, []);
  const tabs = TABS.filter((t) => t.module === "core" || running.has(t.module));
  return (
    <div style={{ marginTop: 40, height: "calc(100% - 40px)" }}>
      <SidebarNavigation
        title="Keepsake"
        showTitle
        pages={tabs.map((t) => ({ title: t.title, icon: t.icon, content: t.content, route: `${ROUTE_PATH}/${t.path}` }))}
      />
    </div>
  );
}
