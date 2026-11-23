import { ConfirmModal, DialogButton, Field, Focusable, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { HistoryItem, pinSnapshot, recentHistory, releaseQuarantine, restoreSnapshot } from "../backend";
import { isoText, kindText, plainError, sizeText } from "../format";

function describe(s: HistoryItem): string {
  const flags = [
    s.quarantined ? "QUARANTINED, not uploaded" : "",
    s.base ? "current on this device" : "",
    s.pinned ? "pinned" : "",
    s.pruned ? "files pruned" : "",
  ].filter(Boolean);
  return `${isoText(s.created)}, ${kindText(s.kind)}, ${s.device ?? "unknown device"}, ${s.files} files, ${sizeText(s.bytes)}${flags.length ? `. ${flags.join(", ")}` : ""}`;
}

export function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const result = await recentHistory(50);
      setItems(result.snapshots);
      setErrors(result.errors);
    } catch (err) {
      setErrors([String(err)]);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const act = async (work: () => Promise<string>) => {
    setBusy(true);
    try {
      toaster.toast({ title: "Haversack", body: await work() });
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  const confirm = (title: string, description: string, ok: string, work: () => Promise<string>) =>
    showModal(
      <ConfirmModal
        strTitle={title}
        strDescription={description}
        strOKButtonText={ok}
        strCancelButtonText="Cancel"
        onOK={() => void act(work)}
      />,
    );

  return (
    <div>
      <Field
        label="Recent snapshots"
        description="Across every synced game, newest first. Every restore first saves the current files, so it can be undone from the game's page."
      />
      {errors.map((e) => (
        <Field key={e} label="Some history could not be loaded" description={e} />
      ))}
      {items && items.length === 0 && <Field label="No snapshots yet" />}
      {(items ?? []).map((s) => (
        <Field key={`${s.gameKey}/${s.snapId}`} label={s.name} description={describe(s)} childrenLayout="below">
          <Focusable style={{ display: "flex", gap: 8 }}>
            {s.quarantined ? (
              <DialogButton
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() =>
                  confirm(
                    "Release this snapshot?",
                    `It was refused because: ${(s.reasons ?? []).join("; ")}. Releasing uploads it as the newest save. Only do this if the save really did lose those files.`,
                    "Release",
                    async () => (await releaseQuarantine(s.key, s.snapId, true), "Snapshot released."),
                  )
                }
              >
                Release quarantine
              </DialogButton>
            ) : (
              <>
                <DialogButton
                  style={{ width: "auto" }}
                  disabled={busy || s.pruned}
                  onClick={() =>
                    confirm(
                      `Restore ${s.name}?`,
                      "Quit the game first. Your current save files are saved first and can be put back with Undo on the game's page.",
                      "Restore",
                      async () => {
                        const r = await restoreSnapshot(s.key, s.snapId);
                        return r.status === "already-current" ? "These files are already in place." : "Snapshot restored.";
                      },
                    )
                  }
                >
                  Restore
                </DialogButton>
                <DialogButton
                  style={{ width: "auto" }}
                  disabled={busy || s.pinned}
                  onClick={() => void act(async () => (await pinSnapshot(s.key, s.snapId), "Snapshot pinned. Retention will keep it."))}
                >
                  Pin
                </DialogButton>
              </>
            )}
          </Focusable>
        </Field>
      ))}
    </div>
  );
}
