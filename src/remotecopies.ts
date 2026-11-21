// Games you can stream from another device (ADR-0064): Steam Remote Play lists the games installed on the
// account's other running devices, with Stream instead of Play. This reads Steam's own view of each
// shortcut, read only, and reports it to the backend:
// - appStore.m_mapApps, IAppOverview.BIsShortcut() and GetPerClientData("local") (installed here?);
// - SteamAppOverview.per_client_data (which other clients have it, by client name);
// - collectionStore.BIsHidden(app).
// All verified in @decky/ui 4.16.5 types (stores/appstore.d.ts, stores/collectionstore.d.ts, App.d.ts);
// their values for a remote copy are unverified on a device (A199, A200).
import { remoteCopiesReport, RemoteCopyReport } from "./backend";

type Overview = {
  appid: number;
  display_name: string;
  per_client_data?: { clientid: string; client_name: string; installed?: boolean }[];
  local_per_client_data?: { clientid: string; installed?: boolean };
  BIsShortcut?: () => boolean;
  GetPerClientData?: (which: "local" | "mostavailable" | "selected") => { clientid: string; installed?: boolean };
};

const SHORTCUT_TYPE = 1073741824; // EAppType.Shortcut

/** Steam's verdict on one shortcut: installed on this client, only on others, or not clear. */
export function verdict(app: Overview): Pick<RemoteCopyReport, "steam" | "clients"> {
  const local = app.GetPerClientData?.("local") ?? app.local_per_client_data;
  const others = (app.per_client_data ?? []).filter((c) => c.installed && (!local || c.clientid !== local.clientid));
  const clients = others.map((c) => c.client_name).filter(Boolean);
  if (local?.installed === true) return { steam: "local", clients };
  if (local && local.installed === false && others.length > 0) return { steam: "remote", clients };
  return { steam: "unsure", clients };
}

export function readShortcuts(): RemoteCopyReport[] {
  const apps = (appStore as unknown as { m_mapApps?: Map<number, Overview & { app_type?: number }> })?.m_mapApps;
  if (!apps) return [];
  const out: RemoteCopyReport[] = [];
  for (const app of apps.values()) {
    const shortcut = typeof app.BIsShortcut === "function" ? app.BIsShortcut() : app.app_type === SHORTCUT_TYPE;
    if (!shortcut) continue;
    out.push({
      appid: app.appid,
      name: app.display_name ?? "",
      ...verdict(app),
      hidden: Boolean(collectionStore?.BIsHidden?.(app.appid)),
    });
  }
  return out;
}

/** Report now; returns what the backend found (newly hidden local shortcuts, copies tidied). */
export async function reportRemoteCopies() {
  return remoteCopiesReport(readShortcuts());
}

/** Report at start, then every five minutes: the copies follow the other devices' Steam sessions. */
export function startRemoteCopies(): () => void {
  const tick = () => void reportRemoteCopies().catch(() => undefined);
  const first = setTimeout(tick, 15_000); // after Steam has loaded its library
  const timer = setInterval(tick, 5 * 60_000);
  return () => {
    clearTimeout(first);
    clearInterval(timer);
  };
}
