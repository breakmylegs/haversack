import { DialogButton, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { ReactElement, useEffect, useState } from "react";
import { FaCheckCircle, FaClock, FaCodeBranch, FaExclamationTriangle, FaMinusCircle, FaRegCircle } from "react-icons/fa";
import {
  checkRunningPrefix,
  discoverGames,
  DiscoveryResult,
  enableSteamWithoutCloud,
  GameEntry,
  GameMatch,
  getSettings,
  manifestStatus,
  ManifestStatus,
  matchGames,
  refreshManifest,
  SyncWord,
} from "../backend";
import { SYNC_LABELS } from "../format";
import { GameDetail } from "./GameDetail";

type Filter = "enabled" | "shortcuts" | "steam" | "all";

const FILTER_LABELS: Record<Filter, string> = {
  enabled: "Synced games",
  shortcuts: "Non-Steam shortcuts",
  steam: "Steam games",
  all: "All",
};

const STATUS_ICONS: Record<SyncWord, ReactElement> = {
  off: <FaMinusCircle style={{ opacity: 0.5 }} />,
  "not-synced": <FaRegCircle />,
  synced: <FaCheckCircle style={{ color: "#59bf40" }} />,
  pending: <FaClock style={{ color: "#e5b33a" }} />,
  conflict: <FaCodeBranch style={{ color: "#e04f4f" }} />,
  quarantined: <FaExclamationTriangle style={{ color: "#e5b33a" }} />,
};

function prefixText(game: GameEntry): string {
  if (!game.prefix) return game.kind === "steam" ? "No Proton prefix (native or never run)" : "No prefix found";
  const id = game.prefix.split("/").pop();
  const where = game.prefix_library_index === 0 ? "internal library" : `library ${game.prefix_library_index}`;
  return `compatdata/${id} on the ${where}${game.exe_inside_prefix ? ", game installed inside the prefix" : ""}`;
}

function matchText(match: GameMatch | undefined): string {
  if (!match) return "";
  if (match.proposal) {
    return `Confirm match: looks like ${match.proposal.candidate.title ?? match.proposal.candidate.gameKey}`;
  }
  switch (match.method) {
    case "manual-key":
      return `Synced by its own game key: ${match.gameKey}`;
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
  const [showSteam, setShowSteam] = useState(false);
  const [cloudDetection, setCloudDetection] = useState(false);
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
    getSettings()
      .then((s) => {
        setShowSteam(s.showSteamApps);
        setCloudDetection(s.steamCloudDetection);
      })
      .catch(() => undefined);
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
  // Steam apps are off by default because Steam Cloud covers them (build prompt section 14).
  const filters = (Object.keys(FILTER_LABELS) as Filter[]).filter((f) => showSteam || f !== "steam");
  const visible = (result?.games ?? []).filter((g) => showSteam || g.kind === "shortcut");
  const games = visible.filter((g) => {
    if (filter === "enabled") return matches[g.key]?.enabled;
    if (filter === "shortcuts") return g.kind === "shortcut";
    if (filter === "steam") return g.kind === "steam";
    return true;
  });

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
        {filters.map((f) => (
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
      {showSteam && cloudDetection && Object.values(matches).some((m) => m.steamCloud === "no-cloud" && !m.enabled) && (
        <Field
          label={`${Object.values(matches).filter((m) => m.steamCloud === "no-cloud" && !m.enabled).length} Steam games have no Steam Cloud saves`}
          description="Keepsake can sync them like your non-Steam games."
          childrenLayout="inline"
        >
          <DialogButton
            style={{ width: "auto" }}
            disabled={scanning}
            onClick={() =>
              void enableSteamWithoutCloud()
                .then((r) => toaster.toast({ title: "Keepsake", body: `Sync turned on for ${r.enabled.length} Steam games.` }))
                .then(() => scan(false))
            }
          >
            Sync them all
          </DialogButton>
        </Field>
      )}
      {error && <Field label="Scan failed" description={error} />}
      {result && result.roots.length === 0 && <Field label="No Steam installation found" />}
      {Object.values(matches).some((m) => m.proposal) && (
        <Field
          label={`${Object.values(matches).filter((m) => m.proposal).length} matches need your approval`}
          description="Keepsake found likely matches it is not certain about. Open each game marked Confirm match to approve or choose another."
        />
      )}
      {result && (
        <Field
          label={`${games.length} shown`}
          description={`${result.games.length} found on this device.${showSteam ? "" : " Steam games are hidden (Settings, Show Steam games)."}`}
        />
      )}
      {games.map((game) => {
        const mismatch = game.key in (result?.mismatches ?? {}) || "_unreadable" in (result?.mismatches ?? {});
        const running = runningAppId !== undefined && runningAppId === game.appid;
        const flags = [
          game.kind === "shortcut" && !game.is_default_user ? "other Steam user" : "",
          mismatch ? "PREFIX MISMATCH, sync blocked" : "",
          running ? "running" : "",
          matches[game.key]?.steamCloud === "cloud" ? "uses Steam Cloud" : "",
          matches[game.key]?.steamCloud === "no-cloud" ? "no Steam Cloud" : "",
          ...game.notes,
        ].filter(Boolean);
        return (
          <Field
            key={game.key}
            label={
              <span>
                {STATUS_ICONS[matches[game.key]?.sync ?? "off"]} {game.name}
              </span>
            }
            description={`${SYNC_LABELS[matches[game.key]?.sync ?? "off"]}. ${matchText(matches[game.key])}. ${prefixText(game)}.${flags.length ? `  ${flags.join(", ")}` : ""}`}
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
