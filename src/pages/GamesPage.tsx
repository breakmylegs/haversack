import { DialogButton, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { checkRunningPrefix, discoverGames, DiscoveryResult, GameEntry } from "../backend";

type Filter = "shortcuts" | "steam" | "all";

const FILTER_LABELS: Record<Filter, string> = {
  shortcuts: "Non-Steam shortcuts",
  steam: "Steam games",
  all: "All",
};

function prefixText(game: GameEntry): string {
  if (!game.prefix) return game.kind === "steam" ? "No Proton prefix (native or never run)" : "No prefix found";
  const id = game.prefix.split("/").pop();
  const where = game.prefix_library_index === 0 ? "internal library" : `library ${game.prefix_library_index}`;
  return `compatdata/${id} on the ${where}${game.exe_inside_prefix ? ", game installed inside the prefix" : ""}`;
}

function lastPlayedText(seconds: number): string {
  return seconds > 0 ? new Date(seconds * 1000).toISOString().slice(0, 10) : "never";
}

export function GamesPage() {
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [filter, setFilter] = useState<Filter>("shortcuts");
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scan = async (refresh: boolean) => {
    setScanning(true);
    try {
      setResult(await discoverGames(refresh));
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setScanning(false);
    }
  };

  useEffect(() => {
    void scan(false);
  }, []);

  const runningAppId = SteamUIStore?.MainRunningAppID;
  const games = (result?.games ?? []).filter(
    (g) => filter === "all" || (filter === "shortcuts" ? g.kind === "shortcut" : g.kind === "steam"),
  );

  const crossCheck = async (game: GameEntry) => {
    const outcome = await checkRunningPrefix(game.key);
    const body =
      outcome.status === "match"
        ? "The running game uses the discovered prefix."
        : outcome.status === "mismatch"
          ? "The running game uses a different prefix. Sync is blocked for this game."
          : "No running process with a prefix was found for this game.";
    toaster.toast({ title: game.name, body });
    void scan(false);
  };

  return (
    <div>
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
        {(Object.keys(FILTER_LABELS) as Filter[]).map((f) => (
          <DialogButton
            key={f}
            style={{ width: "auto", opacity: f === filter ? 1 : 0.6 }}
            onClick={() => setFilter(f)}
          >
            {FILTER_LABELS[f]}
          </DialogButton>
        ))}
        <DialogButton style={{ width: "auto" }} disabled={scanning} onClick={() => void scan(true)}>
          {scanning ? "Scanning" : "Rescan"}
        </DialogButton>
      </Focusable>
      {error && <Field label="Scan failed" description={error} />}
      {result && result.roots.length === 0 && <Field label="No Steam installation found" />}
      {result && <Field label={`${games.length} shown`} description={`${result.games.length} found on this device.`} />}
      {games.map((game) => {
        const mismatch = game.key in (result?.mismatches ?? {}) || "_unreadable" in (result?.mismatches ?? {});
        const running = runningAppId !== undefined && runningAppId === game.appid;
        const flags = [
          game.kind === "shortcut" && !game.is_default_user ? "other Steam user" : "",
          mismatch ? "PREFIX MISMATCH, sync blocked" : "",
          running ? "running" : "",
          ...game.notes,
        ].filter(Boolean);
        return (
          <Field
            key={game.key}
            focusable={!running}
            label={game.name}
            description={`${prefixText(game)}. Last played ${lastPlayedText(game.last_played)}. ID ${game.appid}.${flags.length ? `  ${flags.join(", ")}` : ""}`}
            childrenLayout={running ? "below" : undefined}
          >
            {running && (
              <DialogButton style={{ width: "auto" }} onClick={() => void crossCheck(game)}>
                Check running prefix
              </DialogButton>
            )}
          </Field>
        );
      })}
    </div>
  );
}
