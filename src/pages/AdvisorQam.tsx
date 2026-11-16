import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { addEventListener, removeEventListener } from "@decky/api";
import { useEffect, useState } from "react";
import { advisorView, AdvisorView } from "../backend";

// Advisor in the Quick Access Menu: the top advice for the game being played. Read-only (P16).

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
  const lines = [...top.lines.power, ...top.lines.display, ...top.lines.scaling].slice(0, 4);
  return (
    <PanelSection title="Advisor">
      <PanelSectionRow>
        <div style={{ fontSize: 12 }}>
          {view.game ? `${view.game.name}: ` : `${view.device?.name}: `}
          {top.source === "fallback" ? "general advice" : `from ${top.device_reported} (${top.matchLabel})`}, {top.confidence}{" "}
          confidence
        </div>
      </PanelSectionRow>
      {lines.map((line) => (
        <PanelSectionRow key={line}>
          <div style={{ fontSize: 12 }}>{line}</div>
        </PanelSectionRow>
      ))}
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onOpen}>
          All advice
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
