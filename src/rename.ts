// Keepsake becomes Haversack (ADR-0089). While the old Keepsake plugin is installed, the backend starts
// nothing and the quick menu shows one card. After the user confirms, the old plugin (and the old helper)
// are removed through Decky's own route "utilities/uninstall_plugin", then the backend copies the data
// across, checks it and starts. The background services start only once the backend has started.
import { renameFinish, renameStatus, RenameStatus } from "./backend";

export const OLD_NAME = "Keepsake";
export const OLD_HELPER = "Keepsake Helper";

type Listener = (status: RenameStatus) => void;

let current: RenameStatus | null = null;
let onStart: (() => void) | null = null;
const listeners = new Set<Listener>();

function publish(status: RenameStatus) {
  current = status;
  if (status.started) onStart?.();
  listeners.forEach((l) => l(status));
}

/** Ask the backend until it has started, or is held for the user, or has failed; then call ``start``. */
export function watchRename(start: () => void): () => void {
  onStart = start;
  let live = true;
  let tries = 0;
  let timer: number | undefined;
  const again = () => {
    if (live && ++tries < 60) timer = window.setTimeout(poll, 2000);
  };
  const poll = () =>
    renameStatus()
      .then((s) => {
        if (!live) return;
        publish(s);
        if (!s.started && !s.hold && !s.error) again(); // still starting
      })
      .catch(again);
  void poll();
  return () => {
    live = false;
    window.clearTimeout(timer);
    onStart = null;
  };
}

export function renameState(): RenameStatus | null {
  return current;
}

export function onRename(listener: Listener): () => void {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

interface DeckyBackendLike {
  call?: (route: string, ...args: unknown[]) => Promise<unknown>;
}

export function canRemoveOld(): boolean {
  return typeof (window as unknown as { DeckyBackend?: DeckyBackendLike }).DeckyBackend?.call === "function";
}

/** Remove the old plugins the user confirmed, then let the backend copy the data and start. */
export async function removeOldAndFinish(status: RenameStatus): Promise<RenameStatus> {
  const backend = (window as unknown as { DeckyBackend?: DeckyBackendLike }).DeckyBackend;
  if (typeof backend?.call === "function") {
    for (const [installed, name] of [
      [status.oldInstalled, OLD_NAME],
      [status.oldHelper, OLD_HELPER],
    ] as const) {
      if (!installed) continue;
      try {
        await backend.call("utilities/uninstall_plugin", name);
      } catch {
        // Checked again by the backend: Haversack stays held if Keepsake is still there.
      }
    }
  }
  const after = await renameFinish();
  publish(after);
  return after;
}
