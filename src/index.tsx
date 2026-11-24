import { ButtonItem, ConfirmModal, PanelSection, PanelSectionRow, showModal, staticClasses } from "@decky/ui";
import { addEventListener, definePlugin, removeEventListener, routerHook, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaCompactDisc } from "react-icons/fa";
import {
  checkForUpdates,
  getStatus,
  qamShortcuts,
  QamShortcuts,
  runShortcut,
  Shortcut,
  SHORTCUTS_EVENT,
  takeStartupNotice,
  UpdateStatus,
  replicationAnswer,
  RenameStatus,
} from "./backend";
import { plainError } from "./format";
import { startLifecycle } from "./lifecycle";
import { startSteamOps } from "./steamops";
import { startRemoteCopies } from "./remotecopies";
import { GameTransfersCompact } from "./pages/GameTransfers";
import { openWhatsNew } from "./pages/WhatsNewModal";
import { KeepsakeRoute, LegacyRedirect, SectionRoute } from "./pages/KeepsakeRoute";
import { legacyRoutes, pageRoutes } from "./sidebar";
import { RenameCard } from "./pages/RenameCard";
import { onRename, renameState, watchRename } from "./rename";
import { openSection, ROUTE_PATH, SectionId } from "./routes";

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

// The quick access menu (the strip, ADR-0098): games moving between devices, what needs attention,
// the chosen shortcuts, and Open Haversack. Nothing deeper.
function Content() {
  const [version, setVersion] = useState<string | null>(null);
  const [safeMode, setSafeMode] = useState(false);
  const [update, setUpdate] = useState<UpdateStatus | null>(null);
  const [shortcuts, setShortcuts] = useState<QamShortcuts | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  const loadShortcuts = () =>
    qamShortcuts()
      .then(setShortcuts)
      .catch(() => undefined); // keep what is shown

  useEffect(() => {
    void loadShortcuts();
    const shortcutsListener = addEventListener(SHORTCUTS_EVENT, () => void loadShortcuts());
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

  const attention: { key: string; text: string; open: () => void }[] = [];
  if (safeMode) attention.push({ key: "safe", text: "Safe mode: settings come from a newer version. Please update.", open: () => openSection("settings", "updates") });
  if (update?.updateAvailable && update.latest) {
    attention.push({ key: "update", text: `Update available: v${update.latest.version}`, open: () => openSection("settings", "updates") });
  }

  // The chosen shortcuts, in the user's order (layout v3 addendum, ADR-0073); Open Haversack is always last.
  const runAction = async (s: Shortcut) => {
    if (running) return; // never disable a focused button: ignore a second press
    setRunning(s.id);
    try {
      const r = await runShortcut(s.id);
      toaster.toast({ title: "Haversack", body: r.message });
      if (r.open) openSection(r.open[0] as SectionId, r.open[1]);
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setRunning(null);
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
      return (
        <PanelSectionRow key={s.id}>
          <ButtonItem layout="below" onClick={() => void runAction(s)}>
            {running === s.id ? "Working" : s.label}
          </ButtonItem>
        </PanelSectionRow>
      );
    }
    if (s.id === "status-transfers") return <GameTransfersCompact key={s.id} onOpen={() => openSection("games-devices", "moving")} />;
    return null;
  };

  return (
    <PanelSection title="Haversack">
      {attention.slice(0, 3).map((a) => (
        <PanelSectionRow key={a.key}>
          <ButtonItem layout="below" onClick={a.open}>
            {a.text}
          </ButtonItem>
        </PanelSectionRow>
      ))}
      {(shortcuts?.shown ?? []).map((s) => shortcutItem(s))}
      <PanelSectionRow>
        <ButtonItem layout="below" description={version ? `Version ${version}` : undefined} onClick={() => openSection("install")}>
          Open Haversack
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
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
  // The background services start once the backend has started, never while it is held (ADR-0089).
  let stops: (() => void)[] | null = null;
  const stopWatch = watchRename(() => {
    if (stops) return;
    stops = [startLifecycle(), startSteamOps(), startRemoteCopies()];
    void announce();
  });
  // Messages from the backend, such as a game on its way to the other device.
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
    icon: <FaCompactDisc />,
    onDismount() {
      stopWatch();
      for (const stop of stops ?? []) stop();
      removeEventListener("keepsake_toast", toastListener);
      removeEventListener("keepsake_pair_request", pairListener);
      for (const old of legacy) routerHook.removeRoute(old.path);
      for (const r of pages) routerHook.removeRoute(r.path);
      routerHook.removeRoute(ROUTE_PATH);
    },
  };
});
