import { DialogButton, Focusable, ModalRoot, TextField, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { snapshotGame } from "../backend";

// A named checkpoint (ADR-0048): a new snapshot, pinned with its name, kept by retention.
export function openCheckpointModal(gameKey: string, gameName: string, onDone?: () => void) {
  showModal(<CheckpointModal gameKey={gameKey} gameName={gameName} onDone={onDone} />);
}

function defaultName(): string {
  return `Checkpoint ${new Date().toLocaleString([], { dateStyle: "short", timeStyle: "short" })}`;
}

function CheckpointModal({
  gameKey,
  gameName,
  onDone,
  closeModal,
}: {
  gameKey: string;
  gameName: string;
  onDone?: () => void;
  closeModal?: () => void;
}) {
  const [name, setName] = useState(defaultName());
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const result = await snapshotGame(gameKey, name);
      toaster.toast({
        title: "Keepsake",
        body:
          result.status === "published"
            ? `Checkpoint "${name.trim()}" saved for ${gameName}. Find it in History.`
            : result.status === "quarantined"
              ? "The save looks broken, so it was held back. See History."
              : "No save files found for this game.",
      });
      closeModal?.();
      onDone?.();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Checkpoint not saved: ${err}` });
      setBusy(false);
    }
  };

  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal} bCancelDisabled={busy}>
      <div style={{ fontSize: 20, fontWeight: "bold", marginBottom: 8 }}>Save a checkpoint of {gameName}</div>
      <div style={{ marginBottom: 8 }}>
        A copy of the current save, kept until you remove it. Save in the game first, so the checkpoint has your latest progress.
      </div>
      <TextField label="Name" value={name} disabled={busy} onChange={(e) => setName(e.target.value)} />
      <Focusable style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <DialogButton style={{ width: "auto" }} disabled={busy || !name.trim()} onClick={() => void save()}>
          Save checkpoint
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={closeModal}>
          Cancel
        </DialogButton>
      </Focusable>
    </ModalRoot>
  );
}
