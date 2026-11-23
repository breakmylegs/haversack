import { ButtonItem, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { gamePause, gamePauseStatus, gameResume, PauseStatus } from "../backend";
import { plainError } from "../format";

// Pause the running game (R29 stage 3, ADR-0094). The game's processes stop until Resume, the game
// exits, Haversack stops, or an hour passes, whichever comes first: its own watchdog always lets
// the game run again (P11). Shown only while a game runs and the Device module is on.
export function PauseButton() {
  const [status, setStatus] = useState<PauseStatus | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    gamePauseStatus()
      .then(setStatus)
      .catch(() => undefined); // keep what is shown (v0.41.1)
  }, []);
  if (!status?.available || status.game === null) return null;
  const toggle = async () => {
    if (busy) return; // never disable a focused button: ignore a second press
    setBusy(true);
    try {
      const next = status.paused ? await gameResume() : await gamePause();
      setStatus(next);
      toaster.toast({
        title: "Haversack",
        body: next.paused ? `Game paused. It carries on by itself after ${next.limitMinutes} minutes.` : "Game running again.",
      });
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <PanelSectionRow>
      <ButtonItem
        layout="below"
        description={status.paused ? "The game is paused. It carries on when you press this." : "Stops the game until you resume it, up to an hour."}
        onClick={() => void toggle()}
      >
        {busy ? "Working" : status.paused ? "Resume game" : "Pause game"}
      </ButtonItem>
    </PanelSectionRow>
  );
}
