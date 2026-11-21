import { DialogButton, Field, Focusable } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { useState } from "react";
import { exportSnapshots } from "../backend";
import { plainError } from "../format";

// Folder mode for the file picker (FileSelectionType.FOLDER in @decky/api).
const FOLDER = 1 as unknown as Parameters<typeof openFilePicker>[0];

// No lock-in (ADR-0050): copy snapshots out as plain zips to a folder you choose, such as an SD card.
export function ExportSection() {
  const [busy, setBusy] = useState(false);

  const run = async (scope: "latest" | "all") => {
    let folder: string;
    try {
      const picked = await openFilePicker(FOLDER, "/run/media", false, true);
      folder = picked.realpath || picked.path;
    } catch {
      return; // the picker was closed
    }
    setBusy(true);
    try {
      const result = await exportSnapshots(folder, scope);
      toaster.toast({
        title: "Keepsake",
        body: `Exported ${result.snapshots} snapshots of ${result.games} games to ${result.folder}.`,
      });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Not exported: ${plainError(err)}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Field
      label="Export snapshots"
      description="Copy your saves out as plain zip files, with a list of what is in each, to a folder you choose, such as an SD card or USB drive. Nothing there is overwritten."
      childrenLayout="below"
    >
      <Focusable style={{ display: "flex", gap: 8 }}>
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run("latest")}>
          {busy ? "Exporting" : "Export the latest of each game"}
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run("all")}>
          Export every snapshot
        </DialogButton>
      </Focusable>
    </Field>
  );
}
