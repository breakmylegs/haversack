import { SidebarNavigation } from "@decky/ui";
import { FaClipboardList, FaCloudDownloadAlt, FaCog, FaGamepad, FaStethoscope } from "react-icons/fa";
import { DiagnosticsPage } from "./DiagnosticsPage";
import { GamesPage } from "./GamesPage";
import { LogsPage } from "./LogsPage";
import { SettingsPage } from "./SettingsPage";
import { UpdatesPage } from "./UpdatesPage";

export const ROUTE_PATH = "/keepsake";

export function KeepsakeRoute() {
  return (
    <div style={{ marginTop: 40, height: "calc(100% - 40px)" }}>
      <SidebarNavigation
        title="Keepsake"
        showTitle
        pages={[
          { title: "Games", icon: <FaGamepad />, content: <GamesPage />, route: `${ROUTE_PATH}/games` },
          { title: "Diagnostics", icon: <FaStethoscope />, content: <DiagnosticsPage />, route: `${ROUTE_PATH}/diagnostics` },
          { title: "Updates", icon: <FaCloudDownloadAlt />, content: <UpdatesPage />, route: `${ROUTE_PATH}/updates` },
          { title: "Logs", icon: <FaClipboardList />, content: <LogsPage />, route: `${ROUTE_PATH}/logs` },
          { title: "Settings", icon: <FaCog />, content: <SettingsPage />, route: `${ROUTE_PATH}/settings` },
        ]}
      />
    </div>
  );
}
