import { ButtonItem, PanelSectionRow } from "@decky/ui";
import { addEventListener, removeEventListener } from "@decky/api";
import { useEffect, useState } from "react";
import { advisorView, AdvisorView } from "../backend";

// Advisor in the Quick Access Menu: the top advice for the game being played, two lines inside
// Now playing (layout v3, ADR-0073). Read-only (P16).

const ADVISOR_EVENT = "keepsake_advisor";

export function AdvisorQam({ onOpen }: { onOpen: () => void }) {
  const [view, setView] = useState<AdvisorView | null>(null);

  useEffect(() => {
    const load = () =>
      advisorView()
        .then(setView)
        .catch(() => undefined);
    void load();
    const listener = addEventListener(ADVISOR_EVENT, () => void load());
    return () => removeEventListener(ADVISOR_EVENT, listener);
  }, []);

  if (!view?.running || !view.recommendations?.length) return null;
  const top = view.recommendations[0];
  const lines = [...top.lines.power, ...top.lines.display, ...top.lines.scaling].slice(0, 2);
  const where = top.source === "fallback" ? "general advice" : `from ${top.device_reported}, ${top.confidence} confidence`;
  return (
    <PanelSectionRow>
      <ButtonItem layout="below" description={lines.join(" ")} onClick={onOpen}>
        Advisor ({where})
      </ButtonItem>
    </PanelSectionRow>
  );
}
