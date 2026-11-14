// Slice 1 probes: record what the Steam client actually reports, so ADR-0001
// is based on real payloads rather than guesses. Every listener is wrapped so a
// missing or renamed client API never breaks the plugin.
import { recordProbeEvent } from "./backend";

type Unregister = () => void;

// Copy primitive own properties only. Steam client objects are large and can
// hold cycles, so never serialise them whole.
export function primitiveSnapshot(value: unknown, maxKeys = 80): Record<string, unknown> | null {
  if (value === null || value === undefined || typeof value !== "object") return null;
  const out: Record<string, unknown> = {};
  let count = 0;
  for (const key of Object.keys(value as object)) {
    if (count >= maxKeys) break;
    let item: unknown;
    try {
      item = (value as Record<string, unknown>)[key];
    } catch {
      continue;
    }
    if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
      out[key] = item;
      count += 1;
    }
  }
  return out;
}

export function runningAppDetails(): Record<string, unknown> {
  try {
    const main = SteamUIStore?.MainRunningApp;
    return {
      mainRunningAppID: SteamUIStore?.MainRunningAppID ?? null,
      mainRunningApp: primitiveSnapshot(main),
      runningAppIDs: (SteamUIStore?.RunningApps ?? []).map((app) => app?.appid),
    };
  } catch (err) {
    return { error: String(err) };
  }
}

function appOverview(appId: number): Record<string, unknown> | null {
  try {
    return primitiveSnapshot(appStore?.GetAppOverviewByAppID(appId));
  } catch {
    return null;
  }
}

function record(kind: string, payload: unknown): void {
  recordProbeEvent(kind, payload).catch(() => undefined);
}

function tryRegister(name: string, register: () => { unregister: () => void } | undefined): Unregister | null {
  try {
    const handle = register();
    if (!handle) {
      record("probe-unavailable", { name });
      return null;
    }
    return () => handle.unregister();
  } catch (err) {
    record("probe-unavailable", { name, error: String(err) });
    return null;
  }
}

export function startProbes(): Unregister {
  const handles: (Unregister | null)[] = [
    tryRegister("GameSessions.RegisterForAppLifetimeNotifications", () =>
      SteamClient.GameSessions.RegisterForAppLifetimeNotifications((n) => {
        record("app-lifetime", {
          notification: primitiveSnapshot(n),
          overview: appOverview(n.unAppID),
          running: runningAppDetails(),
        });
      }),
    ),
    tryRegister("Apps.RegisterForGameActionStart", () =>
      SteamClient.Apps.RegisterForGameActionStart((gameActionId, appId, action, launchSource) => {
        record("game-action-start", {
          gameActionId,
          appId,
          appIdType: typeof appId,
          action,
          launchSource,
          overview: appOverview(Number(appId)),
        });
      }),
    ),
    tryRegister("System.RegisterForOnSuspendRequest", () =>
      SteamClient.System.RegisterForOnSuspendRequest(() => record("suspend-request", {})),
    ),
    tryRegister("System.RegisterForOnResumeFromSuspend", () =>
      SteamClient.System.RegisterForOnResumeFromSuspend(() => record("resume-from-suspend", {})),
    ),
  ];
  return () => {
    for (const unregister of handles) {
      try {
        unregister?.();
      } catch {
        // Ignore: the client may already have dropped the listener.
      }
    }
  };
}

// Which install or update hand-off routes are visible to a plugin. Read only:
// nothing here installs anything.
export function deckyMechanisms(): Record<string, unknown> {
  const w = window as unknown as {
    DeckyBackend?: { call?: unknown; callable?: unknown };
    DeckyPluginLoader?: object;
  };
  let loaderMethods: string[] = [];
  try {
    const loader = w.DeckyPluginLoader;
    if (loader) {
      const proto = Object.getPrototypeOf(loader) as object;
      loaderMethods = Object.getOwnPropertyNames(proto).filter((name) => /install|update|plugin|reload/i.test(name));
    }
  } catch {
    loaderMethods = [];
  }
  return {
    deckyBackendCall: typeof w.DeckyBackend?.call,
    deckyBackendCallable: typeof w.DeckyBackend?.callable,
    deckyPluginLoader: typeof w.DeckyPluginLoader,
    deckyPluginLoaderMethods: loaderMethods,
  };
}
