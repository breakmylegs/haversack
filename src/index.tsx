import { ButtonItem, Navigation, PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { definePlugin, routerHook, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaSave } from "react-icons/fa";
import { checkForUpdates, getSettings, getStatus, takeStartupNotice, UpdateStatus } from "./backend";
import { startProbes } from "./probes";
import { KeepsakeRoute, ROUTE_PATH } from "./pages/KeepsakeRoute";

function openRoute(path: string) {
  Navigation.Navigate(path);
  Navigation.CloseSideMenus();
}

function Content() {
  const [deviceName, setDeviceName] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [safeMode, setSafeMode] = useState(false);
  const [update, setUpdate] = useState<UpdateStatus | null>(null);

  useEffect(() => {
    getSettings()
      .then((s) => setDeviceName(s.deviceName || "Not set"))
      .catch(() => setDeviceName("Backend not responding"));
    getStatus()
      .then((s) => {
        setVersion(s.version);
        setSafeMode(s.safeMode);
      })
      .catch(() => undefined);
    // Throttled to once a day by the backend.
    checkForUpdates(false)
      .then(setUpdate)
      .catch(() => undefined);
  }, []);

  return (
    <PanelSection title="Status">
      <PanelSectionRow>
        <div style={{ fontSize: 12 }}>
          Device: {deviceName ?? "Loading"}
          {version ? `  |  v${version}` : ""}
        </div>
      </PanelSectionRow>
      {safeMode && (
        <PanelSectionRow>
          <div style={{ fontSize: 12 }}>Safe mode: settings come from a newer version. Please update.</div>
        </PanelSectionRow>
      )}
      {update?.updateAvailable && update.latest && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => openRoute(`${ROUTE_PATH}/updates`)}>
            Update available: v{update.latest.version}
          </ButtonItem>
        </PanelSectionRow>
      )}
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

async function announce() {
  try {
    const notice = await takeStartupNotice();
    if (notice) toaster.toast({ title: "Keepsake", body: `Updated to v${notice.to}` });
    const update = await checkForUpdates(false);
    if (update.notify && update.latest) {
      toaster.toast({ title: "Keepsake", body: `Update available: v${update.latest.version}` });
    }
  } catch {
    // Backend not ready yet; the panel shows the state when opened.
  }
}

export default definePlugin(() => {
  routerHook.addRoute(ROUTE_PATH, KeepsakeRoute);
  const stopProbes = startProbes();
  void announce();

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
