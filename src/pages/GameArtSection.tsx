import { DialogButton, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { gameArtApply, gameArtStatus, installerStreamArtSearch } from "../backend";
import { plainError } from "../format";

// Artwork for a non-Steam game (R29 stage 2, ADR-0093): pick it on SteamGridDB (your key, under Install)
// and Haversack adds only the kinds of artwork the game has none of, through Steam (P15). Nothing the
// user or another tool set is replaced.
export function GameArtSection({ gameKey, gameName }: { gameKey: string; gameName: string }) {
  const [missing, setMissing] = useState<string[] | null>(null);
  const [results, setResults] = useState<{ id: number; name: string; verified: boolean }[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    gameArtStatus(gameKey)
      .then((s) => setMissing(s.nonSteam && s.available ? s.missing : null))
      .catch(() => setMissing(null));
  }, [gameKey]);
  if (!missing) return null;
  if (!missing.length) return <Field label="Artwork" description="This game has all its artwork." />;
  const search = async () => {
    if (busy) return; // never disable a focused button: ignore a second press
    setBusy(true);
    try {
      setResults(await installerStreamArtSearch(gameName));
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  const apply = async (id: number) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await gameArtApply(gameKey, id);
      toaster.toast({ title: "Haversack", body: `${r.queued} images going to ${gameName}.` });
      setResults(null);
      setMissing([]);
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Field
      label="Artwork"
      description={`No ${missing.join(", ")} yet. Find the game on SteamGridDB and Haversack adds only those, through Steam.`}
      childrenLayout="below"
    >
      {results ? (
        <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {results.length ? (
            results.map((r) => (
              <DialogButton key={r.id} style={{ width: "auto" }} onClick={() => void apply(r.id)}>
                {r.name}
                {r.verified ? " (verified)" : ""}
              </DialogButton>
            ))
          ) : (
            <span>Nothing found on SteamGridDB.</span>
          )}
          <DialogButton style={{ width: "auto" }} onClick={() => setResults(null)}>
            Cancel
          </DialogButton>
        </Focusable>
      ) : (
        <DialogButton style={{ width: "auto" }} onClick={() => void search()}>
          {busy ? "Looking" : "Find artwork"}
        </DialogButton>
      )}
    </Field>
  );
}
