import { DialogButton, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { installerStreamArtApply, installerStreamArtSearch, installerStreamTiles } from "../backend";
import { plainError } from "../format";

// Artwork for streaming tiles (R18, ADR-0081): Steam lists a non-Steam game installed on another
// device with no artwork. Pick it on SteamGridDB and Haversack sets the tile's artwork through
// Steam, as for an installed game. Only after the user chooses the game.

type Tile = { appid: number; name: string; devices: string[] };

export function StreamArtSection() {
  const [tiles, setTiles] = useState<Tile[]>([]);
  const [picking, setPicking] = useState<{ tile: Tile; results: { id: number; name: string; verified: boolean }[] } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    installerStreamTiles()
      .then(setTiles)
      .catch(() => setTiles([]));
  }, []);
  if (!tiles.length) return null;
  const search = async (tile: Tile) => {
    setBusy(true);
    try {
      setPicking({ tile, results: await installerStreamArtSearch(tile.name) });
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  const apply = async (tile: Tile, gameId: number) => {
    setBusy(true);
    try {
      const r = await installerStreamArtApply(tile.appid, gameId);
      toaster.toast({ title: "Haversack", body: `${r.queued} images going to ${tile.name}'s streaming tile.` });
      setPicking(null);
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Field
        label="Artwork for streaming tiles"
        description="Steam shows non-Steam games installed on your other devices with no artwork. Find each one on SteamGridDB (your SteamGridDB key, under Install) and Haversack sets the tile's artwork through Steam."
      />
      {tiles.map((tile) => (
        <Field
          key={tile.appid}
          label={tile.name || `App ${tile.appid}`}
          description={tile.devices.length ? `Streams from ${tile.devices.join(", ")}` : "Streams from another device"}
          childrenLayout="below"
        >
          {picking?.tile.appid === tile.appid ? (
            <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {picking.results.length ? (
                picking.results.map((r) => (
                  <DialogButton key={r.id} style={{ width: "auto" }} disabled={busy} onClick={() => void apply(tile, r.id)}>
                    {r.name}
                    {r.verified ? " (verified)" : ""}
                  </DialogButton>
                ))
              ) : (
                <span>Nothing found on SteamGridDB.</span>
              )}
              <DialogButton style={{ width: "auto" }} onClick={() => setPicking(null)}>
                Cancel
              </DialogButton>
            </Focusable>
          ) : (
            <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void search(tile)}>
              Find artwork
            </DialogButton>
          )}
        </Field>
      ))}
    </>
  );
}
