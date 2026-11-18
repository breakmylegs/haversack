import { DialogButton, Field, Focusable, TextField, ToggleField } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  addCustomPath,
  GameConfig,
  GameEntry,
  gamePlaytime,
  getGame,
  IdentitySuggestion,
  MatchInfo,
  MatchProposal,
  Playtime,
  Preview,
  previewGame,
  searchTitles,
  SteamCloud,
  updateGameConfig,
} from "../backend";
import { IdentityPanel } from "./IdentityPanel";
import { ProposalCard } from "./ProposalCard";
import { LaunchGatePanel } from "./LaunchGatePanel";
import { SnapshotsPanel } from "./SnapshotsPanel";
import { SyncPanel } from "./SyncPanel";

// FileSelectionType.FOLDER in @decky/api is a type-only const enum (value 1).
const FOLDER = 1 as unknown as Parameters<typeof openFilePicker>[0];

const METHOD_TEXT: Record<MatchInfo["method"], string> = {
  manual: "Matched by your choice",
  "steam-id": "Matched by Steam ID",
  title: "Matched by title",
  ambiguous: "Several titles match. Choose one.",
  none: "No match found. Choose one.",
  "no-save-data": "Known game with no save locations in the manifest",
  "no-manifest": "The manifest has not been downloaded yet",
  "manual-key": "Synced by its own game key (no manifest entry)",
};

function sizeText(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function durationText(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours ? `${hours} h ${minutes} min` : `${minutes} min`;
}

export function GameDetail({ gameKey, onBack }: { gameKey: string; onBack: () => void }) {
  const [game, setGame] = useState<GameEntry | null>(null);
  const [config, setConfig] = useState<GameConfig | null>(null);
  const [match, setMatch] = useState<MatchInfo | null>(null);
  const [suggestions, setSuggestions] = useState<IdentitySuggestion[]>([]);
  const [proposal, setProposal] = useState<MatchProposal | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<string[]>([]);
  const [exclusions, setExclusions] = useState("");
  const [busy, setBusy] = useState(false);
  const [hasRegistry, setHasRegistry] = useState(false);
  const [steamCloud, setSteamCloud] = useState<SteamCloud>(null);
  const [played, setPlayed] = useState<Playtime | null>(null);

  const load = async () => {
    const data = await getGame(gameKey);
    setGame(data.game);
    setConfig(data.config);
    setMatch(data.match);
    setSuggestions(data.suggestions ?? []);
    setProposal(data.proposal ?? null);
    setHasRegistry(Boolean(data.hasRegistry));
    setSteamCloud(data.steamCloud ?? null);
    setExclusions(data.config.exclusions.join(", "));
    setQuery(data.game.name);
  };

  const runPreview = async () => {
    setBusy(true);
    try {
      setPreview(await previewGame(gameKey));
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Preview failed: ${err}` });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    gamePlaytime(gameKey)
      .then(setPlayed)
      .catch(() => setPlayed(null)); // offline or not synced: simply not shown
    load()
      .then(runPreview)
      .catch((err) => toaster.toast({ title: "Keepsake", body: String(err) }));
  }, [gameKey]);

  const change = async (changes: Partial<GameConfig>, done: string) => {
    try {
      setConfig(await updateGameConfig(gameKey, changes));
      toaster.toast({ title: "Keepsake", body: done });
      await load();
      await runPreview();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Not saved: ${err}` });
    }
  };

  const pickFolder = async () => {
    const start = preview?.roots.base ?? preview?.roots.winDocuments ?? preview?.roots.home ?? "/";
    try {
      const picked = await openFilePicker(FOLDER, start, false, true);
      setConfig(await addCustomPath(gameKey, picked.realpath || picked.path));
      toaster.toast({ title: "Keepsake", body: "Custom path added." });
      await runPreview();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Not added: ${err}` });
    }
  };

  if (!game || !config || !match) return <Field label="Loading" />;

  const candidates = results.length ? results : match.candidates;

  return (
    <div>
      <Focusable style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <DialogButton style={{ width: "auto" }} onClick={onBack}>
          Back to games
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void runPreview()}>
          {busy ? "Scanning" : "Refresh preview"}
        </DialogButton>
      </Focusable>
      <Field label={game.name} description={`${METHOD_TEXT[match.method]}${match.title ? `: ${match.title}` : ""}`} />
      {played && played.totalSeconds > 0 && (
        <Field
          focusable
          label={`Played ${durationText(played.totalSeconds)} on your devices`}
          description={played.byDevice.map((d) => `${d.device}: ${durationText(d.seconds)}`).join("; ")}
        />
      )}
      {proposal && (
        <ProposalCard
          gameKey={gameKey}
          gameName={game.name}
          proposal={proposal}
          onChanged={() => void load().then(runPreview)}
        />
      )}
      <IdentityPanel
        gameKey={gameKey}
        config={config}
        match={match}
        suggestions={proposal ? [] : suggestions}
        onChanged={() => void load().then(runPreview)}
      />
      {match.gameKey && <Field label="Game key" description={`${match.gameKey}. The same on every device.`} />}

      <Field label="Change match" description="Search the manifest and choose the right game." childrenLayout="below">
        <TextField value={query} onChange={(e) => setQuery(e.target.value)} />
        <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          <DialogButton style={{ width: "auto" }} onClick={() => void searchTitles(query).then(setResults)}>
            Search
          </DialogButton>
          {config.matchTitle && (
            <DialogButton style={{ width: "auto" }} onClick={() => void change({ matchTitle: null }, "Automatic match restored.")}>
              Use automatic match
            </DialogButton>
          )}
        </Focusable>
      </Field>
      {candidates.map((title) => (
        <Field key={title} focusable={false} label={title} childrenLayout="inline">
          <DialogButton style={{ width: "auto" }} onClick={() => void change({ matchTitle: title }, `Matched to ${title}.`)}>
            Use this
          </DialogButton>
        </Field>
      ))}

      <ToggleField
        label="Include config files"
        description="Off by default: config files often hold screen and graphics settings that differ between devices."
        checked={config.includeConfig}
        onChange={(on) => void change({ includeConfig: on }, on ? "Config files included." : "Config files excluded.")}
      />
      {hasRegistry && (
        <ToggleField
          label="Sync registry keys"
          description="This game keeps some of its data in the Proton registry. When on, those keys are saved with the game and put back when a save is restored, only while the game is closed, with a backup. Other registry keys are never touched. Shared with your other devices."
          checked={config.syncRegistry}
          onChange={(on) => void change({ syncRegistry: on }, on ? "Registry keys will be synced." : "Registry keys will not be synced.")}
        />
      )}
      {steamCloud && (
        <Field
          label="Steam Cloud"
          description={
            steamCloud === "cloud"
              ? "This game uses Steam Cloud, which already keeps its saves in step. Keepsake is not needed for it."
              : steamCloud === "no-cloud"
                ? "No Steam Cloud saves found for this game. Keepsake can sync it."
                : "Not played yet, so Steam Cloud use is unknown."
          }
        />
      )}

      <Field label="Custom paths" description="Extra folders to sync, inside this game's save folders." childrenLayout="below">
        {config.customPaths.map((p, i) => (
          <Focusable key={`${p.root}/${p.rel}`} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
            <div style={{ fontSize: 12, flex: 1 }}>{`<${p.root}>/${p.rel}`}</div>
            <DialogButton
              style={{ width: "auto" }}
              onClick={() =>
                void change({ customPaths: config.customPaths.filter((_, j) => j !== i) }, "Custom path removed.")
              }
            >
              Remove
            </DialogButton>
          </Focusable>
        ))}
        <DialogButton style={{ width: "auto" }} onClick={() => void pickFolder()}>
          Add folder
        </DialogButton>
      </Field>

      <Field label="Exclusions" description="Patterns to leave out, separated by commas, for example */screenshots/*" childrenLayout="below">
        <TextField value={exclusions} onChange={(e) => setExclusions(e.target.value)} />
        <DialogButton
          style={{ width: "auto", marginTop: 8 }}
          onClick={() =>
            void change(
              { exclusions: exclusions.split(",").map((s) => s.trim()).filter(Boolean) },
              "Exclusions saved.",
            )
          }
        >
          Save exclusions
        </DialogButton>
      </Field>

      {match.gameKey && (
        <SyncPanel
          gameKey={gameKey}
          enabled={config.enabled}
          kind={game.kind}
          onEnabled={() => void load().then(runPreview)}
        />
      )}
      {match.gameKey && (
        <LaunchGatePanel
          gameKey={gameKey}
          appid={game.appid}
          mode={config.launchGate}
          onMode={(m) => setConfig({ ...config, launchGate: m })}
        />
      )}
      {match.gameKey && <SnapshotsPanel gameKey={gameKey} gameName={game.name} />}

      {preview && (
        <>
          <Field
            label={`Preview: ${preview.totalFiles} files, ${sizeText(preview.totalBytes)}`}
            description={`${preview.excluded} excluded by rules. ${preview.warnings.join(". ")}`}
          />
          {preview.entries.map((entry) => (
            <Field
              key={`${entry.source}-${entry.path}-${entry.pattern}`}
              focusable
              label={`${entry.path}${entry.source === "custom" ? "  (custom)" : ""}`}
              description={`${entry.files} files, ${sizeText(entry.bytes)}${entry.samples.length ? `. ${entry.samples.slice(0, 5).join(", ")}` : ""}`}
            />
          ))}
          {preview.skipped.length > 0 && (
            <Field
              focusable
              label={`${preview.skipped.length} manifest paths not used`}
              description={preview.skipped
                .slice(0, 8)
                .map((s) => `${s.path}: ${s.reason}`)
                .join("; ")}
            />
          )}
        </>
      )}
    </div>
  );
}
