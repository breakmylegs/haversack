import { DialogButton, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  checkRunningPrefix,
  discoverGames,
  DiscoveryResult,
  GameEntry,
  GameMatch,
  manifestStatus,
  ManifestStatus,
  matchGames,
  refreshManifest,
} from "../backend";
import { GameDetail } from "./GameDetail";

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

function matchText(match: GameMatch | undefined): string {
  if (!match) return "";
  switch (match.method) {
    case "manual":
    case "steam-id":
    case "title":
      return `Manifest: ${match.title}`;
    case "ambiguous":
      return "Manifest: several matches, choose one";
    case "no-save-data":
      return "Manifest: no save locations known";
    case "no-manifest":
      return "Manifest not downloaded yet";
    default:
      return "Manifest: no match";
  }
}

function dateText(seconds: number | undefined): string {
  return seconds ? new Date(seconds * 1000).toISOString().slice(0, 10) : "never";
}

export function GamesPage() {
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [matches, setMatches] = useState<Record<string, GameMatch>>({});
  const [status, setStatus] = useState<ManifestStatus | null>(null);
  const [filter, setFilter] = useState<Filter>("shortcuts");
  const [scanning, setScanning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const scan = async (refresh: boolean) => {
    setScanning(true);
    try {
      setResult(await discoverGames(refresh));
      const list = await matchGames();
      setMatches(Object.fromEntries(list.map((m) => [m.key, m])));
      setStatus(await manifestStatus());
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

  const updateManifest = async () => {
    setRefreshing(true);
    try {
      const outcome = await refreshManifest(true);
      toaster.toast({
        title: "Keepsake",
        body: outcome.ok ? "Manifest is up to date." : `Manifest not updated: ${outcome.reason}`,
      });
      await scan(false);
    } finally {
      setRefreshing(false);
    }
  };

  if (selected) {
    return (
      <GameDetail
        gameKey={selected}
        onBack={() => {
          setSelected(null);
          void scan(false);
        }}
      />
    );
  }

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
      <Field
        label={
          status?.available
            ? `Manifest: ${status.games} games with save data, updated ${dateText(status.fetched)}`
            : "Manifest: not downloaded yet"
        }
        description={status?.attribution}
      />
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
        <DialogButton style={{ width: "auto" }} disabled={refreshing} onClick={() => void updateManifest()}>
          {refreshing ? "Updating manifest" : "Update manifest"}
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
            label={game.name}
            description={`${matchText(matches[game.key])}. ${prefixText(game)}.${flags.length ? `  ${flags.join(", ")}` : ""}`}
            childrenLayout="inline"
          >
            <Focusable style={{ display: "flex", gap: 8 }}>
              <DialogButton style={{ width: "auto" }} onClick={() => setSelected(game.key)}>
                Open
              </DialogButton>
              {running && (
                <DialogButton style={{ width: "auto" }} onClick={() => void crossCheck(game)}>
                  Check prefix
                </DialogButton>
              )}
            </Focusable>
          </Field>
        );
      })}
    </div>
  );
}
