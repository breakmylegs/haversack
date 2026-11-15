import { ButtonItem, Navigation, PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { addEventListener, definePlugin, removeEventListener, routerHook, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaSave } from "react-icons/fa";
import { checkForUpdates, getStatus, qamSummary, QamSummary, syncNow, takeStartupNotice, UpdateStatus } from "./backend";
import { agoText, BACKEND_LABELS, HEALTH_COLOURS, HEALTH_LABELS, SYNC_LABELS } from "./format";
import { startLifecycle } from "./lifecycle";
import { startProbes } from "./probes";
import { KeepsakeRoute } from "./pages/KeepsakeRoute";
import { SetupWizard } from "./pages/SetupWizard";
import { ROUTE_PATH, SETUP_PATH } from "./routes";

function openRoute(path: string) {
  Navigation.Navigate(path);
  Navigation.CloseSideMenus();
}

function storeText(s: QamSummary): string {
  if (s.store === "local") return "Test store on this device";
  return s.signedIn ? BACKEND_LABELS[s.store] : `${BACKEND_LABELS[s.store]}, not set up`;
}

function Content() {
  const [summary, setSummary] = useState<QamSummary | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState<string | null>(null);
  const [safeMode, setSafeMode] = useState(false);
  const [update, setUpdate] = useState<UpdateStatus | null>(null);
  const [syncing, setSyncing] = useState(false);

  const refresh = () =>
    qamSummary()
      .then((s) => {
        setSummary(s);
        setFailed(false);
      })
      .catch(() => setFailed(true));

  useEffect(() => {
    void refresh();
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

  const runSync = async () => {
    setSyncing(true);
    try {
      const result = await syncNow();
      const body = result.ok
        ? `Checked ${result.games ?? 0} games.`
        : "Keepsake is busy with another job. Try again in a moment.";
      toaster.toast({ title: "Keepsake", body });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Sync failed: ${err}` });
    } finally {
      setSyncing(false);
      void refresh();
    }
  };

  return (
    <PanelSection title="Status">
      <PanelSectionRow>
        <div style={{ fontSize: 12 }}>
          {failed && "Backend not responding."}
          {!failed && !summary && "Loading"}
          {summary && (
            <>
              <span style={{ color: HEALTH_COLOURS[summary.health] }}>{"●"} </span>
              {HEALTH_LABELS[summary.health]}
              {`  |  ${storeText(summary)}  |  Last sync ${agoText(summary.lastSync)}`}
              {version ? `  |  v${version}` : ""}
            </>
          )}
        </div>
      </PanelSectionRow>
      {summary && summary.problems.length > 0 && (
        <PanelSectionRow>
          <div style={{ fontSize: 12 }}>Check: {summary.problems.slice(0, 3).join(", ")}</div>
        </PanelSectionRow>
      )}
      {summary && !summary.setupComplete && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => openRoute(SETUP_PATH)}>
            Set up Keepsake
          </ButtonItem>
        </PanelSectionRow>
      )}
      {summary?.currentGame && (
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            description={SYNC_LABELS[summary.currentGame.status]}
            onClick={() => openRoute(`${ROUTE_PATH}/games`)}
          >
            Playing: {summary.currentGame.name}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {summary && summary.conflicts > 0 && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => openRoute(`${ROUTE_PATH}/conflicts`)}>
            {summary.conflicts === 1 ? "1 conflict needs your choice" : `${summary.conflicts} conflicts need your choice`}
          </ButtonItem>
        </PanelSectionRow>
      )}
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
        <ButtonItem
          layout="below"
          disabled={syncing || !summary || summary.enabledGames === 0 || Boolean(summary.busy)}
          onClick={() => void runSync()}
        >
          {syncing ? "Syncing" : "Sync now"}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => openRoute(`${ROUTE_PATH}/games`)}>
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
  routerHook.addRoute(SETUP_PATH, SetupWizard);
  const stopProbes = startProbes();
  const stopLifecycle = startLifecycle();
  // Messages from the backend, such as "Recovered missed exit backup for <game>".
  const toastListener = addEventListener<[string]>("keepsake_toast", (body) =>
    toaster.toast({ title: "Keepsake", body }),
  );
  void announce();

  return {
    name: "Keepsake",
    titleView: <div className={staticClasses.Title}>Keepsake</div>,
    content: <Content />,
    icon: <FaSave />,
    onDismount() {
      stopProbes();
      stopLifecycle();
      removeEventListener("keepsake_toast", toastListener);
      routerHook.removeRoute(ROUTE_PATH);
      routerHook.removeRoute(SETUP_PATH);
    },
  };
});
