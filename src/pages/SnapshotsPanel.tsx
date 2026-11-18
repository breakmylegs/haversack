import { ConfirmModal, DialogButton, Field, Focusable, ToggleField, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  listSnapshots,
  pinSnapshot,
  releaseQuarantine,
  repairSnapshot,
  RestoreChange,
  restorePreview,
  restoreSnapshot,
  runRetention,
  snapshotGame,
  SnapshotListing,
  SnapshotSummary,
  undoRestore,
} from "../backend";
import { kindText } from "../format";
import { openCheckpointModal } from "./CheckpointModal";

const ACTION_WORD = { create: "would come back", replace: "would be replaced", delete: "would be removed" } as const;

function sizeText(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function describe(s: SnapshotSummary): string {
  const flags = [s.base ? "current base" : "", s.pinned ? "pinned" : "", s.pruned ? "files pruned" : ""].filter(Boolean);
  return `${s.created.replace("T", " ").replace("Z", "")}, ${kindText(s.kind)}, ${s.device ?? "unknown device"}, ${s.files} files, ${sizeText(s.bytes)}${flags.length ? `. ${flags.join(", ")}` : ""}`;
}

// History for one game: restore, pin, release quarantine and undo, plus the last sync per device.
export function SnapshotsPanel({ gameKey, gameName }: { gameKey: string; gameName?: string }) {
  const [listing, setListing] = useState<SnapshotListing | null>(null);
  const [busy, setBusy] = useState(false);
  // Partial restore (ADR-0048): the preview of one snapshot, and the files chosen from it.
  const [preview, setPreview] = useState<{ snapId: string; changes: RestoreChange[] } | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const pathOf = (c: RestoreChange) => `${c.root}/${c.rel}`;

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

  const openPreview = (snapId: string) =>
    void act(async () => {
      const result = await restorePreview(gameKey, snapId);
      setPreview(result);
      setChosen(new Set());
      return result.changes.length ? "Choose the files to restore." : "This snapshot matches the files here.";
    });

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
      {(listing?.damaged ?? []).length > 0 && (
        <Field
          label={`${listing?.damaged?.length} snapshots are damaged in the cloud`}
          description="The weekly check found their files damaged or missing, so they cannot be restored. Your current save is fine. Repair saves a fresh copy of it from this device."
          childrenLayout="below"
        >
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const r = await repairSnapshot(gameKey);
                return r.status === "published" ? "A fresh copy is saved." : `Not repaired: ${r.status}`;
              })
            }
          >
            Repair
          </DialogButton>
        </Field>
      )}
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
          onClick={() => openCheckpointModal(gameKey, gameName ?? "this game", () => void refresh())}
        >
          Save checkpoint
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

      {preview && preview.changes.length > 0 && (
        <Field
          label="Restore some files"
          description="Only the files you choose change. Your current files are saved first, so this can be undone."
          childrenLayout="below"
        >
          {preview.changes.map((c) => (
            <ToggleField
              key={pathOf(c)}
              label={c.rel}
              description={ACTION_WORD[c.action]}
              checked={chosen.has(pathOf(c))}
              onChange={(on) => {
                const next = new Set(chosen);
                if (on) next.add(pathOf(c));
                else next.delete(pathOf(c));
                setChosen(next);
              }}
            />
          ))}
          <Focusable style={{ display: "flex", gap: 8 }}>
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy || chosen.size === 0}
              onClick={() =>
                confirm(
                  `Restore ${chosen.size} file${chosen.size === 1 ? "" : "s"}?`,
                  "Quit the game first. Your current files are saved first and can be put back with Undo.",
                  "Restore",
                  async () => {
                    await restoreSnapshot(gameKey, preview.snapId, [...chosen]);
                    setPreview(null);
                    return "Files restored.";
                  },
                )
              }
            >
              Restore chosen files
            </DialogButton>
            <DialogButton style={{ width: "auto" }} onClick={() => setPreview(null)}>
              Cancel
            </DialogButton>
          </Focusable>
        </Field>
      )}

      {(listing?.snapshots ?? []).map((s) => (
        <Field key={s.snapId} label={s.label ? `Checkpoint: ${s.label}` : s.snapId} description={describe(s)} childrenLayout="below">
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
            <DialogButton style={{ width: "auto" }} disabled={busy || s.pruned} onClick={() => openPreview(s.snapId)}>
              Restore some files
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
