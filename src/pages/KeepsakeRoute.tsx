import { SidebarNavigation } from "@decky/ui";
import { FaClipboardList, FaCog, FaStethoscope } from "react-icons/fa";
import { DiagnosticsPage } from "./DiagnosticsPage";
import { LogsPage } from "./LogsPage";
import { SettingsPage } from "./SettingsPage";

export const ROUTE_PATH = "/keepsake";

export function KeepsakeRoute() {
  return (
    <div style={{ marginTop: 40, height: "calc(100% - 40px)" }}>
      <SidebarNavigation
        title="Keepsake"
        showTitle
        pages={[
          { title: "Diagnostics", icon: <FaStethoscope />, content: <DiagnosticsPage />, route: `${ROUTE_PATH}/diagnostics` },
          { title: "Logs", icon: <FaClipboardList />, content: <LogsPage />, route: `${ROUTE_PATH}/logs` },
          { title: "Settings", icon: <FaCog />, content: <SettingsPage />, route: `${ROUTE_PATH}/settings` },
        ]}
      />
    </div>
  );
}
