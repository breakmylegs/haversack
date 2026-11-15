import { DialogButton, Field, Focusable, TextField, ToggleField } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  addCustomPath,
  GameConfig,
  GameEntry,
  getGame,
  MatchInfo,
  Preview,
  previewGame,
  searchTitles,
  updateGameConfig,
} from "../backend";

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
};

function sizeText(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function GameDetail({ gameKey, onBack }: { gameKey: string; onBack: () => void }) {
  const [game, setGame] = useState<GameEntry | null>(null);
  const [config, setConfig] = useState<GameConfig | null>(null);
  const [match, setMatch] = useState<MatchInfo | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<string[]>([]);
  const [exclusions, setExclusions] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const data = await getGame(gameKey);
    setGame(data.game);
    setConfig(data.config);
    setMatch(data.match);
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
