// Uninstall (ADR-0065). Steam games: an optional final backup, then Steam's own uninstall wizard. Non-Steam
// games: a confirmation screen listing every folder that will be deleted, with sizes and free space after,
// Cancel focused first; then the final backup, the shortcut and its artwork through Steam, the folders, and
// Keepsake's own records, in the background with progress and Stop.
import { DialogButton, Field, Focusable, ModalRoot, ToggleField, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { UninstallJob, UninstallPlan, uninstallCancel, uninstallPlan, uninstallStart, uninstallStatus, uninstallSteam } from "../backend";
import { plainError, sizeText } from "../format";

const STATES: Record<string, string> = {
  starting: "Starting",
  "backing-up": "Saving a final backup",
  "removing-shortcut": "Removing the shortcut from Steam",
  deleting: "Deleting folders",
  cleaning: "Tidying Keepsake's records",
  done: "Uninstalled",
  failed: "Stopped",
  cancelled: "Stopped",
};

function storeText(store: string | undefined): string {
  return store === "direct" ? "your other devices" : store === "local" ? "this device's test store" : "the cloud";
}

function ConfirmModal({ plan, closeModal, onStarted }: { plan: UninstallPlan; closeModal?: () => void; onStarted: () => void }) {
  const [skipBackup, setSkipBackup] = useState(false);
  const [busy, setBusy] = useState(false);
  const total = plan.folders.reduce((sum, f) => sum + f.size, 0);
  const go = async () => {
    setBusy(true);
    try {
      if (plan.steam) {
        await uninstallSteam(plan.key, !skipBackup);
        toaster.toast({ title: "Keepsake", body: "Steam's uninstall is open. Confirm it there." });
      } else {
        await uninstallStart(plan.key, skipBackup);
        onStarted();
      }
      closeModal?.();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <Field
        label={`Uninstall ${plan.name}?`}
        description={
          plan.steam
            ? "Steam removes the game itself: its install folder and library entry. Keepsake deletes nothing."
            : `These folders will be deleted from this device (${sizeText(total)}). The shortcut and its artwork are removed from Steam.`
        }
      />
      {plan.folders.map((f) => (
        <Field
          key={f.path}
          label={f.kind === "prefix" ? "Proton prefix" : "Game folder"}
          description={`${f.path}, ${sizeText(f.size)}. Free space after: ${sizeText(f.freeAfter)}.`}
        />
      ))}
      {plan.kept.map((k) => (
        <Field key={k.path} label="Not deleted" description={`${k.path}: ${k.reason}.`} />
      ))}
      {plan.synced ? (
        <>
          <Field
            label="Final backup"
            description={`Your saves are backed up to ${storeText(plan.store)} first. To get them back, open the game's History on any device that syncs with it, or reinstall the game and sync.`}
          />
          <ToggleField label="Uninstall without a final backup" checked={skipBackup} onChange={setSkipBackup} />
        </>
      ) : (
        <Field label="Saves" description="This game is not synced, so no backup is taken. Its saves inside the deleted folders are lost." />
      )}
      <Focusable style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Focusable autoFocus>
          <DialogButton style={{ width: "auto" }} onClick={closeModal}>
            Cancel
          </DialogButton>
        </Focusable>
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void go()}>
          {plan.steam ? "Open Steam's uninstall" : "Uninstall"}
        </DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

export function UninstallPanel({ gameKey, onGone }: { gameKey: string; onGone: () => void }) {
  const [job, setJob] = useState<UninstallJob | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const now = await uninstallStatus().catch(() => null);
      if (!alive) return;
      setJob(now && now.key === gameKey ? now : null);
      if (now && now.key === gameKey && now.state === "done") onGone();
    };
    void tick();
    const timer = setInterval(() => void tick(), 1000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [gameKey]);
  const open = async () => {
    try {
      const plan = await uninstallPlan(gameKey);
      showModal(<ConfirmModal plan={plan} onStarted={() => void uninstallStatus().then(setJob)} />);
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    }
  };
  const running = job && !["done", "failed", "cancelled"].includes(job.state);
  return (
    <Field
      label="Uninstall"
      description={
        job
          ? `${STATES[job.state] ?? job.state}${job.total ? `: ${sizeText(job.done)} of ${sizeText(job.total)}` : ""}.${job.error ? ` ${job.error}.` : ""}${job.restoreFrom ? ` Restore the saves from ${job.restoreFrom}.` : ""}`
          : "Remove this game from this device."
      }
      childrenLayout="inline"
    >
      {running ? (
        <DialogButton style={{ width: "auto" }} onClick={() => void uninstallCancel().then(setJob)}>
          Stop
        </DialogButton>
      ) : (
        <DialogButton style={{ width: "auto" }} onClick={() => void open()}>
          Uninstall
        </DialogButton>
      )}
    </Field>
  );
}
