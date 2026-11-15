import { ConfirmModal, DialogButton, Field, Focusable, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  listSnapshots,
  pinSnapshot,
  releaseQuarantine,
  restoreSnapshot,
  runRetention,
  snapshotGame,
  SnapshotListing,
  SnapshotSummary,
  undoRestore,
} from "../backend";

function sizeText(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function describe(s: SnapshotSummary): string {
  const flags = [s.base ? "current base" : "", s.pinned ? "pinned" : "", s.pruned ? "files pruned" : ""].filter(Boolean);
  return `${s.created.replace("T", " ").replace("Z", "")}, ${s.kind}, ${s.device ?? "unknown device"}, ${s.files} files, ${sizeText(s.bytes)}${flags.length ? `. ${flags.join(", ")}` : ""}`;
}

// History for one game: restore, pin, release quarantine and undo, plus the last sync per device.
export function SnapshotsPanel({ gameKey }: { gameKey: string }) {
  const [listing, setListing] = useState<SnapshotListing | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      setListing(await listSnapshots(gameKey));
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Could not list snapshots: ${err}` });
    }
  };

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
        label="History"
        description="Snapshots of this game's saves, newest first. Every restore first saves the current files so it can be undone."
      />
      {(listing?.lastByDevice ?? []).length > 0 && (
        <Field
          focusable
          label="Last sync per device"
          description={(listing?.lastByDevice ?? [])
            .map((d) => `${d.device ?? "Unknown device"}: ${d.created.replace("T", " ").replace("Z", "")} (${d.kind})`)
            .join("; ")}
        />
      )}
      <Focusable style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() =>
            void act(async () => {
              const r = await snapshotGame(gameKey);
              if (r.status === "quarantined") return `Snapshot refused and quarantined: ${(r.reasons ?? []).join("; ")}`;
              if (r.status === "no-change") return "Nothing changed since the last snapshot.";
              if (r.status === "nothing-to-save") return "No save files found.";
              return "Snapshot saved.";
            })
          }
        >
          Take snapshot
        </DialogButton>
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() =>
            void act(async () => {
              const r = await runRetention(gameKey);
              return `Retention kept ${r.kept} and pruned ${r.pruned.length} snapshots.`;
            })
          }
        >
          Run retention
        </DialogButton>
      </Focusable>

      {(listing?.snapshots ?? []).map((s) => (
        <Field key={s.snapId} label={s.snapId} description={describe(s)} childrenLayout="below">
          <Focusable style={{ display: "flex", gap: 8 }}>
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy || s.pruned}
              onClick={() =>
                confirm(
                  "Restore this snapshot?",
                  "Quit the game first. Your current save files are saved first and can be put back with Undo.",
                  "Restore",
                  async () => {
                    const r = await restoreSnapshot(gameKey, s.snapId);
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
              onClick={() => void act(async () => (await pinSnapshot(gameKey, s.snapId), "Snapshot pinned. Retention will keep it."))}
            >
              Pin
            </DialogButton>
          </Focusable>
        </Field>
      ))}

      {(listing?.quarantine ?? []).length > 0 && <Field label="Quarantined (not uploaded)" />}
      {(listing?.quarantine ?? []).map((s) => (
        <Field key={s.snapId} label={s.snapId} description={`${describe(s)}. Refused: ${(s.reasons ?? []).join("; ")}`} childrenLayout="below">
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() =>
              confirm(
                "Release this snapshot?",
                `It was refused because: ${(s.reasons ?? []).join("; ")}. Releasing uploads it as the newest snapshot. Only do this if the save really did lose those files.`,
                "Release",
                async () => (await releaseQuarantine(gameKey, s.snapId, true), "Snapshot released."),
              )
            }
          >
            Release
          </DialogButton>
        </Field>
      ))}

      {(listing?.prerestore ?? []).length > 0 && <Field label="Before each restore (this device only)" />}
      {(listing?.prerestore ?? []).map((s) => (
        <Field key={s.snapId} label={s.snapId} description={describe(s)} childrenLayout="below">
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() =>
              confirm("Undo to these files?", "The files from before that restore are put back. Your current files are saved first.", "Undo", async () => {
                await undoRestore(gameKey, s.snapId);
                return "Files put back.";
              })
            }
          >
            Undo to this
          </DialogButton>
        </Field>
      ))}
    </div>
  );
}
