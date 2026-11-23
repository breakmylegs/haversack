import { DialogButton, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { GameConfig, IdentitySuggestion, MatchInfo, newGameKey, setGameKey } from "../backend";
import { plainError } from "../format";

const SIGNAL_TEXT: Record<string, string> = {
  exe: "same program file",
  "exe-generic": "same (common) program file name",
  folder: "same install folder",
  name: "same name",
  "name-partial": "similar name",
  saves: "same save folders",
  "saves-partial": "some of the same save folders",
};

function evidence(s: IdentitySuggestion): string {
  return `${s.signals.map((x) => SIGNAL_TEXT[x] ?? x).join(", ")} (${s.sources.join(" and ")})`;
}

// Cross-device matching (ADR-0011): suggestions with their evidence, and a key for games the manifest lacks.
export function IdentityPanel({
  gameKey,
  config,
  match,
  suggestions,
  onChanged,
}: {
  gameKey: string;
  config: GameConfig;
  match: MatchInfo;
  suggestions: IdentitySuggestion[];
  onChanged: () => void;
}) {
  const apply = async (work: () => Promise<GameConfig>, done: string) => {
    try {
      await work();
      toaster.toast({ title: "Haversack", body: done });
      onChanged();
    } catch (err) {
      toaster.toast({ title: "Haversack", body: `Not changed: ${plainError(err)}` });
    }
  };

  return (
    <div>
      {config.gameKeySource === "auto" && (
        <Field
          label="Matched to your other device automatically"
          description={`This game uses the key ${config.gameKey}, found by its program file, folders and save folders. Change it below if that is wrong.`}
        />
      )}
      {suggestions.length > 0 && (
        <Field label="Same game on another device?" description="Haversack compared program files, install folders and save folders." />
      )}
      {suggestions.map((s) => (
        <Field key={s.gameKey} label={`${s.title ?? s.gameKey} (score ${s.score})`} description={evidence(s)} childrenLayout="below">
          <DialogButton
            style={{ width: "auto" }}
            disabled={config.gameKey === s.gameKey}
            onClick={() => void apply(() => setGameKey(gameKey, s.gameKey, s.title), `Now synced as ${s.title ?? s.gameKey}.`)}
          >
            {config.gameKey === s.gameKey ? "In use" : "Use this"}
          </DialogButton>
        </Field>
      ))}
      <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
        {!match.gameKey && (
          <DialogButton
            style={{ width: "auto" }}
            onClick={() => void apply(() => newGameKey(gameKey), "This game has its own key now. Add its save folders below.")}
          >
            Give it its own game key
          </DialogButton>
        )}
        {config.gameKey && (
          <DialogButton
            style={{ width: "auto" }}
            onClick={() => void apply(() => setGameKey(gameKey, null, null), "Game key cleared.")}
          >
            Clear game key
          </DialogButton>
        )}
      </Focusable>
    </div>
  );
}
