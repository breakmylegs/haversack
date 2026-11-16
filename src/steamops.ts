// Steam Operations Executor (v2 spec 7.2, P15, ADR-0015): the backend queues Steam-side changes and this
// frontend, the only place SteamClient exists, applies them. Every change stores the original value first,
// waits for Steam (setters called too soon after AddShortcut are ignored, A71), reads the field back and
// reports. Field names are verified in @decky/ui 4.16.5 types (App.d.ts AppDetails); behaviour is unverified
// on device (A70 to A76). Operations only exist after an explicit user action in the backend.
import { addEventListener, removeEventListener } from "@decky/api";
import { steamOpsClaim, steamOpsFinish, SteamOp } from "./backend";

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

async function execute(op: SteamOp): Promise<Outcome> {
  const appid = Number(op.payload.appid);
  const value = String(op.payload.value ?? "");
  switch (op.kind) {
    case "probe":
      return { ok: true, result: probe() };
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
