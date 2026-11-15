import { ConfirmModal, DialogButton, Field, Focusable, showModal, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { HeadSummary, resolveConflict, SyncStatus, syncPull, syncPush, syncStatus, updateGameConfig } from "../backend";

function sizeText(bytes: number): string {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function headText(h: HeadSummary): string {
  return `${h.device ?? "Unknown device"}, ${(h.created ?? "").replace("T", " ").replace("Z", "")}, ${h.files} files, ${sizeText(h.bytes)}`;
}

const CONFLICT_TEXT = {
  adoption: "This device has save files that differ from the cloud, and they have never been synced.",
  fork: "Two devices saved different progress from the same starting point.",
  "both-changed": "This device and the cloud both have new progress.",
};

export function SyncPanel({ gameKey, enabled, onEnabled }: { gameKey: string; enabled: boolean; onEnabled: (on: boolean) => void }) {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => setStatus(await syncStatus(gameKey));

  useEffect(() => {
    void refresh();
  }, [gameKey]);

  const act = async (work: () => Promise<string>) => {
    setBusy(true);
    try {
      toaster.toast({ title: "Keepsake", body: await work() });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  const choose = (choice: string, head: string | null, title: string, description: string) =>
    showModal(
      <ConfirmModal
        strTitle={title}
        strDescription={description}
        strOKButtonText="Continue"
        strCancelButtonText="Decide later"
        onOK={() => void act(async () => (await resolveConflict(gameKey, choice, head), "Conflict resolved."))}
      />,
    );

  if (status && !status.available) return <Field label="Sync" description={status.reason} />;

  const conflict = status?.conflict;

  return (
    <div>
      <ToggleField
        label="Sync this game"
        description="Keep this game's saves in step between your devices."
        checked={enabled}
        onChange={(on) => void updateGameConfig(gameKey, { enabled: on }).then(() => onEnabled(on))}
      />
      <Field
        label="Sync status"
        description={[
          status?.base ? `Based on ${status.base}` : "Not synced yet",
          status?.pending ? "waiting for the cloud" : "",
          status?.sessionOpen ? "game session open" : "",
          status?.quarantined ? `a snapshot was quarantined (${status.quarantined})` : "",
        ]
          .filter(Boolean)
          .join(". ")}
      />
      <Focusable style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() => void act(async () => `Check before play: ${JSON.stringify(await syncPull(gameKey))}`)}
        >
          Check before play
        </DialogButton>
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() => void act(async () => `Save after play: ${JSON.stringify(await syncPush(gameKey))}`)}
        >
          Save after play
        </DialogButton>
      </Focusable>

      {conflict && (
        <>
          <Field label="Conflict" description={`${CONFLICT_TEXT[conflict.kind]} This device has ${conflict.localFiles} files. Whichever you do not choose is kept.`} />
          {conflict.heads.map((h) => (
            <Field key={h.snapId} label={`Cloud: ${headText(h)}`} childrenLayout="below">
              <DialogButton
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() =>
                  choose("use-cloud", h.snapId, "Use this cloud save?", "This device's current files are uploaded and pinned first, then replaced with this save. Quit the game first.")
                }
              >
                Use cloud save
              </DialogButton>
            </Field>
          ))}
          <Focusable style={{ display: "flex", gap: 8 }}>
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy}
              onClick={() =>
                choose("use-local", null, "Use this device's save?", "This device's files become the newest save everywhere. The cloud saves are pinned for at least 90 days.")
              }
            >
              Use this device's save
            </DialogButton>
            <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(async () => "You can decide later. Automatic pulls stay off for this game.")}>
              Decide later
            </DialogButton>
          </Focusable>
        </>
      )}
    </div>
  );
}
