// Forward Steam game start and exit to the backend, which runs the launch gate and the exit save.
// The backend normalises any ID shape (32-bit, signed, or 64-bit shortcut game ID) and ignores
// games that are not synced, so every event can be forwarded as is (ADR-0001).
import { advisorPerfSample, onGameEvent, onResume, onSuspend } from "./backend";

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
  try {
    // Slice 11: provisional snapshots of running games when the device sleeps (if enabled in Settings).
    handles.push(SteamClient.System.RegisterForOnSuspendRequest(() => onSuspend().catch(() => undefined)));
  } catch {
    // Missing in this Steam client.
  }
  try {
    // Advisor sessions (ADR-0069): sampling pauses while the device sleeps and carries on after.
    handles.push(SteamClient.System.RegisterForOnResumeFromSuspend(() => onResume().catch(() => undefined)));
  } catch {
    // Missing in this Steam client.
  }
  try {
    // Advisor sessions: the frame rate Steam's own performance overlay reports, read only, at most once a
    // second and only while a game runs (SteamClient.System.Perf in @decky/ui 4.16.5; its entries, A211).
    let last = 0;
    handles.push(
      SteamClient.System.Perf.RegisterForDiagnosticInfoChanges((data: ArrayBuffer) => {
        const now = Date.now();
        if (now - last < 1000 || !SteamUIStore?.MainRunningAppID) return;
        last = now;
        let binary = "";
        for (const byte of new Uint8Array(data).subarray(0, 32768)) binary += String.fromCharCode(byte);
        advisorPerfSample(btoa(binary)).catch(() => undefined);
      }),
    );
  } catch {
    // Missing in this Steam client: sessions record everything but the frame rate.
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
