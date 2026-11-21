import { DialogButton, Field, Focusable } from "@decky/ui";
import { addEventListener, removeEventListener } from "@decky/api";
import { useEffect, useState } from "react";
import { advisorView, AdvisorView, qamSummary, QamSummary, setSetting } from "../backend";
import { agoText, SYNC_LABELS } from "../format";
import { openSection } from "../routes";
import { openCheckpointModal } from "./CheckpointModal";
import { SessionCards } from "./SessionCards";

// Play, Now playing (layout v3, ADR-0073): the game in play or the last one, its saves, and the
// Advisor's top advice and last session. Read-only apart from Save checkpoint.

const ADVISOR_EVENT = "keepsake_advisor";

export function NowPlaying() {
  const [summary, setSummary] = useState<QamSummary | null>(null);
  const [view, setView] = useState<AdvisorView | null>(null);

  useEffect(() => {
    qamSummary()
      .then(setSummary)
      .catch(() => undefined);
    const load = () =>
      advisorView()
        .then(setView)
        .catch(() => setView(null));
    void load();
    const listener = addEventListener(ADVISOR_EVENT, () => void load());
    return () => removeEventListener(ADVISOR_EVENT, listener);
  }, []);

  const game = summary?.currentGame;
  const top = view?.running ? view.recommendations?.[0] : undefined;
  const lines = top ? [...top.lines.power, ...top.lines.display, ...top.lines.scaling].slice(0, 6) : [];
  return (
    <div>
      {game ? (
        <Field label={`Playing: ${game.name}`} description={SYNC_LABELS[game.status]} childrenLayout="below">
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <DialogButton style={{ width: "auto" }} onClick={() => openCheckpointModal(game.key, game.name)}>
              Save checkpoint
            </DialogButton>
            <DialogButton style={{ width: "auto" }} onClick={() => openSection("saves", "games")}>
              Open in Saves
            </DialogButton>
          </Focusable>
        </Field>
      ) : (
        <Field
          label="No game is running"
          description={summary ? `Last sync ${agoText(summary.lastSync)}. Start a game to see its saves and advice here.` : "Loading"}
        />
      )}
      {summary?.setupComplete && !summary.tipsDismissed && (
        <Field
          label="Tip"
          description="While you play, Save checkpoint (here or in the quick access menu) keeps a named copy of your save. In a game's History you can bring back older saves, even single files."
          childrenLayout="below"
        >
          <DialogButton
            style={{ width: "auto" }}
            onClick={() => void setSetting("tipsDismissed", true).then(() => setSummary({ ...summary, tipsDismissed: true }))}
          >
            Got it
          </DialogButton>
        </Field>
      )}
      {lines.length > 0 && (
        <Field label="Advisor suggests" description={lines.join(" ")} childrenLayout="below">
          <DialogButton style={{ width: "auto" }} onClick={() => openSection("play", "advisor")}>
            Open Advisor
          </DialogButton>
        </Field>
      )}
      {view?.sessions?.last && <SessionCards sessions={view.sessions} />}
    </div>
  );
}
