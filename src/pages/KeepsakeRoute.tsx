import { SidebarNavigation } from "@decky/ui";
import { ReactElement } from "react";
import {
  FaClipboardList,
  FaCloudDownloadAlt,
  FaCodeBranch,
  FaCog,
  FaGamepad,
  FaHistory,
  FaStethoscope,
} from "react-icons/fa";
import { ROUTE_PATH } from "../routes";
import { ConflictsPage } from "./ConflictsPage";
import { DiagnosticsPage } from "./DiagnosticsPage";
import { GamesPage } from "./GamesPage";
import { HistoryPage } from "./HistoryPage";
import { LogsPage } from "./LogsPage";
import { SettingsPage } from "./SettingsPage";
import { UpdatesPage } from "./UpdatesPage";

export { ROUTE_PATH };

// Tabs are grouped by module so later modules (Advisor, Replication, Installer, Desktop) add
// their own entries here without touching the Saves tabs (build prompt v2 section 10, slice 9).
type Module = "saves" | "core";

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
  { module: "core", title: "Settings", icon: <FaCog />, content: <SettingsPage />, path: "settings" },
  { module: "core", title: "Updates", icon: <FaCloudDownloadAlt />, content: <UpdatesPage />, path: "updates" },
  { module: "core", title: "Logs", icon: <FaClipboardList />, content: <LogsPage />, path: "logs" },
  { module: "core", title: "Diagnostics", icon: <FaStethoscope />, content: <DiagnosticsPage />, path: "diagnostics" },
];

export function KeepsakeRoute() {
  return (
    <div style={{ marginTop: 40, height: "calc(100% - 40px)" }}>
      <SidebarNavigation
        title="Keepsake"
        showTitle
        pages={TABS.map((t) => ({ title: t.title, icon: t.icon, content: t.content, route: `${ROUTE_PATH}/${t.path}` }))}
      />
    </div>
  );
}
