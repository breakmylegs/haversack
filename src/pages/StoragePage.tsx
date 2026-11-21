import { ConfirmModal, DialogButton, Field, Focusable, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { cancelPrefixReset, clearShaderCache, deleteOldPrefix, resetPrefix, StorageRow, storageUsage } from "../backend";
import { plainError } from "../format";

function size(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${Math.max(0, Math.round(bytes / 1024))} KB`;
}

function breakdown(row: StorageRow): string {
  const parts = [
    row.install.insidePrefix ? "game inside its prefix" : row.install.present ? `game ${size(row.install.bytes)}` : "",
    row.prefix.present ? `prefix ${size(row.prefix.bytes)}` : "",
    row.shaderCache.present ? `shader cache ${size(row.shaderCache.bytes)}` : "",
    row.saves.bytes ? `saves ${size(row.saves.bytes)}` : "",
  ].filter(Boolean);
  return `${parts.join(", ") || "Nothing on disk found"}${row.partial ? ". Still counting: some folders are very large." : ""}`;
}

// Disk use per game, clearing a shader cache, and "reset prefix, keep saves" (ADR-0052).
export function StoragePage() {
  const [rows, setRows] = useState<StorageRow[] | null>(null);
  const [notMeasured, setNotMeasured] = useState(0);
  const [busy, setBusy] = useState(false);

  const measure = async () => {
    setBusy(true);
    try {
      const result = await storageUsage(null);
      setRows(result.games);
      setNotMeasured(result.notMeasured);
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };

  const act = (title: string, description: string, ok: string, work: () => Promise<string>) =>
    showModal(
      <ConfirmModal
        strTitle={title}
        strDescription={description}
        strOKButtonText={ok}
        strCancelButtonText="Cancel"
        onOK={async () => {
          setBusy(true);
          try {
            toaster.toast({ title: "Keepsake", body: await work() });
          } catch (err) {
            toaster.toast({ title: "Keepsake", body: plainError(err) });
          } finally {
            setBusy(false);
            await measure();
          }
        }}
      />,
    );

  return (
    <div>
      <Field
        label="Storage"
        description="How much space each game uses: the game, its Proton prefix, its shader cache and its saves. Quit a game before changing it here."
        childrenLayout="below"
      >
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void measure()}>
          {busy ? "Counting" : rows ? "Count again" : "Count disk use"}
        </DialogButton>
      </Field>
      {notMeasured > 0 && <Field description={`${notMeasured} more games were not counted, to keep this quick.`} />}
      {(rows ?? []).map((row) => (
        <Field key={row.key} label={`${row.name}: ${size(row.totalBytes)}`} description={breakdown(row)} childrenLayout="below">
          {row.reset?.stage === "waiting" && (
            <Field description="Prefix reset: start the game once and quit it at the title screen. Keepsake then puts your saves back." />
          )}
          {row.reset?.stage === "restored" && (
            <Field description="Prefix reset finished and your saves are back. The old prefix is kept until you delete it." />
          )}
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {row.canClearShaderCache && (
              <DialogButton
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() =>
                  act(
                    "Clear the shader cache?",
                    `${size(row.shaderCache.bytes)} will be freed. Steam builds the cache again the next time the game runs, so the first minutes may stutter. Your saves are not touched.`,
                    "Clear",
                    async () => `Freed ${size((await clearShaderCache(row.key)).freed)}.`,
                  )
                }
              >
                Clear shader cache
              </DialogButton>
            )}
            {row.canResetPrefix && !row.reset && (
              <DialogButton
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() =>
                  act(
                    "Reset the prefix and keep the saves?",
                    "Use this when a game will not start because its Proton prefix is broken. Keepsake keeps a copy of the saves, then moves the prefix aside; nothing is deleted. Start the game once afterwards and quit at the title screen: Steam builds a fresh prefix, and Keepsake puts the saves back.",
                    "Reset",
                    async () => (await resetPrefix(row.key), "Prefix moved aside. Start the game once, then quit."),
                  )
                }
              >
                Reset prefix, keep saves
              </DialogButton>
            )}
            {row.reset?.stage === "waiting" && (
              <DialogButton
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() =>
                  act("Undo the reset?", "The old prefix is put back exactly as it was.", "Undo", async () => {
                    await cancelPrefixReset(row.key);
                    return "The old prefix is back.";
                  })
                }
              >
                Undo reset
              </DialogButton>
            )}
            {row.reset?.stage === "restored" && (
              <DialogButton
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() =>
                  act(
                    "Delete the old prefix?",
                    "Only do this once the game works with the fresh prefix. This cannot be undone.",
                    "Delete",
                    async () => `Freed ${size((await deleteOldPrefix(row.key)).freed)}.`,
                  )
                }
              >
                Delete old prefix
              </DialogButton>
            )}
          </Focusable>
        </Field>
      ))}
    </div>
  );
}
