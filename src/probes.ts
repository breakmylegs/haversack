// Read-only facts about the Steam client and Decky for Diagnostics. Every read is wrapped so a
// missing or renamed client API never breaks the plugin.
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
