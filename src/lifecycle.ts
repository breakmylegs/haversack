// Forward Steam game start and exit to the backend, which runs the launch gate and the exit save.
// The backend normalises any ID shape (32-bit, signed, or 64-bit shortcut game ID) and ignores
// games that are not synced, so every event can be forwarded as is (ADR-0001).
import { onGameEvent } from "./backend";

type Unregister = () => void;

function forward(kind: "start" | "exit", id: number | string): void {
  onGameEvent(kind, id).catch(() => undefined);
}

export function startLifecycle(): Unregister {
  const handles: { unregister: () => void }[] = [];
  try {
    handles.push(
      SteamClient.GameSessions.RegisterForAppLifetimeNotifications((n) => forward(n.bRunning ? "start" : "exit", n.unAppID)),
    );
  } catch {
    // Missing in this Steam client; the idle pass still saves changes.
  }
  try {
    // Fires before the game's processes exist, so the gate can start polling early.
    handles.push(SteamClient.Apps.RegisterForGameActionStart((_actionId, appId) => forward("start", appId)));
  } catch {
    // Missing in this Steam client.
  }
  return () => {
    for (const handle of handles) {
      try {
        handle.unregister();
      } catch {
        // Already gone.
      }
    }
  };
}
