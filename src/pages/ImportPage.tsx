import { ConfirmModal, DialogButton, Field, Focusable, showModal, TextField } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { useState } from "react";
import { ImportResult, ludusaviImport, ludusaviScan, LudusaviGame } from "../backend";

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

  const scan = async (path: string) => {
    setBusy(true);
    try {
      const found = await ludusaviScan(path);
      setRoot(found.root);
      setGames(found.games);
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Could not read the folder: ${err}` });
    } finally {
      setBusy(false);
    }
  };

  const pick = async () => {
    try {
      const picked = await openFilePicker(FOLDER, root.startsWith("/") ? root : "/home", false, true);
      await scan(picked.realpath || picked.path);
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `No folder chosen: ${err}` });
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
            toaster.toast({ title: "Keepsake", body: `Import failed: ${err}` });
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
      {(games ?? []).map((game) => {
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
