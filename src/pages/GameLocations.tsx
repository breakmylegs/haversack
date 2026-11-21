// The save locations one game uses (ADR-0071): all of them by default. Shown only with several locations.
import { Field, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { Backend, GameConfig, locationsStatus, setGameLocations } from "../backend";
import { BACKEND_LABELS, plainError } from "../format";

export function GameLocations({ gameKey, config, onConfig }: { gameKey: string; config: GameConfig; onConfig: (c: GameConfig) => void }) {
  const [inUse, setInUse] = useState<Backend[]>([]);
  useEffect(() => {
    locationsStatus()
      .then((s) => setInUse(s.locations.map((l) => l.id)))
      .catch(() => setInUse([]));
  }, []);
  if (inUse.length < 2) return null;
  const chosen = config.locations ?? inUse;
  const toggle = (id: Backend, on: boolean) => {
    const next = on ? [...chosen, id] : chosen.filter((c) => c !== id);
    if (!next.length) {
      toaster.toast({ title: "Keepsake", body: "A game needs at least one save location." });
      return;
    }
    const all = inUse.every((b) => next.includes(b));
    void setGameLocations(gameKey, all ? null : next)
      .then(onConfig)
      .catch((err) => toaster.toast({ title: "Keepsake", body: plainError(err) }));
  };
  return (
    <>
      <Field label="Save locations for this game" description="Its snapshots go to each location you leave on." />
      {inUse.map((id) => (
        <ToggleField key={id} label={BACKEND_LABELS[id]} checked={chosen.includes(id)} onChange={(on) => toggle(id, on)} />
      ))}
    </>
  );
}
