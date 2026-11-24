import { ButtonItem, DialogButton, Field, ModalRoot, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { useEffect, useState } from "react";
import { discoverGames, GameEntry } from "../backend";
import { GameArtSection } from "./GameArtSection";
import { InStepPanel } from "./InStepPanel";
import { SendPanel } from "./SendPanel";

// Games and devices, Games (the strip, ADR-0098): this device's non-Steam games. Choosing one opens
// what can be done with it: send it to your other handheld, keep it in step, and find its artwork.
// The modal is where focus may move; the page itself takes none (v0.41.1).

function GameModal({ game, closeModal }: { game: GameEntry; closeModal?: () => void }) {
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ fontSize: 20, fontWeight: "bold", marginBottom: 8 }}>{game.name}</div>
      <div style={{ maxHeight: "65vh", overflowY: "auto" }}>
        <SendPanel gameKey={game.key} gameName={game.name} />
        <InStepPanel appid={game.appid} />
        <GameArtSection gameKey={game.key} gameName={game.name} />
      </div>
      <DialogButton style={{ width: "auto", marginTop: 12 }} onClick={closeModal}>
        Close
      </DialogButton>
    </ModalRoot>
  );
}

export function GamesList() {
  const [games, setGames] = useState<GameEntry[] | null>(null);
  const [problem, setProblem] = useState("");
  useEffect(() => {
    discoverGames(false)
      .then((r) => setGames(r.games.filter((g) => g.kind === "shortcut").sort((a, b) => a.name.localeCompare(b.name))))
      .catch((err) => setProblem(String(err))); // keep what is shown (v0.41.1)
  }, []);
  if (!games) return <Field label="Games" description={problem || "Looking for this device's games"} />;
  if (!games.length) return <Field label="Games" description="No non-Steam games on this device yet. Install one from Install, or get one from your other device." />;
  return (
    <PanelSection>
      <Field label="Games" description="Your non-Steam games on this device. Choose one to send it, keep it in step or find its artwork." />
      {games.map((g) => (
        <PanelSectionRow key={g.key}>
          <ButtonItem layout="below" onClick={() => showModal(<GameModal game={g} />)}>
            {g.name}
          </ButtonItem>
        </PanelSectionRow>
      ))}
    </PanelSection>
  );
}
