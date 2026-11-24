// Forward Steam game start and exit to the backend. Moving games waits while a game runs and checks
// a linked game for changes after it exits; Install learns that an installer has finished (ADR-0098).
// The backend normalises any ID shape (32-bit, signed, or 64-bit shortcut game ID), so every event
// can be forwarded as is (ADR-0001).
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
