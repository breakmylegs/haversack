import { ButtonItem, Navigation, PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { useEffect, useState } from "react";
import { FaSave } from "react-icons/fa";
import { getSettings } from "./backend";
import { startProbes } from "./probes";
import { KeepsakeRoute, ROUTE_PATH } from "./pages/KeepsakeRoute";

function openRoute(path: string) {
  Navigation.Navigate(path);
  Navigation.CloseSideMenus();
}

function Content() {
  const [deviceName, setDeviceName] = useState<string | null>(null);

  useEffect(() => {
    getSettings()
      .then((s) => setDeviceName(s.deviceName || "Not set"))
      .catch(() => setDeviceName("Backend not responding"));
  }, []);

  return (
    <PanelSection title="Status">
      <PanelSectionRow>
        <div style={{ fontSize: 12 }}>Device: {deviceName ?? "Loading"}</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ fontSize: 12 }}>Sync is not available yet. This build collects diagnostics.</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => openRoute(`${ROUTE_PATH}/diagnostics`)}>
          Open Keepsake
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => {
  routerHook.addRoute(ROUTE_PATH, KeepsakeRoute);
  const stopProbes = startProbes();

  return {
    name: "Keepsake",
    titleView: <div className={staticClasses.Title}>Keepsake</div>,
    content: <Content />,
    icon: <FaSave />,
    onDismount() {
      stopProbes();
      routerHook.removeRoute(ROUTE_PATH);
    },
  };
});
