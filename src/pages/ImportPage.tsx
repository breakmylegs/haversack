import { ConfirmModal, DialogButton, Field, Focusable, showModal, TextField } from "@decky/ui";
import { addEventListener, openFilePicker, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  ImportAllStatus,
  ImportResult,
  ludusaviImport,
  ludusaviImportAll,
  ludusaviImportCancel,
  ludusaviImportStatus,
  ludusaviScan,
  LudusaviGame,
} from "../backend";
import { plainError } from "../format";

const IMPORT_EVENT = "keepsake_import_progress";

function batchSummary(s: ImportAllStatus): string {
  const n = (k: keyof ImportAllStatus["summary"]) => s.summary[k] ?? 0;
  return `${n("imported")} imported, ${n("already-imported")} already imported, ${n("nothing-to-import")} with nothing to import, ${n("failed")} failed`;
}

// FileSelectionType.FOLDER in @decky/api is a type-only const enum (value 1).
const FOLDER = 1 as unknown as Parameters<typeof openFilePicker>[0];

function summary(results: ImportResult[]): string {
  const count = (status: ImportResult["status"]) => results.filter((r) => r.status === status).length;
  const parts = [
    `${count("published")} imported`,
    count("already-imported") ? `${count("already-imported")} already imported` : "",
    count("nothing-to-import") ? `${count("nothing-to-import")} with no save files Keepsake knows` : "",
    count("error") ? `${count("error")} failed` : "",
  ].filter(Boolean);
  return parts.join(", ");
}

export function ImportPage() {
  const [root, setRoot] = useState("~/ludusavi-backup");
  const [games, setGames] = useState<LudusaviGame[] | null>(null);
  const [results, setResults] = useState<Record<string, ImportResult[]>>({});
  const [busy, setBusy] = useState(false);
  const [batch, setBatch] = useState<ImportAllStatus | null>(null);

  // Live progress of an import of every game; it runs in the backend, so it carries on if this page closes.
  useEffect(() => {
    const apply = (status: ImportAllStatus) => {
      setBatch(status.total ? status : null);
      setResults((r) => ({ ...r, ...Object.fromEntries(Object.entries(status.games).map(([folder, g]) => [folder, g.results])) }));
    };
    const listener = addEventListener<[ImportAllStatus]>(IMPORT_EVENT, (status) => {
      apply(status);
      if (!status.running && status.total) {
        toaster.toast({ title: "Keepsake", body: `${status.cancelled ? "Import stopped" : "Import finished"}: ${batchSummary(status)}.` });
      }
    });
    ludusaviImportStatus()
      .then(apply)
      .catch(() => undefined);
    return () => removeEventListener(IMPORT_EVENT, listener);
  }, []);

  const eligible = (games ?? []).filter((g) => !g.error && g.backups.length > 0);
  const elsewhere = eligible.filter((g) => !g.localGame || !g.inManifest).length;
  const backupsAll = eligible.reduce((n, g) => n + g.backups.length, 0);

  const importEvery = (mode: "latest" | "all") =>
    showModal(
      <ConfirmModal
        strTitle={mode === "latest" ? "Import the latest backup of every game?" : "Import all backups of every game?"}
        strDescription={`${mode === "latest" ? eligible.length : backupsAll} backups from ${eligible.length} games become snapshots in their games' History, with their original dates. Your current saves on every device stay as they are: restore an imported snapshot from History when you want it.${elsewhere ? ` ${elsewhere} of these games are not on this device or not in the save manifest. They are imported too, so the backups are ready if you install the game later or play it on your other device.` : ""} Backups already imported are skipped, and one game failing does not stop the others.`}
        strOKButtonText="Import"
        strCancelButtonText="Cancel"
        onOK={() =>
          void ludusaviImportAll(root, mode)
            .then(setBatch)
            .catch((err) => toaster.toast({ title: "Keepsake", body: `Import not started: ${plainError(err)}` }))
        }
      />,
    );

  const scan = async (path: string) => {
    setBusy(true);
    try {
      const found = await ludusaviScan(path);
      setRoot(found.root);
      setGames(found.games);
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Could not read the folder: ${plainError(err)}` });
    } finally {
      setBusy(false);
    }
  };

  const pick = async () => {
    try {
      const picked = await openFilePicker(FOLDER, root.startsWith("/") ? root : "/home", false, true);
      await scan(picked.realpath || picked.path);
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `No folder chosen: ${plainError(err)}` });
    }
  };

  const run = (game: LudusaviGame, ids: string[]) =>
    showModal(
      <ConfirmModal
        strTitle={`Import ${game.name}?`}
        strDescription={`${ids.length} backup(s) become snapshots in the History of ${game.gameKey}, with their original dates. Your current saves on every device stay as they are: restore an imported snapshot from History when you want it.`}
        strOKButtonText="Import"
        strCancelButtonText="Cancel"
        onOK={async () => {
          setBusy(true);
          try {
            const outcome = await ludusaviImport(root, game.folder, ids, game.gameKey);
            setResults((r) => ({ ...r, [game.folder]: outcome.results }));
            toaster.toast({ title: game.name, body: summary(outcome.results) });
          } catch (err) {
            toaster.toast({ title: "Keepsake", body: `Import failed: ${plainError(err)}` });
          } finally {
            setBusy(false);
          }
        }}
      />,
    );

  return (
    <div>
      <Field
        label="Import save backups from Ludusavi"
        description="Bring in save-game backups that Ludusavi made on this device. This imports saves only: it does not install, copy or move games. Files are checked against Ludusavi's records, and paths inside any Proton prefix are recognised whatever its compatdata number. Ludusavi's folder is only read, never changed."
      />
      <Field label="Ludusavi backup folder" childrenLayout="below">
        <TextField value={root} disabled={busy} onChange={(e) => setRoot(e.target.value)} />
        <Focusable style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void scan(root)}>
            {busy ? "Working" : "Read folder"}
          </DialogButton>
          <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void pick()}>
            Choose folder
          </DialogButton>
        </Focusable>
      </Field>
      {games && games.length === 0 && <Field label="No Ludusavi games found in this folder" />}
      {eligible.length > 0 && !batch?.running && (
        <Field
          label="Import every game"
          description={`${eligible.length} games with backups.${games && games.length > eligible.length ? ` ${games.length - eligible.length} unreadable or empty are left out.` : ""}`}
          childrenLayout="below"
        >
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => importEvery("latest")}>
              Latest backup of every game ({eligible.length})
            </DialogButton>
            <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => importEvery("all")}>
              All backups of every game ({backupsAll})
            </DialogButton>
          </Focusable>
        </Field>
      )}
      {batch?.running && (
        <Field
          label={`Importing ${Math.min(batch.done + 1, batch.total)} of ${batch.total}${batch.current ? `: ${batch.current}` : ""}`}
          description="Each game is imported in turn. You can stop between games; what is already imported stays."
          childrenLayout="inline"
        >
          <DialogButton style={{ width: "auto" }} onClick={() => void ludusaviImportCancel().then(setBatch)}>
            Stop after this game
          </DialogButton>
        </Field>
      )}
      {batch && !batch.running && (
        <Field label={batch.cancelled ? "Import stopped" : "Import finished"} description={`${batchSummary(batch)}.`} />
      )}
      {[...(games ?? [])]
        .sort((a, b) => Number(batch?.games[b.folder]?.status === "failed") - Number(batch?.games[a.folder]?.status === "failed"))
        .map((game) => {
        const done = results[game.folder];
        const latest = game.backups[game.backups.length - 1];
        const detail = game.error
          ? `Cannot read: ${game.error}`
          : `${game.backups.length} backups. Game key ${game.gameKey}${game.inManifest ? "" : " (not in the manifest)"}. ${
              game.localGame ? `On this device: ${game.localGame}.` : "Not found on this device."
            }${done ? ` Last import: ${summary(done)}.` : ""}`;
        return (
          <Field key={game.folder} label={game.name} description={detail} childrenLayout="below">
            {!game.error && game.backups.length > 0 && (
              <Focusable style={{ display: "flex", gap: 8 }}>
                <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => run(game, [latest.id])}>
                  Import latest
                </DialogButton>
                <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => run(game, game.backups.map((b) => b.id))}>
                  Import all
                </DialogButton>
              </Focusable>
            )}
            {(done ?? [])
              .filter((r) => r.status === "error" || (r.skippedCount ?? 0) > 0)
              .map((r) => (
                <div key={r.backup} style={{ fontSize: 12 }}>
                  {r.backup}: {r.error ?? `${r.skippedCount} files outside known save folders were left out`}
                </div>
              ))}
          </Field>
        );
      })}
    </div>
  );
}
