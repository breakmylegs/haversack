// Steam Operations Executor (v2 spec 7.2, P15, ADR-0015): the backend queues Steam-side changes and this
// frontend, the only place SteamClient exists, applies them. Every change stores the original value first,
// waits for Steam (setters called too soon after AddShortcut are ignored, A71), reads the field back and
// reports. Field names are verified in @decky/ui 4.16.5 types (App.d.ts AppDetails); behaviour is unverified
// on device (A70 to A76). Operations only exist after an explicit user action in the backend.
import { addEventListener, removeEventListener } from "@decky/api";
import { steamOpsClaim, steamOpsFile, steamOpsFinish, SteamOp } from "./backend";

const SETTLE_MS = 600;
const PROBED = {
  Apps: [
    "AddShortcut",
    "RemoveShortcut",
    "SetShortcutName",
    "SetShortcutExe",
    "SetShortcutStartDir",
    "SetShortcutIcon",
    "SetAppLaunchOptions",
    "SpecifyCompatTool",
    "GetAvailableCompatTools",
    "SetCustomArtworkForApp",
  ],
  System: ["RegisterForOnSuspendRequest", "RegisterForOnResumeFromSuspend"],
  GameSessions: ["RegisterForAppLifetimeNotifications"],
};

type Outcome = { ok: boolean; result: Record<string, unknown> };

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function probe(): Record<string, unknown> {
  const client = SteamClient as unknown as Record<string, Record<string, unknown> | undefined>;
  const found: Record<string, boolean> = {};
  for (const [area, names] of Object.entries(PROBED)) {
    for (const name of names) found[`${area}.${name}`] = typeof client[area]?.[name] === "function";
  }
  found.appDetailsStore = typeof appDetailsStore?.GetAppDetails === "function";
  return { functions: found };
}

function details(appid: number) {
  return appDetailsStore?.GetAppDetails(appid) ?? null;
}

async function applyAndReadBack(
  appid: number,
  read: () => string | undefined,
  write: () => void,
  wanted: string,
): Promise<Outcome> {
  const original = read() ?? null;
  write();
  await sleep(SETTLE_MS);
  const readBack = read() ?? null;
  return { ok: readBack === wanted, result: { appid, original, readBack, wanted } };
}

// Creates a shortcut, then sets every field again after Steam settles, because AddShortcut's own
// start dir and launch options may be ignored (A70, A71). The compatibility tool is the newest
// installed GE-Proton, else Proton Experimental (Advisor will recommend one in a later version).
async function addShortcut(op: SteamOp): Promise<Outcome> {
  const { name, exe, startDir, launchOptions, compatTool } = op.payload as Record<string, string>;
  const appid = await SteamClient.Apps.AddShortcut(name, exe, startDir, launchOptions);
  if (!appid) return { ok: false, result: { error: "Steam did not create the shortcut" } };
  await sleep(SETTLE_MS);
  SteamClient.Apps.SetShortcutName(appid, name);
  SteamClient.Apps.SetShortcutExe(appid, exe);
  SteamClient.Apps.SetShortcutStartDir(appid, startDir);
  SteamClient.Apps.SetAppLaunchOptions(appid, launchOptions);
  const tools = (await SteamClient.Apps.GetAvailableCompatTools(appid)).map((t) => t.strToolName);
  // Numeric order, so GE-Proton10-3 is newer than GE-Proton9-27.
  const ge = tools
    .filter((t) => t.startsWith("GE-Proton"))
    .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
  // A game sent from another device asks for the tool it used there (ADR-0059), when Steam has it.
  const wanted = compatTool && tools.includes(compatTool) ? compatTool : undefined;
  const tool = wanted ?? ge[0] ?? (tools.includes("proton_experimental") ? "proton_experimental" : tools[0]);
  if (tool) SteamClient.Apps.SpecifyCompatTool(appid, tool);
  await sleep(SETTLE_MS);
  const d = details(appid);
  const readBack = { name: d?.strDisplayName, exe: d?.strShortcutExe, startDir: d?.strShortcutStartDir, compatTool: d?.strCompatToolName };
  return { ok: true, result: { appid, compatTool: tool ?? null, readBack } };
}

// Removes a shortcut the module itself created (the backend refuses any other). Read back: the app is gone.
async function removeShortcut(appid: number): Promise<Outcome> {
  const before = details(appid)?.strDisplayName ?? null;
  SteamClient.Apps.RemoveShortcut(appid);
  await sleep(SETTLE_MS);
  return { ok: true, result: { appid, original: before, readBack: details(appid)?.strDisplayName ?? null } };
}

// Steam has no getter for custom artwork, so success means SetCustomArtworkForApp resolved (A139).
async function setArtwork(op: SteamOp): Promise<Outcome> {
  const appid = Number(op.payload.appid);
  const assetType = Number(op.payload.assetType);
  const imageType = op.payload.imageType === "jpg" ? "jpg" : "png";
  const { base64 } = await steamOpsFile(op.id);
  await SteamClient.Apps.SetCustomArtworkForApp(appid, base64, imageType, assetType);
  return { ok: true, result: { appid, assetType, readBack: "not available" } };
}

// Hides or shows an app through Steam's hidden collection (ADR-0064): only Steam's copies of other
// devices' shortcuts (backend checks), or a local one the guard shows again. Read back with BIsHidden.
async function setHidden(op: SteamOp): Promise<Outcome> {
  const appid = Number(op.payload.appid);
  const hidden = op.payload.hidden === true;
  const original = collectionStore.BIsHidden(appid);
  collectionStore.SetAppsAsHidden([appid], hidden);
  await sleep(SETTLE_MS);
  const readBack = collectionStore.BIsHidden(appid);
  return { ok: readBack === hidden, result: { appid, original, readBack, wanted: hidden } };
}

async function execute(op: SteamOp): Promise<Outcome> {
  const appid = Number(op.payload.appid);
  const value = String(op.payload.value ?? "");
  switch (op.kind) {
    case "probe":
      return { ok: true, result: probe() };
    case "add-shortcut":
      return addShortcut(op);
    case "remove-shortcut":
      return removeShortcut(appid);
    case "set-artwork":
      return setArtwork(op);
    case "set-hidden":
      return setHidden(op);
    case "set-launch-options":
      return applyAndReadBack(appid, () => details(appid)?.strLaunchOptions, () => SteamClient.Apps.SetAppLaunchOptions(appid, value), value);
    case "set-shortcut-name":
      return applyAndReadBack(appid, () => details(appid)?.strDisplayName, () => SteamClient.Apps.SetShortcutName(appid, value), value);
    case "set-shortcut-exe":
      return applyAndReadBack(appid, () => details(appid)?.strShortcutExe, () => SteamClient.Apps.SetShortcutExe(appid, value), value);
    case "set-shortcut-start-dir":
      return applyAndReadBack(appid, () => details(appid)?.strShortcutStartDir, () => SteamClient.Apps.SetShortcutStartDir(appid, value), value);
    case "set-compat-tool":
      return applyAndReadBack(appid, () => details(appid)?.strCompatToolName, () => SteamClient.Apps.SpecifyCompatTool(appid, value), value);
    default:
      return { ok: false, result: { error: `unknown operation ${op.kind}` } };
  }
}

export function startSteamOps(): () => void {
  let running = false;
  const drain = async () => {
    if (running) return;
    running = true;
    try {
      for (let op = await steamOpsClaim(); op; op = await steamOpsClaim()) {
        let outcome: Outcome;
        try {
          outcome = await execute(op);
        } catch (err) {
          outcome = { ok: false, result: { error: String(err) } };
        }
        await steamOpsFinish(op.id, outcome.ok, outcome.result);
      }
    } catch {
      // Backend not ready or the state database is off; the next event or tick tries again.
    } finally {
      running = false;
    }
  };
  const listener = addEventListener("keepsake_steam_ops", () => void drain());
  const timer = setInterval(() => void drain(), 60_000);
  void drain();
  return () => {
    removeEventListener("keepsake_steam_ops", listener);
    clearInterval(timer);
  };
}
