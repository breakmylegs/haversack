import { ButtonItem, ConfirmModal, Navigation, PanelSection, PanelSectionRow, showModal, staticClasses } from "@decky/ui";
import { addEventListener, definePlugin, removeEventListener, routerHook, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaSave } from "react-icons/fa";
import {
  checkForUpdates,
  getStatus,
  qamShortcuts,
  QamShortcuts,
  qamSummary,
  QamSummary,
  runShortcut,
  Shortcut,
  SHORTCUTS_EVENT,
  syncNow,
  takeStartupNotice,
  UpdateStatus,
  replicationAnswer,
  RenameStatus,
} from "./backend";
import { agoText, BACKEND_LABELS, HEALTH_COLOURS, HEALTH_LABELS, newerText, plainError, SYNC_LABELS } from "./format";
import { startLifecycle } from "./lifecycle";
import { startProbes } from "./probes";
import { startSteamOps } from "./steamops";
import { startRemoteCopies } from "./remotecopies";
import { startLibraryBadges } from "./libraryBadges";
import { AdvisorQam } from "./pages/AdvisorQam";
import { GameTransfersCompact } from "./pages/GameTransfers";
import { ReconnectQam } from "./pages/ReconnectQam";
import { BatteryPanel } from "./pages/BatteryPanel";
import { PowerPanel } from "./pages/PowerPanel";
import { openCheckpointModal } from "./pages/CheckpointModal";
import { openWhatsNew } from "./pages/WhatsNewModal";
import { KeepsakeRoute, LegacyRedirect, SectionRoute } from "./pages/KeepsakeRoute";
import { legacyRoutes, pageRoutes } from "./sidebar";
import { SetupWizard } from "./pages/SetupWizard";
import { RenameCard } from "./pages/RenameCard";
import { onRename, renameState, watchRename } from "./rename";
import { openSection, ROUTE_PATH, SectionId, SETUP_PATH } from "./routes";

function openRoute(path: string) {
  Navigation.Navigate(path);
  Navigation.CloseSideMenus();
}

function storeText(s: QamSummary): string {
  if (s.store === "local") return "Test store on this device";
  return s.signedIn ? BACKEND_LABELS[s.store] : `${BACKEND_LABELS[s.store]}, not set up`;
}

// Until the backend has started (ADR-0089: held while the old Keepsake is installed), only the card shows.
function Root() {
  const [rename, setRename] = useState<RenameStatus | null>(renameState());
  useEffect(() => onRename(setRename), []);
  if (rename?.started) return <Content />;
  if (rename) return <RenameCard status={rename} />;
  return (
    <PanelSection title="Haversack">
      <PanelSectionRow>
        <div style={{ fontSize: 12 }}>Starting</div>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Content() {
  const [summary, setSummary] = useState<QamSummary | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState<string | null>(null);
  const [safeMode, setSafeMode] = useState(false);
  const [update, setUpdate] = useState<UpdateStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [shortcuts, setShortcuts] = useState<QamShortcuts | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  const loadShortcuts = () =>
    qamShortcuts()
      .then(setShortcuts)
      .catch(() => undefined); // keep what is shown
  const refresh = () =>
    qamSummary()
      .then((s) => {
        setSummary(s);
        setFailed(false);
      })
      .catch(() => setFailed(true));

  useEffect(() => {
    void loadShortcuts();
    const shortcutsListener = addEventListener(SHORTCUTS_EVENT, () => void loadShortcuts());
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
    return () => {
      removeEventListener(SHORTCUTS_EVENT, shortcutsListener);
    };
  }, []);

  const runSync = async () => {
    setSyncing(true);
    try {
      const result = await syncNow();
      const body = result.ok
        ? `Checked ${result.games ?? 0} games.`
        : "Haversack is busy with another job. Try again in a moment.";
      toaster.toast({ title: "Haversack", body });
    } catch (err) {
      toaster.toast({ title: "Haversack", body: `Sync failed: ${plainError(err)}` });
    } finally {
      setSyncing(false);
      void refresh();
    }
  };

  // Layout v3 (ADR-0073): one screen. Now playing, moving games, at most three things that need
  // attention, then the status line and the two buttons. Nothing deeper.
  const attention: { key: string; text: string; open: () => void }[] = [];
  if (summary && !summary.setupComplete) attention.push({ key: "setup", text: "Set up Haversack", open: () => openRoute(SETUP_PATH) });
  if (safeMode) attention.push({ key: "safe", text: "Safe mode: settings come from a newer version. Please update.", open: () => openSection("settings", "updates") });
  for (const problem of summary?.problems ?? []) attention.push({ key: `p-${problem}`, text: `Check: ${problem}`, open: () => openSection("diagnostics", "health") });
  for (const n of summary?.newer ?? []) attention.push({ key: `n-${n.key}`, text: `${n.name}: ${newerText(n)}`, open: () => openSection("saves", "games") });
  if (update?.updateAvailable && update.latest) {
    attention.push({ key: "update", text: `Update available: v${update.latest.version}`, open: () => openSection("settings", "updates") });
  }

  // The chosen shortcuts, in the user's order (layout v3 addendum, ADR-0073); Open Haversack is always last.
  const runAction = async (s: Shortcut) => {
    if (s.id === "sync-now") return runSync();
    setRunning(s.id);
    try {
      const r = await runShortcut(s.id);
      toaster.toast({ title: "Haversack", body: r.message });
      if (r.open) openSection(r.open[0] as SectionId, r.open[1]);
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setRunning(null);
      void refresh();
    }
  };
  const shortcutItem = (s: Shortcut) => {
    if (s.kind === "page" && s.open) {
      const [section, tab] = s.open;
      return (
        <PanelSectionRow key={s.id}>
          <ButtonItem layout="below" onClick={() => openSection(section as SectionId, tab)}>
            {s.label}
          </ButtonItem>
        </PanelSectionRow>
      );
    }
    if (s.kind === "action") {
      const isSync = s.id === "sync-now";
      return (
        <PanelSectionRow key={s.id}>
          <ButtonItem
            layout="below"
            disabled={isSync ? syncing || !summary || summary.enabledGames === 0 || Boolean(summary.busy) : running !== null}
            onClick={() => void runAction(s)}
          >
            {(isSync && syncing) || running === s.id ? "Working" : s.label}
          </ButtonItem>
        </PanelSectionRow>
      );
    }
    if (s.id === "status-transfers") return <GameTransfersCompact key={s.id} onOpen={() => openSection("games-devices", "moving")} />;
    if (s.id === "status-reconnect") return <ReconnectQam key={s.id} onOpen={() => openSection("device", "controllers")} />;
    if (s.id === "status-conflicts" && summary && summary.conflicts > 0) {
      return (
        <PanelSectionRow key={s.id}>
          <ButtonItem layout="below" onClick={() => openSection("saves", "conflicts")}>
            {summary.conflicts === 1 ? "1 conflict needs your choice" : `${summary.conflicts} conflicts need your choice`}
          </ButtonItem>
        </PanelSectionRow>
      );
    }
    return null;
  };

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
          <PowerPanel compact />
          <AdvisorQam onOpen={() => openSection("play", "advisor")} />
        </PanelSection>
      )}
      <PanelSection title="Haversack">
        <BatteryPanel compact />
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
        {(shortcuts?.shown ?? []).map((s) => shortcutItem(s))}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => openSection(summary?.currentGame ? "play" : "saves")}>
            Open Haversack
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
    else if (notice) toaster.toast({ title: "Haversack", body: `Updated to v${notice.to}` });
    const update = await checkForUpdates(false);
    if (update.notify && update.latest) {
      toaster.toast({ title: "Haversack", body: `Update available: v${update.latest.version}` });
    }
  } catch {
    // Backend not ready yet; the panel shows the state when opened.
  }
}

export default definePlugin(() => {
  // The menu (ADR-0095). Registered most exact first: old addresses redirect to their sub-page; each
  // sub-page's own address opens its section's page with that tab; anything else under /keepsake is
  // the sidebar. Every route is exact and fixed, so none takes a parameter that could be wrong.
  const legacy = legacyRoutes();
  for (const old of legacy) {
    routerHook.addRoute(old.path, () => <LegacyRedirect section={old.section} page={old.page} />, { exact: true });
  }
  const pages = pageRoutes();
  for (const r of pages) {
    routerHook.addRoute(r.path, () => <SectionRoute section={r.section} page={r.page} />, { exact: true });
  }
  routerHook.addRoute(ROUTE_PATH, KeepsakeRoute);
  routerHook.addRoute(SETUP_PATH, SetupWizard);
  // The background services start once the backend has started, never while it is held (ADR-0089).
  let stops: (() => void)[] | null = null;
  const stopWatch = watchRename(() => {
    if (stops) return;
    stops = [startProbes(), startLifecycle(), startSteamOps(), startRemoteCopies(), startLibraryBadges()];
    void announce();
  });
  // Messages from the backend, such as "Recovered missed exit backup for <game>".
  const toastListener = addEventListener<[string]>("keepsake_toast", (body) =>
    toaster.toast({ title: "Haversack", body }),
  );
  // A device asks to pair (ADR-0070): Accept or Decline here, or, while a game runs, only a notification.
  const pairListener = addEventListener<[{ id: string; name: string; address: string }]>("keepsake_pair_request", (request) => {
    if (SteamUIStore?.MainRunningAppID) {
      toaster.toast({ title: "Haversack", body: `${request.name} wants to pair. Answer it in Haversack, Games and devices, Other devices, after your game.` });
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
  return {
    name: "Haversack",
    titleView: <div className={staticClasses.Title}>Haversack</div>,
    content: <Root />,
    icon: <FaSave />,
    onDismount() {
      stopWatch();
      for (const stop of stops ?? []) stop();
      removeEventListener("keepsake_toast", toastListener);
      removeEventListener("keepsake_pair_request", pairListener);
      for (const old of legacy) routerHook.removeRoute(old.path);
      for (const r of pages) routerHook.removeRoute(r.path);
      routerHook.removeRoute(ROUTE_PATH);
      routerHook.removeRoute(SETUP_PATH);
    },
  };
});
