import { ButtonItem, ConfirmModal, Navigation, PanelSection, PanelSectionRow, showModal, staticClasses } from "@decky/ui";
import { addEventListener, definePlugin, removeEventListener, routerHook, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaSave } from "react-icons/fa";
import {
  checkForUpdates,
  getStatus,
  qamSummary,
  QamSummary,
  syncNow,
  takeStartupNotice,
  UpdateStatus,
  replicationAnswer,
} from "./backend";
import { agoText, BACKEND_LABELS, HEALTH_COLOURS, HEALTH_LABELS, newerText, plainError, SYNC_LABELS } from "./format";
import { startLifecycle } from "./lifecycle";
import { startProbes } from "./probes";
import { startSteamOps } from "./steamops";
import { startRemoteCopies } from "./remotecopies";
import { AdvisorQam } from "./pages/AdvisorQam";
import { GameTransfersCompact } from "./pages/GameTransfers";
import { openCheckpointModal } from "./pages/CheckpointModal";
import { openWhatsNew } from "./pages/WhatsNewModal";
import { KeepsakeRoute } from "./pages/KeepsakeRoute";
import { SetupWizard } from "./pages/SetupWizard";
import { openSection, ROUTE_PATH, SETUP_PATH } from "./routes";

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
      toaster.toast({ title: "Keepsake", body: `Sync failed: ${plainError(err)}` });
    } finally {
      setSyncing(false);
      void refresh();
    }
  };

  // Layout v3 (ADR-0073): one screen. Now playing, moving games, at most three things that need
  // attention, then the status line and the two buttons. Nothing deeper.
  const attention: { key: string; text: string; open: () => void }[] = [];
  if (summary && !summary.setupComplete) attention.push({ key: "setup", text: "Set up Keepsake", open: () => openRoute(SETUP_PATH) });
  if (summary && summary.conflicts > 0) {
    const text = summary.conflicts === 1 ? "1 conflict needs your choice" : `${summary.conflicts} conflicts need your choice`;
    attention.push({ key: "conflicts", text, open: () => openSection("saves", "conflicts") });
  }
  if (safeMode) attention.push({ key: "safe", text: "Safe mode: settings come from a newer version. Please update.", open: () => openSection("settings", "updates") });
  for (const problem of summary?.problems ?? []) attention.push({ key: `p-${problem}`, text: `Check: ${problem}`, open: () => openSection("diagnostics", "health") });
  for (const n of summary?.newer ?? []) attention.push({ key: `n-${n.key}`, text: `${n.name}: ${newerText(n)}`, open: () => openSection("saves", "games") });
  if (update?.updateAvailable && update.latest) {
    attention.push({ key: "update", text: `Update available: v${update.latest.version}`, open: () => openSection("settings", "updates") });
  }

  return (
    <>
      {summary?.currentGame && (
        <PanelSection title="Now playing">
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              description={SYNC_LABELS[summary.currentGame.status]}
              onClick={() => openSection("play", "now")}
            >
              {summary.currentGame.name}
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => summary.currentGame && openCheckpointModal(summary.currentGame.key, summary.currentGame.name)}
            >
              Save checkpoint
            </ButtonItem>
          </PanelSectionRow>
          <AdvisorQam onOpen={() => openSection("play", "advisor")} />
        </PanelSection>
      )}
      <PanelSection title="Keepsake">
        <GameTransfersCompact onOpen={() => openSection("games", "moving")} />
        {attention.slice(0, 3).map((a) => (
          <PanelSectionRow key={a.key}>
            <ButtonItem layout="below" onClick={a.open}>
              {a.text}
            </ButtonItem>
          </PanelSectionRow>
        ))}
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
          <ButtonItem layout="below" onClick={() => openSection(summary?.currentGame ? "play" : "saves")}>
            Open Keepsake
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

async function announce() {
  try {
    const notice = await takeStartupNotice();
    if (notice?.notes) openWhatsNew(notice.to, notice.notes);
    else if (notice) toaster.toast({ title: "Keepsake", body: `Updated to v${notice.to}` });
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
  const stopSteamOps = startSteamOps();
  const stopRemoteCopies = startRemoteCopies();
  // Messages from the backend, such as "Recovered missed exit backup for <game>".
  const toastListener = addEventListener<[string]>("keepsake_toast", (body) =>
    toaster.toast({ title: "Keepsake", body }),
  );
  // A device asks to pair (ADR-0070): Accept or Decline here, or, while a game runs, only a notification.
  const pairListener = addEventListener<[{ id: string; name: string; address: string }]>("keepsake_pair_request", (request) => {
    if (SteamUIStore?.MainRunningAppID) {
      toaster.toast({ title: "Keepsake", body: `${request.name} wants to pair. Answer it in Keepsake, Devices, after your game.` });
      return;
    }
    showModal(
      <ConfirmModal
        strTitle={`${request.name} wants to pair`}
        strDescription={`From ${request.address}. Accept only if you are pairing your own device right now. This device then shows a code to type on the other one.`}
        strOKButtonText="Accept"
        strCancelButtonText="Decline"
        onOK={() => void replicationAnswer(request.id, true).catch(() => undefined)}
        onCancel={() => void replicationAnswer(request.id, false).catch(() => undefined)}
      />,
    );
  });
  void announce();

  return {
    name: "Keepsake",
    titleView: <div className={staticClasses.Title}>Keepsake</div>,
    content: <Content />,
    icon: <FaSave />,
    onDismount() {
      stopProbes();
      stopLifecycle();
      stopSteamOps();
      stopRemoteCopies();
      removeEventListener("keepsake_toast", toastListener);
      removeEventListener("keepsake_pair_request", pairListener);
      routerHook.removeRoute(ROUTE_PATH);
      routerHook.removeRoute(SETUP_PATH);
    },
  };
});
